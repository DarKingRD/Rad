"""
Справочник исходных значений `day_status` из файла графиков врачей.

По анализу исторических расписаний:
- 0 — рабочий день;
- 1 — обычный выходной;
- 2 — отпуск / плановое отсутствие;
- 3 — больничный / иное отсутствие;
- 4 — редкий неизвестный статус;
- 5 — период до даты начала работы врача;
- 6 — период после даты окончания работы врача.
"""
from __future__ import annotations

DAY_STATUS_WORKING = 0
DAY_STATUS_WEEKEND = 1
DAY_STATUS_VACATION = 2
DAY_STATUS_SICK_LEAVE = 3
DAY_STATUS_UNKNOWN = 4
DAY_STATUS_BEFORE_EMPLOYMENT = 5
DAY_STATUS_AFTER_EMPLOYMENT = 6

DAY_STATUS_LABELS = {
    DAY_STATUS_WORKING: "Рабочий день",
    DAY_STATUS_WEEKEND: "Выходной",
    DAY_STATUS_VACATION: "Отпуск / плановое отсутствие",
    DAY_STATUS_SICK_LEAVE: "Больничный / иное отсутствие",
    DAY_STATUS_UNKNOWN: "Неизвестный статус",
    DAY_STATUS_BEFORE_EMPLOYMENT: "До начала работы",
    DAY_STATUS_AFTER_EMPLOYMENT: "После окончания работы",
}

NON_WORKING_DAY_STATUSES = {
    DAY_STATUS_WEEKEND,
    DAY_STATUS_VACATION,
    DAY_STATUS_SICK_LEAVE,
    DAY_STATUS_UNKNOWN,
    DAY_STATUS_BEFORE_EMPLOYMENT,
    DAY_STATUS_AFTER_EMPLOYMENT,
}

WORKING_DAY_STATUSES = {DAY_STATUS_WORKING}


def normalize_day_status(value: object) -> int:
    try:
        status = int(value)
    except (TypeError, ValueError):
        return DAY_STATUS_WORKING
    return status if status in DAY_STATUS_LABELS else DAY_STATUS_UNKNOWN


def get_day_status_label(value: object) -> str:
    return DAY_STATUS_LABELS.get(normalize_day_status(value), DAY_STATUS_LABELS[DAY_STATUS_UNKNOWN])


def is_day_off_by_status(value: object) -> bool:
    return normalize_day_status(value) in NON_WORKING_DAY_STATUSES
