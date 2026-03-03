"""
Сервис оффлайн-распределения исследований по врачам.

Постановка задачи: Pm | rⱼ | ΣwⱼTⱼ  (Parallel Machine Weighted Tardiness)
Лит.: Лазарев А.А., Гафаров Е.Р. «Теория расписаний» (МГУ, 2011)

Целевая функция:
    MIN Z = Σᵢ wᵢ × Tᵢ,  Tᵢ = max(0, Cᵢ - dᵢ)

    Cᵢ считается для ВСЕХ исследований — не только назначенных:
      - назначено врачу j : Cᵢ = Cᵢⱼ  (плановое время завершения)
      - не назначено       : Cᵢ = t_now + pᵢ  (оптимистичная нижняя оценка)

Реализация:
  - Основной метод: MILP через PuLP + CBC (pip install pulp)
  - Fallback: жадный WSPT алгоритм (работает без зависимостей)

УП согласно Положению об оплате ОМС:
  Рентген = 0.083 УП, КТ = 0.25 УП, МРТ = 0.333 УП
  Норма = 50 УП/месяц (рентгенолог), 40 УП (завед.)
  max_up_per_day в Doctor — дневной лимит УП (используется напрямую)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Set, Tuple

from django.utils import timezone

from api.models import Doctor, Schedule, Study, StudyType

logger = logging.getLogger(__name__)


# ==============================================================================
# МАППИНГ МОДАЛЬНОСТЕЙ
# ==============================================================================

MODALITY_ALIASES: Dict[str, str] = {
    "KT": "CT", "КТ": "CT", "COMPUTED_TOMOGRAPHY": "CT",
    "MRT": "MRI", "МРТ": "MRI", "MAGNETIC_RESONANCE": "MRI",
    "RENTGEN": "XRAY", "РЕНТГЕН": "XRAY", "X_RAY": "XRAY",
    "US": "US", "УЗИ": "US", "ULTRASOUND": "US",
}


def normalize_modality(m: str) -> str:
    if not m:
        return "OTHER"
    return MODALITY_ALIASES.get(m.strip().upper(), m.strip().upper())


def parse_modalities(data) -> Set[str]:
    if not data:
        return set()
    items = data if isinstance(data, list) else str(data).split("/")
    return {normalize_modality(str(m)) for m in items if m and str(m).strip()}


# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================

PRIORITY_WEIGHTS = {"cito": 100.0, "asap": 10.0, "normal": 1.0}
DEADLINE_HOURS   = {"cito": 2, "asap": 24, "normal": 72}

# Рекомендованное время описания (мин) из Положения об оплате
MODALITY_DURATION_MINUTES = {
    "XRAY": 5, "CT": 15, "CT_CON": 25,
    "MRI": 20, "MRI_CON": 30,
    "MAMMO": 6, "FLUORO": 4, "ECG": 4,
    "HOLTER": 25, "EEG": 20, "US": 10,
}

MIP_TIME_LIMIT  = 300    # 5 минут на батч
MIP_GAP_REL     = 0.01   # 1% gap — хорошее качество
MIP_BATCH_SIZE  = 600    # макс. исследований на один MIP-вызов
                         # При 600×7=4200 переменных CBC работает ~10-60 сек
                         # Для n>BATCH_SIZE задача разбивается на батчи:
                         #   сначала все ASAP (по BATCH_SIZE), затем normal


# ==============================================================================
# СТРУКТУРЫ ДАННЫХ
# ==============================================================================

@dataclass
class StudyData:
    id: int
    research_number: str
    priority: str
    created_at: datetime
    modality: Set[str]
    up_value: float
    duration_minutes: float
    deadline: datetime
    weight: float

    @property
    def duration_hours(self) -> float:
        return self.duration_minutes / 60.0


@dataclass
class DoctorData:
    id: int
    name: str
    modality: Set[str]
    max_up: float
    shift_start: datetime
    shift_end: datetime
    assigned_ids: List[int] = field(default_factory=list)
    used_up: float = 0.0
    used_minutes: float = 0.0

    @property
    def shift_hours(self) -> float:
        return (self.shift_end - self.shift_start).total_seconds() / 3600.0

    @property
    def free_up(self) -> float:
        return max(0.0, self.max_up - self.used_up)


# ==============================================================================
# СЕРВИС
# ==============================================================================

class DistributionService:

    def __init__(self):
        self.now = timezone.now()
        self._debug: List[str] = []

    def _log(self, msg: str):
        logger.info(msg)
        self._debug.append(msg)

    def _make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt if timezone.is_aware(dt) else timezone.make_aware(dt)

    def _modality_ok(self, study_mods: Set[str], doc_mods: Set[str]) -> bool:
        if not study_mods or not doc_mods:
            return True
        return bool(study_mods & doc_mods)

    # ── Загрузка данных ──────────────────────────────────────────────

    def _get_duration(self, study: Study) -> float:
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return float(MODALITY_DURATION_MINUTES.get(mod, 15))
        return 15.0

    def _get_up(self, study: Study) -> float:
        if study.study_type and study.study_type.up_value:
            return float(study.study_type.up_value)
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return {"XRAY": 0.083, "CT": 0.25, "MRI": 0.333, "US": 0.10}.get(mod, 0.25)
        return 0.25

    def load_studies(self) -> List[StudyData]:
        qs = Study.objects.filter(
            diagnostician__isnull=True
        ).select_related("study_type")

        result = []
        for s in qs:
            priority = s.priority or "normal"
            created  = self._make_aware(s.created_at) or self.now

            # Номинальный дедлайн по регламенту (всегда от created_at, не зажатый).
            # Дедлайн в прошлом — это не повод не назначать, а повод назначить первым.
            # Целевая функция сама учтёт накопленную просрочку через T[i].
            deadline = created + timedelta(hours=DEADLINE_HOURS.get(priority, 72))

            # Вес по приоритету.
            # Для уже просроченных увеличиваем пропорционально просрочке:
            # чем дольше снимок ждёт — тем больше штраф за дальнейшее промедление.
            base_weight = PRIORITY_WEIGHTS.get(priority, 1.0)
            if deadline < self.now:
                overdue_hours = (self.now - deadline).total_seconds() / 3600.0
                # +10% за каждый час просрочки, но не более ×10
                overdue_multiplier = min(1.0 + overdue_hours * 0.1, 10.0)
                weight = base_weight * overdue_multiplier
            else:
                weight = base_weight

            result.append(StudyData(
                id=s.id,
                research_number=s.research_number,
                priority=priority,
                created_at=created,
                modality=parse_modalities(s.study_type.modality if s.study_type else ""),
                up_value=self._get_up(s),
                duration_minutes=self._get_duration(s),
                deadline=deadline,
                weight=weight,
            ))

        self._log(f"Исследований без назначения: {len(result)}")
        if result:
            sample = result[:3]
            for s in sample:
                self._log(
                    f"  Пример: id={s.id}, priority={s.priority}, "
                    f"modality={s.modality}, up={s.up_value}, dur={s.duration_minutes}мин"
                )
        return result

    def load_doctors(self) -> List[DoctorData]:
        today = self.now.date()
        schedules = Schedule.objects.filter(
            work_date=today, is_day_off=0
        ).select_related("doctor")

        self._log(f"Расписаний на {today}: {schedules.count()}")

        result = []
        for sch in schedules:
            doc = sch.doctor
            if not doc or not doc.is_active:
                self._log(f"  Пропуск: врач {getattr(doc,'id','?')}, active={getattr(doc,'is_active','?')}")
                continue

            max_up = float(doc.max_up_per_day or 50)

            if sch.time_start and sch.time_end:
                s_start = timezone.make_aware(datetime.combine(today, sch.time_start))
                s_end   = timezone.make_aware(datetime.combine(today, sch.time_end))
            else:
                s_start = self.now.replace(hour=9,  minute=0, second=0, microsecond=0)
                s_end   = self.now.replace(hour=17, minute=0, second=0, microsecond=0)

            shift_h = (s_end - s_start).total_seconds() / 3600.0
            mods    = parse_modalities(doc.modality)

            self._log(
                f"  Врач {doc.fio_alias} (id={doc.id}): "
                f"max_up={max_up}, смена={shift_h:.1f}ч, мод={list(mods)}"
            )

            result.append(DoctorData(
                id=doc.id,
                name=doc.fio_alias or f"Врач {doc.id}",
                modality=mods,
                max_up=max_up,
                shift_start=s_start,
                shift_end=s_end,
            ))

        self._log(f"Врачей загружено: {len(result)}")
        return result

    # ── Жадный WSPT (основной + fallback) ───────────────────────────

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        ignore_up_limit: bool = False,
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[int, int]:
        label = "Жадный (без лимита УП)" if ignore_up_limit else "Жадный WSPT"
        self._log(f"Запуск: {label}...")

        sorted_s = sorted(studies, key=lambda s: (
            {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
            -(s.weight / s.duration_hours) if s.duration_hours > 0 else 0,
            s.deadline,
        ))

        doc_up:  Dict[int, float] = {d.id: 0.0 for d in doctors}
        # Учитываем уже занятое время (CITO назначены ранее)
        doc_min: Dict[int, float] = {
            d.id: (doc_prebooked_minutes or {}).get(d.id, 0.0)
            for d in doctors
        }

        assignment: Dict[int, int] = {}

        for s in sorted_s:
            best_id    = None
            best_score = float("inf")

            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if not ignore_up_limit:
                    if doc_up[d.id] + s.up_value > d.max_up + 1e-9:
                        continue
                if (doc_min[d.id] + s.duration_minutes) / 60.0 > d.shift_hours + 1e-9:
                    continue
                score = doc_min[d.id] / (d.shift_hours * 60) if d.shift_hours > 0 else 1.0
                if score < best_score:
                    best_score = score
                    best_id    = d.id

            if best_id is not None:
                assignment[s.id] = best_id
                doc_up[best_id]  += s.up_value
                doc_min[best_id] += s.duration_minutes

        self._log(f"{label}: назначено {len(assignment)} / {len(studies)}")

        # Диагностика: сколько просроченных CITO назначено vs пропущено
        overdue_cito = [s for s in studies if s.priority == "cito" and s.deadline < self.now]
        assigned_overdue = [s for s in overdue_cito if s.id in assignment]
        skipped_overdue  = [s for s in overdue_cito if s.id not in assignment]
        if overdue_cito:
            self._log(
                f"  Просроченных CITO: {len(overdue_cito)} | "
                f"назначено: {len(assigned_overdue)} | "
                f"пропущено: {len(skipped_overdue)}"
            )
            for s in skipped_overdue[:5]:
                self._log(f"    ПРОПУЩЕНО id={s.id} {s.research_number} "
                          f"(дедлайн {s.deadline.strftime('%H:%M')})")

        for d in doctors:
            cnt  = sum(1 for did in assignment.values() if did == d.id)
            up   = doc_up[d.id]
            mins = doc_min[d.id]
            self._log(
                f"  {d.name}: {cnt} исслед., {up:.2f}/{d.max_up} УП, "
                f"{mins:.0f}/{d.shift_hours*60:.0f} мин"
            )
        return assignment

    # ── MIP ─────────────────────────────────────────────────────────
    #
    # Постановка: Parallel Machine Weighted Tardiness (PMWT)
    #   Лит.: Лазарев А.А., Гафаров Е.Р. «Теория расписаний» (МГУ, 2011)
    #         Постановка Pm | rⱼ | ΣwⱼTⱼ
    #
    # Целевая функция (одна, без β-штрафа):
    #   MIN Z = Σᵢ wᵢ × Tᵢ
    #
    # где:
    #   Tᵢ = max(0, Cᵢ - dᵢ)
    #
    #   Cᵢ считается для ВСЕХ исследований — назначенных и нет:
    #     - назначено врачу j:  Cᵢ = Cᵢⱼ  (плановое время завершения)
    #     - не назначено:       Cᵢ = t_now + pᵢ  (оптимистичная нижняя оценка)
    #
    #
    # Big-M линеаризация max():
    #   T[i] >= C[i,j]  - d[i] - BIG_M*(1 - x[i,j])   ∀(i,j)
    #   T[i] >= C_free[i] - d[i]                         ∀i

    def solve_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[int, int]:
        """
        MILP-решатель с батчингом.

        Если studies > MIP_BATCH_SIZE, задача разбивается на батчи:
          - сортируем по (приоритет, дедлайн)
          - берём батч за батчем, каждый раз обновляем prebooked по уже назначенным
          - результаты объединяем
        """
        try:
            import pulp
        except ImportError:
            self._log("PuLP не установлен → жадный (pip install pulp для MIP)")
            return self.solve_greedy(studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes)

        if len(studies) <= MIP_BATCH_SIZE:
            return self._solve_mip_single(studies, doctors, doc_prebooked_minutes)

        # ── Батчинг ──────────────────────────────────────────────────
        self._log(
            f"MIP батчинг: {len(studies)} исследований → батчи по {MIP_BATCH_SIZE}"
        )
        # Сортировка: сначала срочные, потом по дедлайну
        sorted_studies = sorted(studies, key=lambda s: (
            {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
            s.deadline,
        ))

        assignment: Dict[int, int] = {}
        prebooked = dict(doc_prebooked_minutes or {})

        for batch_start in range(0, len(sorted_studies), MIP_BATCH_SIZE):
            batch = sorted_studies[batch_start: batch_start + MIP_BATCH_SIZE]
            batch_num = batch_start // MIP_BATCH_SIZE + 1
            total_batches = (len(sorted_studies) + MIP_BATCH_SIZE - 1) // MIP_BATCH_SIZE
            self._log(f"  Батч {batch_num}/{total_batches}: {len(batch)} исследований")

            batch_result = self._solve_mip_single(batch, doctors, prebooked)
            assignment.update(batch_result)

            # Обновляем prebooked для следующего батча
            study_map = {s.id: s for s in batch}
            for sid, did in batch_result.items():
                prebooked[did] = prebooked.get(did, 0.0) + study_map[sid].duration_minutes

        self._log(f"MIP батчинг итого: {len(assignment)} / {len(studies)}")
        return assignment

    def _solve_mip_single(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[int, int]:
        """Один MIP-вызов для батча studies."""
        import pulp

        n, m = len(studies), len(doctors)
        self._log(f"MIP: {n} × {m}")

        # ── Совместимые пары ─────────────────────────────────────────
        pairs = [
            (i, j)
            for i, s in enumerate(studies)
            for j, d in enumerate(doctors)
            if self._modality_ok(s.modality, d.modality)
        ]
        self._log(f"  Совместимых пар: {len(pairs)}")
        if not pairs:
            self._log("  Нет совместимых пар → жадный fallback")
            return self.solve_greedy(studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes)

        # ── Оценки Cᵢⱼ (часов от self.now) ──────────────────────────
        sidx: Dict[int, int] = {s.id: i for i, s in enumerate(studies)}
        C: Dict[Tuple[int, int], float] = {}
        for j, d in enumerate(doctors):
            prebooked_h = (doc_prebooked_minutes or {}).get(d.id, 0.0) / 60.0
            effective_start = max(d.shift_start, self.now)
            acc = prebooked_h
            j_studies = sorted(
                [studies[i] for (ii, jj) in pairs if jj == j for i in [ii]],
                key=lambda s: (
                    {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
                    s.deadline,
                ),
            )
            for s in j_studies:
                acc += s.duration_hours
                C[(sidx[s.id], j)] = (
                    effective_start + timedelta(hours=acc) - self.now
                ).total_seconds() / 3600.0

        # ── Дедлайны в часах от self.now ─────────────────────────────
        d_h = [(s.deadline - self.now).total_seconds() / 3600.0 for s in studies]

        # ── C_free[i]: штраф за неназначение ────────────────────────
        horizon_h = max(
            (d.shift_end - self.now).total_seconds() / 3600.0
            for d in doctors
        )
        W_UNASSIGNED = 10.0
        C_free = [
            W_UNASSIGNED * horizon_h + max(0.0, -d_h[i]) + 1.0
            for i in range(n)
        ]

        # ── MAX_T и BIG_M ─────────────────────────────────────────────
        max_remaining_shift = max(
            max(0.0, (d.shift_end - self.now).total_seconds() / 3600.0)
            for d in doctors
        )
        max_overdue = max((max(0.0, -dh) for dh in d_h), default=0.0)
        W_MAX = 10.0
        MAX_T = W_MAX * max_remaining_shift + 2.0 * max_overdue + 2.0
        BIG_M = MAX_T + 1.0

        self._log(
            f"  MAX_T={MAX_T:.1f}ч, BIG_M={BIG_M:.1f}, "
            f"remaining_shift={max_remaining_shift:.1f}ч, overdue={max_overdue:.1f}ч"
        )

        # ── LP задача ────────────────────────────────────────────────
        prob = pulp.LpProblem("PMWT", pulp.LpMinimize)

        x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary")
             for (i, j) in pairs}
        T = {i: pulp.LpVariable(f"T_{i}", lowBound=0, upBound=MAX_T)
             for i in range(n)}

        # Целевая функция
        prob += pulp.lpSum(studies[i].weight * T[i] for i in range(n)), "Obj"

        # (A) Каждое исследование — не более 1 врачу
        for i in range(n):
            row = [x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]]
            if row:
                prob += pulp.lpSum(row) <= 1, f"A{i}"

        # (B) Лимит УП врача
        for j, d in enumerate(doctors):
            col = [studies[i].up_value * x[(i, j)]
                   for (ii, jj) in pairs if jj == j for i in [ii]]
            if col:
                prob += pulp.lpSum(col) <= d.max_up, f"UP{j}"

        # (C) Лимит оставшегося времени смены
        for j, d in enumerate(doctors):
            prebooked_h = (doc_prebooked_minutes or {}).get(d.id, 0.0) / 60.0
            remaining_h = max(0.0,
                (d.shift_end - self.now).total_seconds() / 3600.0 - prebooked_h
            )
            col = [studies[i].duration_hours * x[(i, j)]
                   for (ii, jj) in pairs if jj == j for i in [ii]]
            if col:
                prob += pulp.lpSum(col) <= remaining_h, f"TM{j}"
                self._log(
                    f"  Врач {d.name}: оставшееся время={remaining_h:.2f}ч "
                    f"(prebooked={prebooked_h:.2f}ч)"
                )

        # (D) Tardiness lower bound при назначении врачу j
        for (i, j) in pairs:
            c_ij = C.get((i, j), 0.0)
            prob += (
                T[i] >= c_ij - d_h[i] - BIG_M * (1 - x[(i, j)]),
                f"TD{i}_{j}"
            )

        # (E) Tardiness lower bound если исследование НЕ назначено
        for i in range(n):
            row = [x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]]
            if row:
                prob += (
                    T[i] >= C_free[i] - d_h[i] - BIG_M * pulp.lpSum(row),
                    f"TF{i}"
                )
            else:
                prob += T[i] >= C_free[i] - d_h[i], f"TF_nocompat{i}"

        # ── Решение ──────────────────────────────────────────────────
        try:
            solver = pulp.PULP_CBC_CMD(
                timeLimit=MIP_TIME_LIMIT,
                msg=0,
                gapRel=MIP_GAP_REL,
            )
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            obj    = pulp.value(prob.objective)
            n_assigned = sum(
                1 for i in range(n)
                if any((pulp.value(x[(i, j)]) or 0) > 0.5
                       for (ii, jj) in pairs if ii == i for j in [jj])
            )
            self._log(f"CBC: статус={status}, Z={obj:.2f}, назначено={n_assigned}/{n}")

            # Извлекаем лучшее найденное решение при ЛЮБОМ статусе
            # CBC может вернуть Infeasible/Undefined при time limit,
            # но при этом уже найти хорошее частичное решение.
            result: Dict[int, int] = {}
            for (i, j) in pairs:
                val = pulp.value(x[(i, j)])
                if val is not None and val > 0.5:
                    result[studies[i].id] = doctors[j].id

            if result:
                self._log(f"MIP назначил {len(result)} / {n} (статус: {status})")
                return result

            # Только если вообще ничего не назначено — жадный
            self._log(f"MIP: 0 назначений (статус={status}) → жадный fallback")
            return self.solve_greedy(studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes)

        except Exception as e:
            self._log(f"CBC ошибка: {e} → жадный fallback")
            return self.solve_greedy(studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes)


    # ── Sequencing + расчёт tardiness ───────────────────────────────

    def sequence(self, studies: List[StudyData]) -> List[StudyData]:
        return sorted(studies, key=lambda s: (
            {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
            s.deadline,
        ))

    def build_schedule(self, doctor: DoctorData, ordered: List[StudyData]) -> List[Dict]:
        results = []
        t = doctor.shift_start
        for s in ordered:
            finish    = t + timedelta(minutes=s.duration_minutes)
            tardiness = max(0.0, (finish - s.deadline).total_seconds() / 3600.0)
            results.append({
                "study": s,
                "completion_time": finish,
                "tardiness_hours": tardiness,
                "weighted_tardiness": tardiness * s.weight,
            })
            t = finish
        return results

    # ── Сохранение ───────────────────────────────────────────────────

    def save_to_db(self, assignment: Dict[int, int]) -> None:
        for study_id, doc_id in assignment.items():
            Study.objects.filter(id=study_id).update(
                diagnostician_id=doc_id, status="confirmed"
            )

    # ── Главный метод ────────────────────────────────────────────────

    def distribute(self, use_mip: bool = True) -> Dict:
        self._log("=" * 60)
        self._log("OFFLINE DISTRIBUTION SERVICE")
        self._log(f"Время: {self.now}")
        self._log("=" * 60)

        studies = self.load_studies()
        doctors = self.load_doctors()

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        # ── Разбиваем на CITO и остальные ───────────────────────────
        cito_studies   = [s for s in studies if s.priority == "cito"]
        other_studies  = [s for s in studies if s.priority != "cito"]
        self._log(f"CITO: {len(cito_studies)}, ASAP+normal: {len(other_studies)}")

        assignment: Dict[int, int] = {}

        # ══════════════════════════════════════════════════════════════
        # ЭТАП 1: CITO — назначаем ВСЕ БЕЗ ИСКЛЮЧЕНИЙ
        #
        # Правила:
        #   - Лимит УП игнорируется (врач может превысить норму)
        #   - Лимит времени смены игнорируется (сверхурочно)
        #   - Выбираем врача с наименьшей текущей нагрузкой по времени
        #   - Если совместимых врачей нет — логируем как КРИТИЧЕСКУЮ ошибку
        # ══════════════════════════════════════════════════════════════
        if cito_studies:
            cito_assignment = self._assign_cito_mandatory(cito_studies, doctors)
            assignment.update(cito_assignment)
            unassigned_cito = [s for s in cito_studies if s.id not in cito_assignment]
            if unassigned_cito:
                self._log(
                    f"КРИТИЧНО: {len(unassigned_cito)} CITO без совместимого врача! "
                    f"Проверьте модальности врачей."
                )
                for s in unassigned_cito:
                    self._log(
                        f"  CITO БЕЗ ВРАЧА: id={s.id} {s.research_number} "
                        f"modality={s.modality}"
                    )

        # ══════════════════════════════════════════════════════════════
        # ЭТАП 2: ASAP + normal — назначаем в оставшееся время
        #
        # Здесь уже действуют ограничения по времени и УП.
        # Время врача уже частично занято CITO.
        # ══════════════════════════════════════════════════════════════
        if other_studies:
            # Пересчитываем занятое время врачей после CITO
            doc_used: Dict[int, float] = {d.id: 0.0 for d in doctors}
            for sid, did in assignment.items():
                s = next(x for x in studies if x.id == sid)
                doc_used[did] += s.duration_minutes

            if use_mip:
                other_assignment = self.solve_mip(
                    other_studies, doctors,
                    doc_prebooked_minutes=doc_used,
                )
            else:
                other_assignment = self.solve_greedy(
                    other_studies, doctors,
                    doc_prebooked_minutes=doc_used,
                )
            assignment.update(other_assignment)

        # ── Этап 3: sequencing и расчёт tardiness ───────────────────
        study_map  = {s.id: s for s in studies}
        doctor_map = {d.id: d for d in doctors}

        for sid, did in assignment.items():
            d = doctor_map[did]
            d.assigned_ids.append(sid)
            d.used_up      += study_map[sid].up_value
            d.used_minutes += study_map[sid].duration_minutes

        all_assignments   = []
        total_tardiness   = 0.0
        total_w_tardiness = 0.0
        pstats = {"cito": 0, "asap": 0, "normal": 0}

        for d in doctors:
            if not d.assigned_ids:
                continue
            ordered  = self.sequence([study_map[sid] for sid in d.assigned_ids])
            schedule = self.build_schedule(d, ordered)
            for entry in schedule:
                s   = entry["study"]
                tar = entry["tardiness_hours"]
                wt  = entry["weighted_tardiness"]
                total_tardiness   += tar
                total_w_tardiness += wt
                pstats[s.priority] = pstats.get(s.priority, 0) + 1
                all_assignments.append({
                    "study_id":        s.id,
                    "study_number":    s.research_number,
                    "doctor_id":       d.id,
                    "doctor_name":     d.name,
                    "priority":        s.priority,
                    "deadline":        s.deadline.isoformat(),
                    "completion_time": entry["completion_time"].isoformat(),
                    "tardiness_hours": round(tar, 2),
                    "up_value":        s.up_value,
                    "is_overdue":      s.deadline < self.now,
                })

        self.save_to_db(assignment)

        n_asgn = len(assignment)
        z = round(total_w_tardiness, 3)
        n_cito_assigned = sum(1 for s in cito_studies if s.id in assignment)
        self._log(
            f"Итого: {n_asgn}/{len(studies)} | "
            f"CITO: {n_cito_assigned}/{len(cito_studies)} | Z={z}"
        )

        return {
            "assigned":                 n_asgn,
            "unassigned":               len(studies) - n_asgn,
            "cito_assigned":            n_cito_assigned,
            "cito_total":               len(cito_studies),
            "total_tardiness":          round(total_tardiness, 2),
            "total_weighted_tardiness": z,
            "avg_tardiness":            round(total_tardiness / n_asgn, 2) if n_asgn else 0,
            "assignments":              all_assignments,
            "doctor_stats": [
                {
                    "doctor_id":        d.id,
                    "doctor_name":      d.name,
                    "assigned_studies": len(d.assigned_ids),
                    "total_up":         round(d.used_up, 3),
                    "max_up":           round(d.max_up, 3),
                    "load_percent":     round(d.used_up / d.max_up * 100, 1) if d.max_up else 0,
                    "remaining_up":     round(d.free_up, 3),
                }
                for d in doctors
            ],
            "priority_stats":    pstats,
            "objective_function": f"MIN Z = Σ wᵢ×Tᵢ (Pm|rⱼ|ΣwⱼTⱼ) = {z}",
            "message": (
                f"Оффлайн: назначено {n_asgn} из {len(studies)}. "
                f"CITO: {n_cito_assigned}/{len(cito_studies)}. Z={z}"
            ),
            "_debug": self._debug,
        }

    def _assign_cito_mandatory(
        self,
        cito_studies: List[StudyData],
        doctors: List[DoctorData],
    ) -> Dict[int, int]:
        """
        Назначает ВСЕ CITO через MIP (без лимитов УП и времени смены).
        Цель: минимизировать суммарное взвешенное запаздывание CITO,
        распределив их максимально равномерно по совместимым врачам.

        Если PuLP недоступен — fallback на жадный (наименее загруженный врач).
        """
        self._log(f"CITO MIP: {len(cito_studies)} исследований...")

        try:
            import pulp
        except ImportError:
            self._log("PuLP недоступен → жадный CITO fallback")
            return self._assign_cito_greedy(cito_studies, doctors)

        n = len(cito_studies)
        m = len(doctors)

        # Совместимые пары (без лимитов — CITO идут сверхурочно)
        pairs = [
            (i, j)
            for i, s in enumerate(cito_studies)
            for j, d in enumerate(doctors)
            if self._modality_ok(s.modality, d.modality)
        ]
        if not pairs:
            self._log("CITO: нет совместимых пар → жадный fallback")
            return self._assign_cito_greedy(cito_studies, doctors)

        sidx = {s.id: i for i, s in enumerate(cito_studies)}

        # Оценки C[i,j] от now (CITO назначаются немедленно с текущего момента)
        C: Dict[Tuple[int, int], float] = {}
        for j, d in enumerate(doctors):
            acc = 0.0
            j_st = sorted(
                [cito_studies[i] for (ii, jj) in pairs if jj == j for i in [ii]],
                key=lambda s: s.deadline,
            )
            for s in j_st:
                acc += s.duration_hours
                C[(sidx[s.id], j)] = acc  # часов от now

        d_h = [(s.deadline - self.now).total_seconds() / 3600.0 for s in cito_studies]

        max_overdue = max((max(0.0, -dh) for dh in d_h), default=0.0)
        MAX_T = max(d.shift_hours for d in doctors) + max_overdue + 10.0
        BIG_M = MAX_T + 1.0

        prob = pulp.LpProblem("CITO_PMWT", pulp.LpMinimize)

        x = {(i, j): pulp.LpVariable(f"cx_{i}_{j}", cat="Binary")
             for (i, j) in pairs}
        T = {i: pulp.LpVariable(f"cT_{i}", lowBound=0, upBound=MAX_T)
             for i in range(n)}

        # Цель: MIN Σ wᵢ×Tᵢ (CITO уже имеют weight=100×overdue_multiplier)
        prob += pulp.lpSum(cito_studies[i].weight * T[i] for i in range(n))

        # Каждое CITO — ровно 1 врачу (обязательно)
        for i in range(n):
            row = [x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]]
            if row:
                prob += pulp.lpSum(row) == 1, f"CA{i}"

        # Tardiness lower bound
        for (i, j) in pairs:
            c_ij = C.get((i, j), 0.0)
            prob += T[i] >= c_ij - d_h[i] - BIG_M * (1 - x[(i, j)]), f"CTD{i}_{j}"

        try:
            solver = pulp.PULP_CBC_CMD(timeLimit=30, msg=0, gapRel=0.02)
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            self._log(f"  CITO CBC: статус={status}, Z={pulp.value(prob.objective):.2f}")

            if prob.status in (1, -2):
                result = {
                    cito_studies[i].id: doctors[j].id
                    for (i, j) in pairs
                    if (pulp.value(x[(i, j)]) or 0) > 0.5
                }
                self._log(f"  CITO MIP назначил: {len(result)}/{n}")
                for sid, did in result.items():
                    s = next(s for s in cito_studies if s.id == sid)
                    d = next(d for d in doctors if d.id == did)
                    mark = " [ПРОСРОЧЕН]" if s.deadline < self.now else ""
                    self._log(f"    CITO id={sid} → {d.name}{mark}")
                return result
        except Exception as e:
            self._log(f"  CITO CBC ошибка: {e} → жадный fallback")

        return self._assign_cito_greedy(cito_studies, doctors)

    def _assign_cito_greedy(
        self,
        cito_studies: List[StudyData],
        doctors: List[DoctorData],
    ) -> Dict[int, int]:
        """Жадный fallback для CITO: наименее загруженный совместимый врач."""
        sorted_cito = sorted(cito_studies, key=lambda s: s.deadline)
        doc_min: Dict[int, float] = {d.id: 0.0 for d in doctors}
        assignment: Dict[int, int] = {}
        for s in sorted_cito:
            compatible = [d for d in doctors if self._modality_ok(s.modality, d.modality)]
            if not compatible:
                self._log(f"  CITO id={s.id}: нет совместимого врача для {s.modality}")
                continue
            best = min(compatible, key=lambda d: doc_min[d.id])
            assignment[s.id] = best.id
            doc_min[best.id] += s.duration_minutes
            mark = " [ПРОСРОЧЕН]" if s.deadline < self.now else ""
            self._log(f"  CITO id={s.id} → {best.name}{mark}")
        self._log(f"  CITO жадный назначил: {len(assignment)}/{len(cito_studies)}")
        return assignment


    def _empty(self, message: str, studies: List = None) -> Dict:
        self._log(f"ПУСТО: {message}")
        return {
            "assigned": 0, "unassigned": len(studies or []),
            "total_tardiness": 0.0, "total_weighted_tardiness": 0.0,
            "avg_tardiness": 0, "assignments": [], "doctor_stats": [],
            "priority_stats": {"cito": 0, "asap": 0, "normal": 0},
            "objective_function": "Z = 0",
            "message": message,
            "_debug": self._debug,
        }


# ==============================================================================
# ТОЧКА ВХОДА
# ==============================================================================

def distribute_studies() -> Dict:
    service = DistributionService()
    return service.distribute(use_mip=True)


