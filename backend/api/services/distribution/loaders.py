"""
Загрузка и нормализация данных из БД для сервиса распределения.
"""
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from api.models import Schedule, Study

from .config import (
    DEFAULT_DOCTOR_MAX_UP_PER_DAY,
    DEFAULT_SHIFT_END_HOUR,
    DEFAULT_SHIFT_START_HOUR,
    DEFAULT_STUDY_DURATION_MINUTES,
    DEFAULT_STUDY_UP_VALUE,
    MODALITY_DURATION_MINUTES,
    MODALITY_UP_VALUES,
    PRIORITY_ORDER,
    PRIORITY_WEIGHTS,
)
from .entities import DoctorData, StudyData
from .modality_utils import parse_modalities, workload_modality


_PRIORITY_SET = set(PRIORITY_ORDER)


def _study_type_name(study: Study) -> str:
    study_type = getattr(study, "study_type", None)
    if study_type is None:
        return ""
    return str(getattr(study_type, "name", "") or "")


def _workload_modality_for_study(study: Study) -> str:
    """Вернуть код модальности для расчёта длительности и УП."""
    if not study.study_type:
        return "OTHER"
    return workload_modality(
        getattr(study.study_type, "modality", "") or "",
        _study_type_name(study),
    )


def get_duration(study: Study) -> float:
    """Оценить длительность исследования в минутах."""
    workload_code = _workload_modality_for_study(study)
    return float(MODALITY_DURATION_MINUTES.get(workload_code, DEFAULT_STUDY_DURATION_MINUTES))


def get_up(study: Study) -> float:
    """Определить УП исследования."""
    if study.study_type and getattr(study.study_type, "up_value", None):
        return float(study.study_type.up_value)

    workload_code = _workload_modality_for_study(study)
    return float(MODALITY_UP_VALUES.get(workload_code, DEFAULT_STUDY_UP_VALUE))


def make_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Привести datetime к timezone-aware виду."""
    if dt is None:
        return None
    return dt if timezone.is_aware(dt) else timezone.make_aware(dt)


def _default_shift_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = timezone.make_aware(datetime.combine(target_date, dt_time(hour=DEFAULT_SHIFT_START_HOUR)))
    end = timezone.make_aware(datetime.combine(target_date, dt_time(hour=DEFAULT_SHIFT_END_HOUR)))
    return start, end


def load_studies(
    *,
    now: datetime,
    deadline_hours: Dict[str, float],
    priority_weights: Dict[str, float],
    log,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[StudyData]:
    date_from = make_aware(date_from)
    date_to = make_aware(date_to)

    qs = Study.objects.filter(diagnostician__isnull=True).select_related("study_type")

    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lt=date_to)

    result: List[StudyData] = []
    for study in qs.iterator():
        priority = (study.priority or "normal").strip().lower()
        if priority not in _PRIORITY_SET:
            priority = "normal"

        created_at = make_aware(study.created_at) or now
        deadline = created_at + timedelta(hours=float(deadline_hours.get(priority, 72)))
        weight = float(priority_weights.get(priority, PRIORITY_WEIGHTS.get(priority, 1.0)))

        raw_modality = getattr(getattr(study, "study_type", None), "modality", "") or ""

        result.append(
            StudyData(
                research_number=study.research_number,
                priority=priority,
                created_at=created_at,
                modality=parse_modalities(raw_modality),
                up_value=get_up(study),
                duration_minutes=get_duration(study),
                deadline=deadline,
                weight=weight,
            )
        )

    log(f"Исследований без назначения: {len(result)}")
    for item in result[:3]:
        log(
            f"  Пример: research_number={item.research_number}, priority={item.priority}, "
            f"modality={sorted(item.modality)}, up={item.up_value}, dur={item.duration_minutes}мин"
        )
    return result


def _build_doctor_data(schedule: Schedule, target_date: date) -> DoctorData:
    doc = schedule.doctor
    max_up = float(getattr(doc, "max_up_per_day", None) or DEFAULT_DOCTOR_MAX_UP_PER_DAY)

    if schedule.time_start and schedule.time_end:
        shift_start = timezone.make_aware(datetime.combine(target_date, schedule.time_start))
        shift_end = timezone.make_aware(datetime.combine(target_date, schedule.time_end))
    else:
        shift_start, shift_end = _default_shift_bounds(target_date)

    break_start = (
        timezone.make_aware(datetime.combine(target_date, schedule.break_start))
        if schedule.break_start
        else None
    )
    break_end = (
        timezone.make_aware(datetime.combine(target_date, schedule.break_end))
        if schedule.break_end
        else None
    )

    return DoctorData(
        id=doc.id,
        name=doc.fio_alias or f"Врач {doc.id}",
        modality=parse_modalities(doc.modality),
        max_up=max_up,
        shift_start=shift_start,
        shift_end=shift_end,
        break_start=break_start,
        break_end=break_end,
    )


def load_doctors(*, target_date, log) -> List[DoctorData]:
    """Загрузить врачей с расписанием на целевую дату."""
    schedules = list(
        Schedule.objects.filter(work_date=target_date, is_day_off=0)
        .select_related("doctor")
        .only(
            "doctor_id",
            "time_start",
            "time_end",
            "break_start",
            "break_end",
            "doctor__id",
            "doctor__fio_alias",
            "doctor__is_active",
            "doctor__modality",
            "doctor__max_up_per_day",
        )
        .order_by("doctor_id", "time_start", "time_end")
    )

    log(f"Расписаний на {target_date}: {len(schedules)}")

    result: List[DoctorData] = []
    seen_schedule_keys: set[tuple] = set()
    doctor_seen: set[int] = set()

    for schedule in schedules:
        doc = schedule.doctor
        if not doc or not getattr(doc, "is_active", False):
            log(
                f"  Пропуск: врач {getattr(doc, 'id', '?')}, "
                f"active={getattr(doc, 'is_active', '?')}"
            )
            continue

        dedupe_key = (
            doc.id,
            schedule.time_start,
            schedule.time_end,
            schedule.break_start,
            schedule.break_end,
        )
        if dedupe_key in seen_schedule_keys:
            log(f"  Дубликат расписания врача id={doc.id} пропущен")
            continue
        seen_schedule_keys.add(dedupe_key)

        if doc.id in doctor_seen:
            log(
                f"  Найдено несколько расписаний для врача id={doc.id}; "
                "оставлена первая строка, остальные пропущены"
            )
            continue

        doctor_seen.add(doc.id)
        doctor = _build_doctor_data(schedule, target_date)

        log(
            f"  Врач {doctor.name} (id={doctor.id}): max_up={doctor.max_up}, "
            f"смена={doctor.shift_hours:.1f}ч, перерыв={doctor.break_minutes:.0f}мин, "
            f"мод={sorted(doctor.modality)}"
        )
        result.append(doctor)

    log(f"Врачей загружено: {len(result)}")
    return result
