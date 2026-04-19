from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from math import ceil
from statistics import mean

from django.db.models import Count, DecimalField, Max, Min, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Doctor, Schedule, Study
from .doctor_queries import get_daily_limit

DEFAULT_FORECAST_DAYS = 7
MAX_FORECAST_DAYS = 366

MODALITY_ORDER = {
    "FLG": 1,
    "XRAY": 2,
    "CT": 3,
    "MRI": 4,
    "MMG": 5,
    "US": 6,
    "ECG": 7,
    "HOLTER": 8,
    "OTHER": 99,
}


def _as_float(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round_float(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


def _ceil_non_negative(value: float) -> int:
    if value <= 0:
        return 0
    return int(ceil(value - 1e-9))


def _daterange(start: date, end_inclusive: date):
    current = start
    while current <= end_inclusive:
        yield current
        current += timedelta(days=1)


def _weekday_label(day: date) -> str:
    labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    return labels[day.weekday()]


def _sort_modalities(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            MODALITY_ORDER.get(item.get("modality") or "OTHER", 500),
            -(item.get("expected_up") or 0),
            item.get("modality") or "",
        ),
    )


def _normalize_date_range(date_from: date | None, date_to: date | None):
    today = timezone.localdate()
    resolved_from = date_from or today
    resolved_to = date_to or (resolved_from + timedelta(days=DEFAULT_FORECAST_DAYS - 1))

    if resolved_from > resolved_to:
        raise ValueError("date_to не может быть раньше date_from")

    if (resolved_to - resolved_from).days + 1 > MAX_FORECAST_DAYS:
        raise ValueError("Слишком большой диапазон прогноза. Допустимо не более 366 дней.")

    return resolved_from, resolved_to


def _get_history_bounds():
    bounds = Study.objects.filter(created_at__isnull=False).aggregate(
        min_date=Min("created_at__date"),
        max_date=Max("created_at__date"),
    )
    return bounds["min_date"], bounds["max_date"]


def _get_all_active_doctors():
    return list(
        Doctor.objects.filter(is_active=True).only(
            "id",
            "max_up_per_day",
            "position_type",
            "modality",
        )
    )


def _get_capacity_context():
    doctors = _get_all_active_doctors()
    if not doctors:
        return {
            "avg_daily_capacity": 8.0,
            "capacity_by_modality": {},
        }

    capacities = [float(get_daily_limit(doctor)) for doctor in doctors]
    avg_daily_capacity = mean(capacities) if capacities else 8.0

    modality_capacities: dict[str, list[float]] = defaultdict(list)
    for doctor in doctors:
        doctor_capacity = float(get_daily_limit(doctor))
        for modality in doctor.modality or []:
            modality_capacities[(modality or "OTHER").upper()].append(doctor_capacity)

    capacity_by_modality = {
        modality: (mean(values) if values else avg_daily_capacity)
        for modality, values in modality_capacities.items()
    }

    return {
        "avg_daily_capacity": avg_daily_capacity,
        "capacity_by_modality": capacity_by_modality,
    }


def _build_profiles(history_start: date, history_end: date):
    total_days = (history_end - history_start).days + 1
    weekday_occurrences = {weekday: 0 for weekday in range(7)}
    for current_day in _daterange(history_start, history_end):
        weekday_occurrences[current_day.weekday()] += 1

    weekday_totals: dict[int, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: {"studies_count": 0.0, "total_up": 0.0})
    )
    overall_totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"studies_count": 0.0, "total_up": 0.0}
    )

    rows = (
        Study.objects.filter(
            created_at__date__gte=history_start,
            created_at__date__lte=history_end,
            created_at__isnull=False,
            study_type_id__isnull=False,
        )
        .values("created_at__date", "study_type__modality")
        .annotate(
            studies_count=Count("research_number"),
            total_up=Coalesce(
                Sum("study_type__up_value"),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=12, decimal_places=2),
            ),
        )
    )

    for row in rows:
        day = row["created_at__date"]
        if day is None:
            continue
        modality = (row["study_type__modality"] or "OTHER").upper()
        weekday_bucket = weekday_totals[day.weekday()][modality]
        weekday_bucket["studies_count"] += float(row["studies_count"] or 0)
        weekday_bucket["total_up"] += _as_float(row["total_up"])
        overall_totals[modality]["studies_count"] += float(row["studies_count"] or 0)
        overall_totals[modality]["total_up"] += _as_float(row["total_up"])

    overall_profile = _sort_modalities(
        [
            {
                "modality": modality,
                "expected_studies": values["studies_count"] / total_days,
                "expected_up": values["total_up"] / total_days,
            }
            for modality, values in overall_totals.items()
            if total_days > 0 and (values["studies_count"] > 0 or values["total_up"] > 0)
        ]
    )

    weekday_profiles: dict[int, list[dict]] = {weekday: [] for weekday in range(7)}
    for weekday in range(7):
        occurrences = weekday_occurrences.get(weekday) or 0
        if occurrences <= 0:
            weekday_profiles[weekday] = overall_profile
            continue

        items = []
        for modality, values in weekday_totals.get(weekday, {}).items():
            expected_studies = values["studies_count"] / occurrences
            expected_up = values["total_up"] / occurrences
            if expected_studies <= 0 and expected_up <= 0:
                continue
            items.append(
                {
                    "modality": modality,
                    "expected_studies": expected_studies,
                    "expected_up": expected_up,
                }
            )
        weekday_profiles[weekday] = _sort_modalities(items) if items else overall_profile

    return weekday_profiles, overall_profile


