"""
Загрузка и нормализация данных из БД для сервиса распределения.

Модуль отвечает за:
- преобразование Django-моделей исследований в StudyData;
- преобразование расписаний и врачей в DoctorData;
- базовую нормализацию временных и количественных полей.

Вынесение загрузки в отдельный модуль упрощает сервисный слой и
делает преобразование ORM → доменные структуры более прозрачным.
"""
from __future__ import annotations

from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional

from django.utils import timezone

from api.models import Schedule, Study

from .config import MODALITY_DURATION_MINUTES, PRIORITY_WEIGHTS
from .entities import DoctorData, StudyData
from .modality_utils import normalize_modality, parse_modalities


def get_duration(study: Study) -> float:
    """
    Оценить длительность исследования в минутах.

    Если модальность известна, используется конфигурационный словарь.
    Иначе возвращается значение по умолчанию.
    """
    if study.study_type:
        mod = normalize_modality(study.study_type.modality or "")
        return float(MODALITY_DURATION_MINUTES.get(mod, 15))
    return 15.0


def get_up(study: Study) -> float:
    """
    Определить УП исследования.

    В первую очередь используется явное значение из study_type.
    Если его нет, применяется грубая оценка по модальности.
    """
    if study.study_type and study.study_type.up_value:
        return float(study.study_type.up_value)
    if study.study_type:
        mod = normalize_modality(study.study_type.modality or "")
        return {"XRAY": 0.083, "CT": 0.25, "MRI": 0.333, "US": 0.10}.get(mod, 0.25)
    return 0.25


def make_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Привести datetime к timezone-aware виду.

    Если значение уже aware, оно возвращается без изменений.
    Если значение отсутствует, возвращается None.
    """
    if dt is None:
        return None
    return dt if timezone.is_aware(dt) else timezone.make_aware(dt)


def load_studies(
    *,
    now: datetime,
    deadline_hours: Dict[str, float],
    log,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[StudyData]:
    """
    Загрузить исследования без назначенного врача и преобразовать их в StudyData.

    Дополнительно рассчитываются:
    - нормализованный приоритет;
    - дедлайн на основе priority SLA;
    - вес приоритета;
    - длительность;
    - УП;
    - множество модальностей.
    """
    qs = Study.objects.filter(diagnostician__isnull=True).select_related("study_type")

    if date_from is not None:
        qs = qs.filter(created_at__gte=date_from)
    if date_to is not None:
        qs = qs.filter(created_at__lt=date_to)

    result: List[StudyData] = []

    for s in qs:
        priority = (s.priority or "normal").strip().lower()
        if priority not in PRIORITY_WEIGHTS:
            priority = "normal"

        created = make_aware(s.created_at) or now
        deadline = created + timedelta(hours=deadline_hours.get(priority, 72))
        weight = PRIORITY_WEIGHTS.get(priority, 1.0)

        result.append(
            StudyData(
                research_number=s.research_number,
                priority=priority,
                created_at=created,
                modality=parse_modalities(s.study_type.modality if s.study_type else ""),
                up_value=get_up(s),
                duration_minutes=get_duration(s),
                deadline=deadline,
                weight=weight,
            )
        )

    log(f"Исследований без назначения: {len(result)}")
    for s in result[:3]:
        log(
            f"  Пример: research_number={s.research_number}, priority={s.priority}, "
            f"modality={s.modality}, up={s.up_value}, dur={s.duration_minutes}мин"
        )

    return result


def load_doctors(
    *,
    target_date,
    log,
) -> List[DoctorData]:
    """
    Загрузить врачей с рабочим расписанием на целевую дату и преобразовать их в DoctorData.

    В процессе:
    - отбрасываются выходные и неактивные врачи;
    - формируются границы смены и перерыва;
    - нормализуются модальности;
    - рассчитываются диагностические сообщения для лога.
    """
    schedules = Schedule.objects.filter(
        work_date=target_date,
        is_day_off=0,
    ).select_related("doctor")

    log(f"Расписаний на {target_date}: {schedules.count()}")

    result: List[DoctorData] = []

    for sch in schedules:
        doc = sch.doctor
        if not doc or not doc.is_active:
            log(
                f"  Пропуск: врач {
                    getattr(doc, 'id', '?')}, active={getattr(doc, 'is_active', '?')}"
            )
            continue

        max_up = float(doc.max_up_per_day or 50)

        if sch.time_start and sch.time_end:
            s_start = timezone.make_aware(datetime.combine(target_date, sch.time_start))
            s_end = timezone.make_aware(datetime.combine(target_date, sch.time_end))
        else:
            s_start = timezone.make_aware(datetime.combine(target_date, dt_time(hour=9)))
            s_end = timezone.make_aware(datetime.combine(target_date, dt_time(hour=17)))

        b_start = (
            timezone.make_aware(datetime.combine(target_date, sch.break_start))
            if sch.break_start
            else None
        )
        b_end = (
            timezone.make_aware(datetime.combine(target_date, sch.break_end))
            if sch.break_end
            else None
        )

        break_h = (b_end - b_start).total_seconds() / 3600.0 if b_start and b_end else 0.0
        shift_h = (s_end - s_start).total_seconds() / 3600.0
        mods = parse_modalities(doc.modality)

        log(
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

    log(f"Врачей загружено: {len(result)}")
    return result
