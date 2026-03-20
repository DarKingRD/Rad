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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from django.utils import timezone

from api.models import Schedule, Study


logger = logging.getLogger(__name__)


# ==============================================================================
# МАППИНГ МОДАЛЬНОСТЕЙ
# ==============================================================================

MODALITY_ALIASES: Dict[str, str] = {
    "KT": "CT",
    "КТ": "CT",
    "COMPUTED_TOMOGRAPHY": "CT",
    "MRT": "MRI",
    "МРТ": "MRI",
    "MAGNETIC_RESONANCE": "MRI",
    "RENTGEN": "XRAY",
    "РЕНТГЕН": "XRAY",
    "X_RAY": "XRAY",
    "US": "US",
    "УЗИ": "US",
    "ULTRASOUND": "US",
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

PRIORITY_WEIGHTS = {"cito": 36.0, "asap": 3.0, "normal": 1.0}
DEADLINE_HOURS = {"cito": 2, "asap": 24, "normal": 72}

# Рекомендованное время описания (мин) из Положения об оплате
MODALITY_DURATION_MINUTES = {
    "XRAY": 5,
    "CT": 15,
    "CT_CON": 25,
    "MRI": 20,
    "MRI_CON": 30,
    "MAMMO": 6,
    "FLUORO": 4,
    "ECG": 4,
    "HOLTER": 25,
    "EEG": 20,
    "US": 10,
}

MIP_TIME_LIMIT = 300  # 5 минут на одну MIP-задачу
MIP_GAP_REL = 0.01  # 1% gap — хорошее качество


# ==============================================================================
# СТРУКТУРЫ ДАННЫХ
# ==============================================================================


@dataclass
class StudyData:
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
    break_start: Optional[datetime] = None
    break_end: Optional[datetime] = None
    assigned_ids: List[str] = field(default_factory=list)
    used_up: float = 0.0
    used_minutes: float = 0.0

    @property
    def break_minutes(self) -> float:
        """Длительность перерыва в минутах (0 если не задан или уже прошёл)."""
        if self.break_start and self.break_end and self.break_end > self.break_start:
            return (self.break_end - self.break_start).total_seconds() / 60.0
        return 0.0

    @property
    def shift_hours(self) -> float:
        """Рабочее время смены за вычетом перерыва (в часах)."""
        gross = (self.shift_end - self.shift_start).total_seconds() / 3600.0
        return max(0.0, gross - self.break_minutes / 60.0)

    @property
    def free_up(self) -> float:
        return max(0.0, self.max_up - self.used_up)


# ==============================================================================
# СЕРВИС
# ==============================================================================


class DistributionService:
    def __init__(
        self,
        target_date: Optional[datetime] = None,
        preview_mode: bool = False,
    ):
        self.now = timezone.now()
        self.target_date = target_date or self.now.date()
        self.preview_mode = preview_mode
        self._debug: List[str] = []

    def set_preview_mode(self, preview: bool = True):
        "Включить/выключить режим предпросмотра (не сохранять назначения)"
        self.preview_mode = preview

    def _log(self, msg: str):
        logger.info(msg)
        self._debug.append(msg)

    def _make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt if timezone.is_aware(dt) else timezone.make_aware(dt)

    def _modality_ok(self, study_mods: Set[str], doc_mods: Set[str]) -> bool:
        if not doc_mods:
            return False
        if not study_mods:
            return True
        return bool(study_mods & doc_mods)

    def _align_to_work_time(self, doctor: DoctorData, dt: datetime) -> datetime:
        if dt < doctor.shift_start:
            dt = doctor.shift_start
        if (
            doctor.break_start
            and doctor.break_end
            and doctor.break_start <= dt < doctor.break_end
        ):
            dt = doctor.break_end
        return dt

    def _work_minutes_between(
        self, doctor: DoctorData, start: datetime, end: datetime
    ) -> float:
        start = max(start, doctor.shift_start)
        end = min(end, doctor.shift_end)
        if end <= start:
            return 0.0

        total = (end - start).total_seconds() / 60.0
        if doctor.break_start and doctor.break_end:
            ov_start = max(start, doctor.break_start)
            ov_end = min(end, doctor.break_end)
            if ov_end > ov_start:
                total -= (ov_end - ov_start).total_seconds() / 60.0
        return max(0.0, total)

    def _remaining_work_minutes(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> float:
        effective_start = max(doctor.shift_start, self.now)
        available = self._work_minutes_between(doctor, effective_start, doctor.shift_end)
        return max(0.0, available - prebooked_minutes)

    def _add_work_minutes(
        self, doctor: DoctorData, start: datetime, minutes: float
    ) -> datetime:
        remaining = max(0.0, float(minutes))
        current = self._align_to_work_time(doctor, start)

        while remaining > 1e-9:
            current = self._align_to_work_time(doctor, current)

            if current >= doctor.shift_end:
                return current + timedelta(minutes=remaining)

            next_stop = doctor.shift_end
            if doctor.break_start and doctor.break_end and current < doctor.break_start:
                next_stop = min(next_stop, doctor.break_start)

            available = max(0.0, (next_stop - current).total_seconds() / 60.0)
            if remaining <= available + 1e-9:
                return current + timedelta(minutes=remaining)

            remaining -= available
            current = next_stop

            if (
                doctor.break_start
                and doctor.break_end
                and current == doctor.break_start
            ):
                current = doctor.break_end

        return current

    def _completion_after_load(
        self, doctor: DoctorData, total_minutes_from_now: float
    ) -> datetime:
        start = max(doctor.shift_start, self.now)
        return self._add_work_minutes(doctor, start, total_minutes_from_now)

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

    def load_studies(
        self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
    ) -> List[StudyData]:
        qs = Study.objects.filter(diagnostician__isnull=True).select_related(
            "study_type"
        )

        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lt=date_to)

        result = []
        for s in qs:
            priority = s.priority or "normal"
            created = self._make_aware(s.created_at) or self.now

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

            result.append(
                StudyData(
                    research_number=s.research_number,
                    priority=priority,
                    created_at=created,
                    modality=parse_modalities(
                        s.study_type.modality if s.study_type else ""
                    ),
                    up_value=self._get_up(s),
                    duration_minutes=self._get_duration(s),
                    deadline=deadline,
                    weight=weight,
                )
            )

        self._log(f"Исследований без назначения: {len(result)}")
        if result:
            sample = result[:3]
            for s in sample:
                self._log(
                    f"  Пример: research_number={s.research_number}, priority={s.priority}, "
                    f"modality={s.modality}, up={s.up_value}, dur={s.duration_minutes}мин"
                )
        return result

    def load_doctors(self) -> List[DoctorData]:
        target = self.target_date
        schedules = Schedule.objects.filter(
            work_date=target, is_day_off=0
        ).select_related("doctor")

        self._log(f"Расписаний на {target}: {schedules.count()}")

        result = []
        for sch in schedules:
            doc = sch.doctor
            if not doc or not doc.is_active:
                self._log(
                    f"  Пропуск: врач {getattr(doc, 'id', '?')}, active={getattr(doc, 'is_active', '?')}"
                )
                continue

            max_up = float(doc.max_up_per_day or 50)

            if sch.time_start and sch.time_end:
                s_start = timezone.make_aware(datetime.combine(target, sch.time_start))
                s_end = timezone.make_aware(datetime.combine(target, sch.time_end))
            else:
                s_start = self.now.replace(hour=9, minute=0, second=0, microsecond=0)
                s_end = self.now.replace(hour=17, minute=0, second=0, microsecond=0)

            # Перерыв (обед)
            b_start = (
                timezone.make_aware(datetime.combine(target, sch.break_start))
                if sch.break_start
                else None
            )
            b_end = (
                timezone.make_aware(datetime.combine(target, sch.break_end))
                if sch.break_end
                else None
            )

            break_h = (
                (b_end - b_start).total_seconds() / 3600.0 if b_start and b_end else 0.0
            )
            shift_h = (s_end - s_start).total_seconds() / 3600.0
            mods = parse_modalities(doc.modality)

            self._log(
                f"  Врач {doc.fio_alias} (id={doc.id}): "
                f"max_up={max_up}, смена={shift_h:.1f}ч, "
                f"перерыв={break_h * 60:.0f}мин, эфф.время={shift_h - break_h:.1f}ч, мод={list(mods)}"
            )

            result.append(
                DoctorData(
                    id=doc.id,
                    name=doc.fio_alias or f"Врач {doc.id}",
                    modality=mods,
                    max_up=max_up,
                    shift_start=s_start,
                    shift_end=s_end,
                    break_start=b_start,
                    break_end=b_end,
                )
            )

        self._log(f"Врачей загружено: {len(result)}")
        return result

    # ── Жадный WSPT (fallback) ───────────────────────────

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[str, int]:
        self._log("Запуск: Жадный WSPT...")

        sorted_s = sorted(
            studies,
            key=lambda s: (
                {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
                -(s.weight / s.duration_hours) if s.duration_hours > 0 else 0,
                s.deadline,
            ),
        )

        doc_up: Dict[int, float] = {d.id: 0.0 for d in doctors}
        doc_min: Dict[int, float] = {
            d.id: (doc_prebooked_minutes or {}).get(d.id, 0.0) for d in doctors
        }

        assignment: Dict[str, int] = {}

        for s in sorted_s:
            best_id = None
            best_score = float("inf")

            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if doc_up[d.id] + s.up_value > d.max_up + 1e-9:
                    continue
                effective_start = max(d.shift_start, self.now)
                gross_min = max(
                    0.0, (d.shift_end - effective_start).total_seconds() / 60
                )
                # Перерыв, пересекающийся с остатком смены
                break_overlap_min = 0.0
                if d.break_start and d.break_end:
                    ov_start = max(effective_start, d.break_start)
                    ov_end = min(d.shift_end, d.break_end)
                    if ov_end > ov_start:
                        break_overlap_min = (ov_end - ov_start).total_seconds() / 60
                remaining_minutes = max(
                    0.0, gross_min - break_overlap_min - doc_min[d.id]
                )
                if s.duration_minutes > remaining_minutes + 1e-9:
                    continue
                score = (
                    doc_min[d.id] / (d.shift_hours * 60) if d.shift_hours > 0 else 1.0
                )
                if score < best_score:
                    best_score = score
                    best_id = d.id

            if best_id is not None:
                assignment[s.research_number] = best_id
                doc_up[best_id] += s.up_value
                doc_min[best_id] += s.duration_minutes

        self._log(f"Жадный WSPT: назначено {len(assignment)} / {len(studies)}")

        # Диагностика: сколько просроченных CITO назначено vs пропущено
        overdue_cito = [
            s for s in studies if s.priority == "cito" and s.deadline < self.now
        ]
        assigned_overdue = [s for s in overdue_cito if s.research_number in assignment]
        skipped_overdue = [
            s for s in overdue_cito if s.research_number not in assignment
        ]
        if overdue_cito:
            self._log(
                f"  Просроченных CITO: {len(overdue_cito)} | "
                f"назначено: {len(assigned_overdue)} | "
                f"пропущено: {len(skipped_overdue)}"
            )

        overdue_asap = [
            s for s in studies if s.priority == "asap" and s.deadline < self.now
        ]
        assigned_asap = [s for s in overdue_asap if s.research_number in assignment]
        skipped_asap = [s for s in overdue_asap if s.research_number not in assignment]

        if overdue_asap:
            self._log(
                f"  Просроченных ASAP: {len(overdue_asap)} | "
                f"назначено: {len(assigned_asap)} | "
                f"пропущено: {len(skipped_asap)}"
            )

        overdue_normal = [
            s for s in studies if s.priority == "normal" and s.deadline < self.now
        ]
        assigned_normal = [s for s in overdue_normal if s.research_number in assignment]
        skipped_normal = [
            s for s in overdue_normal if s.research_number not in assignment
        ]

        if overdue_normal:
            self._log(
                f"  Просроченных normal: {len(overdue_normal)} | "
                f"назначено: {len(assigned_normal)} | "
                f"пропущено: {len(skipped_normal)}"
            )

        for d in doctors:
            cnt = sum(1 for did in assignment.values() if did == d.id)
            up = doc_up[d.id]
            mins = doc_min[d.id]
            self._log(
                f"  {d.name}: {cnt} исслед., {up:.2f}/{d.max_up} УП, "
                f"{mins:.0f}/{d.shift_hours * 60:.0f} мин"
            )
        return assignment

    # ── MIP ─────────────────────────────────────────────────────────

    def solve_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[str, int]:
        try:
            import pulp
        except ImportError:
            self._log("PuLP не установлен → жадный (pip install pulp для MIP)")
            return self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )

        self._log(f"MIP без батчинга: {len(studies)} исследований в одной задаче")
        return self._solve_mip_single(studies, doctors, doc_prebooked_minutes)

    def _solve_mip_single(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Dict[str, int]:
        import pulp

        n, m = len(studies), len(doctors)
        self._log(f"MIP: {n} × {m}")

        pairs = [
            (i, j)
            for i, s in enumerate(studies)
            for j, d in enumerate(doctors)
            if self._modality_ok(s.modality, d.modality)
        ]
        self._log(f"  Совместимых пар: {len(pairs)}")
        if not pairs:
            self._log("  Нет совместимых пар → жадный fallback")
            return self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )

        d_h = [(s.deadline - self.now).total_seconds() / 3600.0 for s in studies]
        remaining_h_by_doctor: Dict[int, float] = {}
        assign_cost: Dict[Tuple[int, int], float] = {}

        for j, d in enumerate(doctors):
            prebooked_minutes = (doc_prebooked_minutes or {}).get(d.id, 0.0)
            remaining_minutes = self._remaining_work_minutes(d, prebooked_minutes)
            remaining_h = remaining_minutes / 60.0
            remaining_h_by_doctor[j] = remaining_h

            self._log(
                f"  Врач {d.name}: оставшееся время={remaining_h:.2f}ч "
                f"(prebooked={prebooked_minutes / 60.0:.2f}ч)"
            )

            for i, _ in enumerate(studies):
                if (i, j) not in pairs:
                    continue

                finish_dt = self._completion_after_load(
                    d, prebooked_minutes + studies[i].duration_minutes
                )
                completion_h = max(
                    0.0, (finish_dt - self.now).total_seconds() / 3600.0
                )
                tard_lb = max(0.0, completion_h - d_h[i])

                load_penalty = 0.0
                if remaining_h > 1e-9:
                    load_penalty = studies[i].duration_hours / remaining_h

                assign_cost[(i, j)] = studies[i].weight * tard_lb + 0.01 * load_penalty

        horizon_h = max(
            (d.shift_end - self.now).total_seconds() / 3600.0 for d in doctors
        )
        unassigned_cost = {
            i: studies[i].weight
            * (max(0.0, -d_h[i]) + horizon_h + studies[i].duration_hours)
            + 1.0
            for i in range(n)
        }

        prob = pulp.LpProblem("PMWT_assignment_proxy", pulp.LpMinimize)

        x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary") for (i, j) in pairs}

        prob += (
            pulp.lpSum(assign_cost[(i, j)] * x[(i, j)] for (i, j) in pairs)
            + pulp.lpSum(
                unassigned_cost[i]
                * (
                    1
                    - pulp.lpSum(
                        x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]
                    )
                )
                for i in range(n)
            )
        ), "Obj"

        for i in range(n):
            row = [x[(i, j)] for (ii, jj) in pairs if ii == i for j in [jj]]
            if row:
                prob += pulp.lpSum(row) <= 1, f"A{i}"

        for j, d in enumerate(doctors):
            col_up = [
                studies[i].up_value * x[(i, j)]
                for (ii, jj) in pairs
                if jj == j
                for i in [ii]
            ]
            if col_up:
                prob += pulp.lpSum(col_up) <= d.max_up, f"UP{j}"

            col_time = [
                studies[i].duration_hours * x[(i, j)]
                for (ii, jj) in pairs
                if jj == j
                for i in [ii]
            ]
            if col_time:
                prob += pulp.lpSum(col_time) <= remaining_h_by_doctor[j], f"TM{j}"

        try:
            solver = pulp.PULP_CBC_CMD(
                timeLimit=MIP_TIME_LIMIT,
                msg=0,
                gapRel=MIP_GAP_REL,
            )
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            obj = pulp.value(prob.objective)
            n_assigned = sum(
                1
                for i in range(n)
                if any(
                    (pulp.value(x[(i, j)]) or 0) > 0.5
                    for (ii, jj) in pairs
                    if ii == i
                    for j in [jj]
                )
            )
            self._log(
                f"CBC: статус={status}, proxy_obj={obj:.2f}, назначено={n_assigned}/{n}"
            )

            result: Dict[str, int] = {}
            for i, j in pairs:
                val = pulp.value(x[(i, j)])
                if val is not None and val > 0.5:
                    result[studies[i].research_number] = doctors[j].id

            if result:
                self._log(f"MIP назначил {len(result)} / {n} (статус: {status})")
                return result

            self._log(f"MIP: 0 назначений (статус={status}) → жадный fallback")
            return self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )

        except Exception as e:
            self._log(f"CBC ошибка: {e} → жадный fallback")
            return self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )

    # ── Sequencing + расчёт tardiness ───────────────────────────────

    def sequence(self, studies: List[StudyData]) -> List[StudyData]:
        return sorted(
            studies,
            key=lambda s: (
                {"cito": 0, "asap": 1, "normal": 2}.get(s.priority, 2),
                s.deadline,
            ),
        )

    def build_schedule(
        self, doctor: DoctorData, ordered: List[StudyData]
    ) -> List[Dict]:
        results = []
        t = self._align_to_work_time(doctor, max(doctor.shift_start, self.now))
        for s in ordered:
            finish = self._add_work_minutes(doctor, t, s.duration_minutes)
            tardiness = max(0.0, (finish - s.deadline).total_seconds() / 3600.0)
            results.append(
                {
                    "study": s,
                    "completion_time": finish,
                    "tardiness_hours": tardiness,
                    "weighted_tardiness": tardiness * s.weight,
                }
            )
            t = finish
        return results

    # ── Сохранение ───────────────────────────────────────────────────

    def save_to_db(self, assignment: Dict[str, int]) -> None:
        if self.preview_mode:
            self._log("Режим предпросмотра - сохранение пропущено")
            return

        for study_id, doc_id in assignment.items():
            Study.objects.filter(research_number=study_id).update(
                diagnostician_id=doc_id,
                status="confirmed",
                planned_at=self.now,  # или target_date
            )

    # ── Главный метод ────────────────────────────────────────────────

    def distribute(
        self,
        use_mip: bool = True,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict:
        self._log("=" * 60)
        self._log("OFFLINE DISTRIBUTION SERVICE")
        self._log(f"Время: {self.now}")
        self._log(f"Целевая дата: {self.target_date}")
        self._log(f"Режим предпросмотра: {self.preview_mode}")
        self._log("=" * 60)

        doctors = self.load_doctors()

        if doctors:
            min_start = min(d.shift_start for d in doctors)
            if self.now > min_start:
                self._log(
                    f"Текущее время {self.now} после начала смены {min_start}, используем min_start как единое now для симуляции"
                )
                self.now = min_start

        studies = self.load_studies(date_from, date_to)

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        assignment: Dict[str, int] = {}
        if use_mip:
            assignment = self.solve_mip(studies, doctors)
        else:
            assignment = self.solve_greedy(studies, doctors)

        study_map = {s.research_number: s for s in studies}
        doctor_map = {d.id: d for d in doctors}

        for sid, did in assignment.items():
            d = doctor_map[did]
            d.assigned_ids.append(sid)
            d.used_up += study_map[sid].up_value
            d.used_minutes += study_map[sid].duration_minutes

        all_assignments = []
        total_tardiness = 0.0
        total_w_tardiness = 0.0
        pstats = {"cito": 0, "asap": 0, "normal": 0}

        for d in doctors:
            if not d.assigned_ids:
                continue
            ordered = self.sequence([study_map[sid] for sid in d.assigned_ids])
            schedule = self.build_schedule(d, ordered)
            for entry in schedule:
                s = entry["study"]
                tar = entry["tardiness_hours"]
                wt = entry["weighted_tardiness"]
                total_tardiness += tar
                total_w_tardiness += wt
                pstats[s.priority] = pstats.get(s.priority, 0) + 1
                all_assignments.append(
                    {
                        "study_number": s.research_number,
                        "study_modality": list(s.modality),
                        "doctor_id": d.id,
                        "doctor_name": d.name,
                        "doctor_modality": list(d.modality),
                        "priority": s.priority,
                        "deadline": s.deadline.isoformat(),
                        "completion_time": entry["completion_time"].isoformat(),
                        "tardiness_hours": round(tar, 2),
                        "up_value": s.up_value,
                        "is_overdue": s.deadline < self.now,
                    }
                )

        self.save_to_db(assignment)

        n_asgn = len(assignment)
        z = round(total_w_tardiness, 3)
        n_cito_assigned = sum(
            1
            for s in studies
            if s.priority == "cito" and s.research_number in assignment
        )
        n_asap_assigned = sum(
            1
            for s in studies
            if s.priority == "asap" and s.research_number in assignment
        )
        n_normal_assigned = sum(
            1
            for s in studies
            if s.priority == "normal" and s.research_number in assignment
        )
        n_cito_total = sum(1 for s in studies if s.priority == "cito")
        n_asap_total = sum(1 for s in studies if s.priority == "asap")
        n_normal_total = sum(1 for s in studies if s.priority == "normal")
        self._log(
            f"Итого: {n_asgn}/{len(studies)} | "
            f"CITO: {n_cito_assigned}/{n_cito_total} | "
            f"ASAP: {n_asap_assigned}/{n_asap_total} | "
            f"NORMAL: {n_normal_assigned}/{n_normal_total} | "
            f"Z={z}"
        )

        if not self.preview_mode:
            self._log("Данные сохранены в БД")
        else:
            self._log("Данные НЕ сохранены в БД (режим предпросмотра)")

        return {
            "assigned": n_asgn,
            "unassigned": len(studies) - n_asgn,
            "cito_assigned": n_cito_assigned,
            "cito_total": n_cito_total,
            "total_tardiness": round(total_tardiness, 2),
            "total_weighted_tardiness": z,
            "avg_tardiness": round(total_tardiness / n_asgn, 2) if n_asgn else 0,
            "assignments": all_assignments,
            "doctor_stats": [
                {
                    "doctor_id": d.id,
                    "doctor_name": d.name,
                    "assigned_studies": len(d.assigned_ids),
                    "total_up": round(d.used_up, 3),
                    "max_up": round(d.max_up, 3),
                    "load_percent": round(d.used_up / d.max_up * 100, 1)
                    if d.max_up
                    else 0,
                    "remaining_up": round(d.free_up, 3),
                }
                for d in doctors
            ],
            "priority_stats": pstats,
            "objective_function": f"MIN Z = Σ wᵢ×Tᵢ (Pm|rⱼ|ΣwⱼTⱼ) = {z}",
            "message": (
                f"Оффлайн: назначено {n_asgn} из {len(studies)}. "
                f"CITO: {n_cito_assigned}/{n_cito_total}. Z={z}"
            ),
            "_debug": self._debug,
            "preview_mode": self.preview_mode,
            "target_date": self.target_date.isoformat(),
        }

    def _empty(self, message: str, studies: List = None) -> Dict:
        self._log(f"ПУСТО: {message}")
        return {
            "assigned": 0,
            "unassigned": len(studies or []),
            "total_tardiness": 0.0,
            "total_weighted_tardiness": 0.0,
            "avg_tardiness": 0,
            "assignments": [],
            "doctor_stats": [],
            "priority_stats": {"cito": 0, "asap": 0, "normal": 0},
            "objective_function": "Z = 0",
            "message": message,
            "_debug": self._debug,
        }
