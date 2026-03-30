"""
Вспомогательная логика работы с рабочим временем врача.

Модуль инкапсулирует:
- выравнивание времени относительно смены и перерыва;
- расчёт доступных минут;
- перенос времени выполнения через перерыв;
- построение временных сегментов;
- работу со слотами exact MILP.

Это позволяет отделить календарно-временную механику от логики
распределения и solver-слоя.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Tuple

from .entities import DoctorData
from .config import TIME_SLOT_MINUTES


def align_to_work_time(doctor: DoctorData, dt: datetime) -> datetime:
    """
    Сдвинуть момент времени к ближайшему допустимому рабочему времени врача.

    Если время раньше начала смены, оно поднимается до shift_start.
    Если время попадает в перерыв, оно переносится на конец перерыва.
    """
    if dt < doctor.shift_start:
        dt = doctor.shift_start
    if (
        doctor.break_start
        and doctor.break_end
        and doctor.break_start <= dt < doctor.break_end
    ):
        dt = doctor.break_end
    return dt


def work_minutes_between(doctor: DoctorData, start: datetime, end: datetime) -> float:
    """
    Посчитать количество рабочих минут врача на отрезке времени.

    Из интервала исключается время вне смены и пересечение с перерывом.
    """
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


def add_work_minutes(doctor: DoctorData, start: datetime, minutes: float) -> datetime:
    """
    Прибавить к стартовому моменту заданное число рабочих минут.

    Если выполнение пересекает перерыв, расчёт автоматически переносится
    через него. Если времени смены не хватает, хвост переносится за её пределы.
    """
    remaining = max(0.0, float(minutes))
    current = align_to_work_time(doctor, start)

    while remaining > 1e-9:
        current = align_to_work_time(doctor, current)

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


def effective_start_after_prebook(
    doctor: DoctorData,
    now: datetime,
    prebooked_minutes: float = 0.0,
) -> datetime:
    """
    Получить эффективный момент старта врача с учётом уже занятых минут.

    Используется в жадном и exact-режиме, когда часть рабочей смены уже
    считается забронированной предыдущими назначениями.
    """
    base = max(doctor.shift_start, now)
    return add_work_minutes(doctor, base, prebooked_minutes)


def remaining_work_minutes(
    doctor: DoctorData,
    now: datetime,
    prebooked_minutes: float = 0.0,
) -> float:
    """
    Посчитать остаток доступных рабочих минут врача.

    В расчёте учитываются:
    - текущее время;
    - начало смены;
    - уже забронированные минуты;
    - конец смены и перерыв.
    """
    effective_start = effective_start_after_prebook(doctor, now, prebooked_minutes)
    available = work_minutes_between(doctor, effective_start, doctor.shift_end)
    return max(0.0, available)


def planning_horizon_end(doctors: List[DoctorData], now: datetime) -> datetime:
    """
    Вернуть конец текущего планового горизонта.

    Если врачи есть, это максимальный shift_end среди них.
    Если врачей нет, возвращается текущее время.
    """
    if not doctors:
        return now
    return max(d.shift_end for d in doctors)


def round_up_to_slot(dt: datetime) -> datetime:
    """
    Округлить момент времени вверх до ближайшей границы тайм-слота.

    Размер слота задаётся конфигурацией TIME_SLOT_MINUTES.
    """
    minute = dt.minute
    remainder = minute % TIME_SLOT_MINUTES
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(second=0, microsecond=0)

    delta = TIME_SLOT_MINUTES - remainder if remainder else 0
    rounded = dt + timedelta(minutes=delta)
    return rounded.replace(second=0, microsecond=0)


def execution_segments(
    doctor: DoctorData,
    start: datetime,
    minutes: float,
) -> List[Tuple[datetime, datetime]]:
    """
    Разбить выполнение исследования на рабочие сегменты внутри смены.

    Это нужно для корректного учёта перерыва и последующего определения,
    какие именно слоты exact MILP будут заняты.
    """
    remaining = max(0.0, float(minutes))
    current = align_to_work_time(doctor, start)
    segments: List[Tuple[datetime, datetime]] = []

    while remaining > 1e-9 and current < doctor.shift_end:
        current = align_to_work_time(doctor, current)
        if current >= doctor.shift_end:
            break

        next_stop = doctor.shift_end
        if doctor.break_start and doctor.break_end and current < doctor.break_start:
            next_stop = min(next_stop, doctor.break_start)

        available = max(0.0, (next_stop - current).total_seconds() / 60.0)
        chunk = min(remaining, available)

        if chunk > 1e-9:
            seg_end = current + timedelta(minutes=chunk)
            segments.append((current, seg_end))
            remaining -= chunk
            current = seg_end
        else:
            current = next_stop

        if (
            doctor.break_start
            and doctor.break_end
            and current == doctor.break_start
        ):
            current = doctor.break_end

    return segments


def slot_boundaries(
    doctor: DoctorData,
    now: datetime,
    prebooked_minutes: float = 0.0,
) -> List[datetime]:
    """
    Построить список допустимых моментов старта слотов для врача.

    Слоты начинаются с ближайшей допустимой границы после текущего времени
    и уже занятых минут, не заходят в перерыв и не выходят за конец смены.
    """
    start = round_up_to_slot(
        effective_start_after_prebook(doctor, now, prebooked_minutes)
    )

    slots: List[datetime] = []
    current = start

    while current < doctor.shift_end:
        if (
            doctor.break_start
            and doctor.break_end
            and doctor.break_start <= current < doctor.break_end
        ):
            current = round_up_to_slot(doctor.break_end)
            continue

        slots.append(current)
        current += timedelta(minutes=TIME_SLOT_MINUTES)

    return slots


def occupied_slot_indices(
    segments: List[Tuple[datetime, datetime]],
    slot_boundaries_list: List[datetime],
) -> List[int]:
    """
    Определить индексы слотов, которые пересекаются с выполнением исследования.

    Возвращаемый список используется exact MILP для задания ограничений
    непересечения по времени у одного врача.
    """
    occupied: List[int] = []

    for idx, slot_start in enumerate(slot_boundaries_list):
        slot_end = slot_start + timedelta(minutes=TIME_SLOT_MINUTES)
        if any(
            seg_start < slot_end and slot_start < seg_end
            for seg_start, seg_end in segments
        ):
            occupied.append(idx)

    return occupied
