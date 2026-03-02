"""
Сервис оффлайн-распределения исследований по врачам.

Постановка задачи: Parallel Machine Weighted Tardiness (PMWT)
Цель: MIN Z = Σᵢ wᵢ × Tᵢ, где Tᵢ = max(0, Cᵢ - dᵢ)

Реализация:
  - Основной метод: MIP через PuLP + CBC (pip install pulp)
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

MIP_TIME_LIMIT = 120
MIP_GAP_REL    = 0.05


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
            deadline = created + timedelta(hours=DEADLINE_HOURS.get(priority, 72))
            result.append(StudyData(
                id=s.id,
                research_number=s.research_number,
                priority=priority,
                created_at=created,
                modality=parse_modalities(s.study_type.modality if s.study_type else ""),
                up_value=self._get_up(s),
                duration_minutes=self._get_duration(s),
                deadline=deadline,
                weight=PRIORITY_WEIGHTS.get(priority, 1.0),
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
    ) -> Dict[int, int]:
        label = "Жадный (без лимита УП)" if ignore_up_limit else "Жадный WSPT"
        self._log(f"Запуск: {label}...")

        sorted_s = sorted(studies, key=lambda s: (
            {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
            -(s.weight / s.duration_hours) if s.duration_hours > 0 else 0,
            s.deadline,
        ))

        doc_up:  Dict[int, float] = {d.id: 0.0 for d in doctors}
        doc_min: Dict[int, float] = {d.id: 0.0 for d in doctors}

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
    # Целевая функция:
    #   MIN  P × Σᵢ(1 - yᵢ)  +  Σᵢ wᵢ × Tᵢ
    #
    # где yᵢ = Σⱼ x[i,j] ∈ {0,1} — «исследование i назначено»,
    # P — штраф за ненаначение (P >> max возможного tardiness).
    #
    # Первое слагаемое заставляет CBC МАКСИМИЗИРОВАТЬ число назначений,
    # второе — минимизировать взвешенное опоздание.
    # Решение x=0 для всех i больше не является оптимальным:
    # оно даёт Z = P × n, тогда как любое допустимое назначение даёт Z < P × n.

    def solve_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
    ) -> Dict[int, int]:
        try:
            import pulp
        except ImportError:
            self._log("PuLP не установлен → жадный (pip install pulp для MIP)")
            return self.solve_greedy(studies, doctors)

        n, m = len(studies), len(doctors)
        self._log(f"MIP: {n} × {m}")

        # ── Совместимые пары (i, j) ──────────────────────────────────
        pairs = [
            (i, j)
            for i, s in enumerate(studies)
            for j, d in enumerate(doctors)
            if self._modality_ok(s.modality, d.modality)
        ]
        self._log(f"  Совместимых пар: {len(pairs)}")

        if not pairs:
            self._log("  Нет совместимых пар → 0 назначений")
            return {}

        # ── EDD-оценки completion time Cᵢⱼ (часов от self.now) ──────
        sidx: Dict[int, int] = {s.id: i for i, s in enumerate(studies)}
        C: Dict[Tuple[int, int], float] = {}
        for j, d in enumerate(doctors):
            j_st = sorted(
                [studies[i] for (ii, jj) in pairs if jj == j for i in [ii]],
                key=lambda s: s.deadline,
            )
            acc = 0.0
            for s in j_st:
                acc += s.duration_hours
                C[(sidx[s.id], j)] = (
                    d.shift_start + timedelta(hours=acc) - self.now
                ).total_seconds() / 3600.0

        d_h = [(s.deadline - self.now).total_seconds() / 3600.0 for s in studies]

        # ── Big-M для линеаризации tardiness ────────────────────────
        # BIG_M должно быть >= max возможного опоздания
        max_C   = max((abs(v) for v in C.values()), default=200.0)
        max_d   = max((abs(v) for v in d_h), default=200.0)
        BIG_M   = max_C + max_d + 100.0

        # ── Штраф за ненаначение P >> BIG_M × Σwᵢ ──────────────────
        # Это гарантирует что "назначить всё возможное" всегда лучше
        # чем "ничего не назначить и иметь маленький tardiness".
        total_w = sum(s.weight for s in studies)
        PENALTY = BIG_M * total_w * 10.0
        self._log(f"  BIG_M={BIG_M:.1f}, PENALTY={PENALTY:.1f}")

        # ── Переменные ───────────────────────────────────────────────
        prob = pulp.LpProblem("PMWT_MaxAssign", pulp.LpMinimize)
        x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary") for (i, j) in pairs}
        T = {i: pulp.LpVariable(f"T_{i}", lowBound=0) for i in range(n)}
        # yᵢ = 1 если исследование i назначено хоть кому-то
        y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in range(n)}

        # ── Целевая функция ──────────────────────────────────────────
        # MIN  P × Σ(1 - yᵢ)  +  Σ wᵢ × Tᵢ
        # ≡   -P × Σyᵢ  +  Σ wᵢ × Tᵢ  +  P×n  (константа не влияет на оптимум)
        prob += (
            PENALTY * pulp.lpSum(1 - y[i] for i in range(n))
            + pulp.lpSum(studies[i].weight * T[i] for i in range(n))
        ), "Obj"

        # ── Ограничения ──────────────────────────────────────────────

        # (A) Каждое исследование — не более 1 врачу
        for i in range(n):
            row = [x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]]
            if row:
                prob += pulp.lpSum(row) <= 1, f"A{i}"
            # yᵢ ≤ Σⱼ x[i,j]  (если никуда не назначено — yᵢ = 0)
            if row:
                prob += y[i] <= pulp.lpSum(row), f"Y_ub{i}"
            # yᵢ ≥ x[i,j]  для каждого j  (если назначено — yᵢ = 1)
            for (ii, jj) in pairs:
                if ii == i:
                    prob += y[i] >= x[(i, jj)], f"Y_lb{i}_{jj}"

        # (B) Лимит УП врача
        for j, d in enumerate(doctors):
            col = [studies[i].up_value * x[(i, j)] for (ii, jj) in pairs if jj == j for i in [ii]]
            if col:
                prob += pulp.lpSum(col) <= d.max_up, f"UP{j}"

        # (C) Лимит времени смены
        for j, d in enumerate(doctors):
            col = [studies[i].duration_hours * x[(i, j)] for (ii, jj) in pairs if jj == j for i in [ii]]
            if col:
                prob += pulp.lpSum(col) <= d.shift_hours, f"TM{j}"

        # (D) Tardiness lower bound (Big-M линеаризация)
        # T[i] ≥ C[i,j] - d[i] - BIG_M × (1 - x[i,j])
        for (i, j) in pairs:
            c_ij = C.get((i, j), 0.0)
            prob += T[i] >= c_ij - d_h[i] - BIG_M * (1 - x[(i, j)]), f"TD{i}_{j}"

        # ── Решение ──────────────────────────────────────────────────
        try:
            solver = pulp.PULP_CBC_CMD(timeLimit=MIP_TIME_LIMIT, msg=0, gapRel=MIP_GAP_REL)
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            obj    = pulp.value(prob.objective)
            n_assigned_mip = sum(
                1 for i in range(n) if (pulp.value(y[i]) or 0) > 0.5
            )
            self._log(f"CBC: статус={status}, Z={obj:.2f}, назначено={n_assigned_mip}")

            # Извлекаем назначения
            result: Dict[int, int] = {
                studies[i].id: doctors[j].id
                for (i, j) in pairs
                if (pulp.value(x[(i, j)]) or 0) > 0.5
            }
            self._log(f"MIP назначил {len(result)} / {n}")

            if len(result) == 0 and prob.status != -1:
                # CBC дал Optimal но x=0 — значит PENALTY слишком мал
                # или n=0. Логируем и возвращаем пустой dict (не fallback).
                self._log(
                    "ВНИМАНИЕ: MIP вернул 0 назначений при Optimal. "
                    "Все исследования вне возможностей врачей (модальность/время/УП)."
                )

            return result

        except Exception as e:
            self._log(f"CBC ошибка: {e}")
            return {}

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

        avg_dur = sum(s.duration_minutes for s in studies) / len(studies)
        total_time_supply = sum(d.shift_hours * 60 for d in doctors)
        self._log(f"Среднее время на исследование: {avg_dur:.1f} мин")
        self._log(f"Суммарное время смен: {total_time_supply:.0f} мин")
        self._log(f"Теор. макс. назначений: ~{int(total_time_supply / avg_dur)}")

        # ── Этап 1: назначение ───────────────────────────────────────
        # MIP сам решает, сколько исследований возможно назначить.
        # Fallback-а нет — если назначений 0, значит ресурсов нет.
        if use_mip:
            assignment = self.solve_mip(studies, doctors)
        else:
            assignment = self.solve_greedy(studies, doctors)

        # ── Этап 2: sequencing ───────────────────────────────────────
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
                })

        self.save_to_db(assignment)

        n_asgn = len(assignment)
        z = round(total_w_tardiness, 3)
        self._log(f"Итого: {n_asgn}/{len(studies)}, Z={z}")

        return {
            "assigned":                 n_asgn,
            "unassigned":               len(studies) - n_asgn,
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
            "objective_function": f"MIN Z = Σ(wᵢ × Tᵢ) = {z}",
            "message": f"Оффлайн: назначено {n_asgn} из {len(studies)} исследований. Z = {z}",
            "_debug": self._debug,
        }

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