def _get_scheduled_doctors_map(date_from: date, date_to: date) -> dict[date, int]:
    rows = (
        Schedule.objects.filter(
            work_date__gte=date_from,
            work_date__lte=date_to,
            is_day_off=0,
            doctor__is_active=True,
        )
        .values("work_date")
        .annotate(doctors_count=Count("doctor", distinct=True))
    )
    return {
        row["work_date"]: int(row["doctors_count"] or 0)
        for row in rows
    }


def _build_day_forecast(*, day: date, weekday_profiles: dict[int, list[dict]], overall_profile: list[dict], capacity_context: dict, scheduled_doctors_map: dict[date, int]):
    avg_daily_capacity = float(capacity_context["avg_daily_capacity"] or 8.0)
    capacity_by_modality = capacity_context["capacity_by_modality"]

    profile_items = weekday_profiles.get(day.weekday()) or overall_profile

    required_modalities = []
    expected_studies_total = 0.0
    expected_up_total = 0.0

    for item in profile_items:
        modality = (item.get("modality") or "OTHER").upper()
        expected_studies = float(item.get("expected_studies") or 0.0)
        expected_up = float(item.get("expected_up") or 0.0)
        expected_studies_total += expected_studies
        expected_up_total += expected_up

        modality_capacity = float(capacity_by_modality.get(modality) or avg_daily_capacity)
        recommended_doctors = _ceil_non_negative(expected_up / modality_capacity)

        required_modalities.append(
            {
                "modality": modality,
                "expected_studies": _round_float(expected_studies, 1),
                "expected_up": _round_float(expected_up, 2),
                "recommended_doctors": recommended_doctors,
            }
        )

    min_doctors = _ceil_non_negative(expected_up_total / avg_daily_capacity)
    scheduled_doctors = int(scheduled_doctors_map.get(day, 0))

    return {
        "date": day.isoformat(),
        "label": day.strftime("%d.%m"),
        "weekday": _weekday_label(day),
        "scheduled_doctors": scheduled_doctors,
        "expected_studies_total": _round_float(expected_studies_total, 1),
        "expected_up_total": _round_float(expected_up_total, 2),
        "min_doctors": min_doctors,
        "gap_to_schedule": min_doctors - scheduled_doctors,
        "required_modalities": _sort_modalities(required_modalities),
    }


def build_shift_forecast(*, date_from: date | None = None, date_to: date | None = None):
    forecast_date_from, forecast_date_to = _normalize_date_range(date_from, date_to)
    history_start, history_end = _get_history_bounds()

    if not history_start or not history_end:
        return {
            "date_from": forecast_date_from.isoformat(),
            "date_to": forecast_date_to.isoformat(),
            "history_start_date": None,
            "history_end_date": None,
            "generated_at": timezone.now().isoformat(),
            "summary": {
                "total_expected_studies": 0.0,
                "total_expected_up": 0.0,
                "max_min_doctors_per_shift": 0,
                "modalities": [],
            },
            "chart": [],
            "days": [],
            "message": "Недостаточно исторических исследований для построения прогноза.",
        }

    weekday_profiles, overall_profile = _build_profiles(history_start, history_end)
    capacity_context = _get_capacity_context()
    scheduled_doctors_map = _get_scheduled_doctors_map(forecast_date_from, forecast_date_to)

    days = [
        _build_day_forecast(
            day=current_day,
            weekday_profiles=weekday_profiles,
            overall_profile=overall_profile,
            capacity_context=capacity_context,
            scheduled_doctors_map=scheduled_doctors_map,
        )
        for current_day in _daterange(forecast_date_from, forecast_date_to)
    ]

    chart = [
        {
            "date": item["date"],
            "label": item["label"],
            "expected_studies_total": item["expected_studies_total"],
            "min_doctors": item["min_doctors"],
        }
        for item in days
    ]

    modalities = []
    seen_modalities = set()
    for day in days:
        for item in day["required_modalities"]:
            modality = item["modality"]
            if modality not in seen_modalities:
                seen_modalities.add(modality)
                modalities.append(modality)

    message = (
        "Прогноз рассчитан по всем доступным исследованиям в БД "
        f"за период {history_start.isoformat()}–{history_end.isoformat()} "
        f"и построен для выбранного диапазона {forecast_date_from.isoformat()}–{forecast_date_to.isoformat()}."
    )

    return {
        "date_from": forecast_date_from.isoformat(),
        "date_to": forecast_date_to.isoformat(),
        "history_start_date": history_start.isoformat(),
        "history_end_date": history_end.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "summary": {
            "total_expected_studies": _round_float(sum(item["expected_studies_total"] for item in days), 1),
            "total_expected_up": _round_float(sum(item["expected_up_total"] for item in days), 2),
            "max_min_doctors_per_shift": max((item["min_doctors"] for item in days), default=0),
            "modalities": modalities,
        },
        "chart": chart,
        "days": days,
        "message": message,
    }
