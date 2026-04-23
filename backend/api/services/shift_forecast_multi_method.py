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
from .modality_catalog import (
    CT,
    CT_CONTRAST,
    FLUOROGRAPHY,
    MRI,
    MRI_CONTRAST,
    XRAY,
    normalize_modality_name,
)

try:
    import numpy as np
    from sklearn.linear_model import LinearRegression, PoissonRegressor
except Exception:  # pragma: no cover
    np = None
    LinearRegression = None
    PoissonRegressor = None

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except Exception:  # pragma: no cover
    ExponentialSmoothing = None


DEFAULT_FORECAST_DAYS = 7
MAX_FORECAST_DAYS = 366
DEFAULT_RECENT_WEEKS = 4
DEFAULT_MOVING_WINDOW_DAYS = 14
DEFAULT_MIN_TRAIN_DAYS = 21
DEFAULT_EVALUATION_DAYS = 7
DEFAULT_HOLT_WINTERS_SEASONAL_PERIODS = 7

FORECAST_METHODS = {
    "overall_mean": "Среднее по всем дням истории",
    "weekday_mean": "Среднее по одинаковым дням недели",
    "recent_weekday_mean": "Среднее по последним одинаковым дням недели",
    "moving_average": "Скользящее среднее по последним дням",
    "seasonal_naive": "Значение последнего такого же дня недели",
    "weighted_weekday_mean": "Взвешенное среднее по одинаковым дням недели с приоритетом последних наблюдений",
    "linear_regression": "Линейная регрессия с календарными признаками и лагами",
    "poisson_regression": "Пуассоновская регрессия для количества исследований",
    "holt_winters": "Экспоненциальное сглаживание Холта—Уинтерса",
}

FORECAST_COMPARE_METHODS = (
    "weekday_mean",
    "linear_regression",
    "poisson_regression",
    "holt_winters",
)

SIMPLE_PROFILE_METHODS = {
    "overall_mean",
    "weekday_mean",
    "recent_weekday_mean",
    "moving_average",
    "seasonal_naive",
    "weighted_weekday_mean",
}
MODEL_BASED_METHODS = {
    "linear_regression",
    "poisson_regression",
    "holt_winters",
}

FORECAST_FLUOROGRAPHY = "Флюорография"
FORECAST_XRAY = "Рентген"
FORECAST_CT = "КТ"
FORECAST_CT_CONTRAST = "КТ с контрастом"
FORECAST_MRI = "МРТ"
FORECAST_MRI_CONTRAST = "МРТ с контрастом"
FORECAST_OTHER = "Прочее"

FORECAST_MODALITY_ORDER = {
    FORECAST_XRAY: 1,
    FORECAST_FLUOROGRAPHY: 2,
    FORECAST_CT: 3,
    FORECAST_CT_CONTRAST: 4,
    FORECAST_MRI: 5,
    FORECAST_MRI_CONTRAST: 6,
    FORECAST_OTHER: 999,
}


def _forecast_modality_group(value: object) -> str:
    modality = normalize_modality_name(value)
    if modality == XRAY:
        return FORECAST_XRAY
    if modality == FLUOROGRAPHY:
        return FORECAST_FLUOROGRAPHY
    if modality == CT:
        return FORECAST_CT
    if modality == CT_CONTRAST:
        return FORECAST_CT_CONTRAST
    if modality == MRI:
        return FORECAST_MRI
    if modality == MRI_CONTRAST:
        return FORECAST_MRI_CONTRAST
    return FORECAST_OTHER


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
            FORECAST_MODALITY_ORDER.get(_forecast_modality_group(item.get("modality")), 999),
            -(item.get("expected_up") or 0),
            _forecast_modality_group(item.get("modality")),
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
            "avg_daily_capacity": 7.2,
            "capacity_by_modality": {},
        }

    capacities = [float(get_daily_limit(doctor)) for doctor in doctors]
    avg_daily_capacity = mean(capacities) if capacities else 7.2

    modality_capacities: dict[str, list[float]] = defaultdict(list)
    for doctor in doctors:
        doctor_capacity = float(get_daily_limit(doctor))
        doctor_groups = set()
        for modality in doctor.modality or []:
            group = _forecast_modality_group(modality)
            if group == FORECAST_OTHER:
                continue
            doctor_groups.add(group)
        for group in doctor_groups:
            if group != FORECAST_OTHER:
                modality_capacities[group].append(doctor_capacity)

    capacity_by_modality = {
        modality: (mean(values) if values else avg_daily_capacity)
        for modality, values in modality_capacities.items()
    }

    return {
        "avg_daily_capacity": avg_daily_capacity,
        "capacity_by_modality": capacity_by_modality,
    }



def _load_daily_series(history_start: date, history_end: date):
    daily_series: dict[date, dict[str, dict[str, float]]] = {
        current_day: {} for current_day in _daterange(history_start, history_end)
    }
    modalities: set[str] = set()

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
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            ),
        )
    )

    for row in rows:
        day = row["created_at__date"]
        if day is None:
            continue

        modality = _forecast_modality_group(row["study_type__modality"])
        modalities.add(modality)
        day_bucket = daily_series.setdefault(day, {})
        modality_bucket = day_bucket.setdefault(
            modality,
            {"studies_count": 0.0, "total_up": 0.0},
        )
        modality_bucket["studies_count"] += float(row["studies_count"] or 0.0)
        modality_bucket["total_up"] += _as_float(row["total_up"])

    return daily_series, sorted(
        modalities,
        key=lambda item: FORECAST_MODALITY_ORDER.get(item, 999),
    )



def _load_daily_totals(history_start: date, history_end: date) -> dict[date, dict[str, float]]:
    totals = {
        current_day: {"studies_count": 0.0, "total_up": 0.0}
        for current_day in _daterange(history_start, history_end)
    }

    rows = (
        Study.objects.filter(
            created_at__date__gte=history_start,
            created_at__date__lte=history_end,
            created_at__isnull=False,
            study_type_id__isnull=False,
        )
        .values("created_at__date")
        .annotate(
            studies_count=Count("research_number"),
            total_up=Coalesce(
                Sum("study_type__up_value"),
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            ),
        )
    )

    for row in rows:
        current_day = row["created_at__date"]
        if current_day is None:
            continue
        totals[current_day] = {
            "studies_count": float(row["studies_count"] or 0.0),
            "total_up": _as_float(row["total_up"]),
        }

    return totals



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



def _weighted_average(pairs: list[tuple[float, float]]) -> float:
    weight_sum = sum(weight for _, weight in pairs)
    if weight_sum <= 0:
        return 0.0
    return sum(value * weight for value, weight in pairs) / weight_sum



def _select_source_days(
    *,
    target_day: date,
    history_days: list[date],
    method: str,
    recent_weeks: int,
    moving_window_days: int,
) -> list[date]:
    if not history_days:
        return []

    if method == "overall_mean":
        return history_days

    if method == "weekday_mean":
        same_weekday_days = [day for day in history_days if day.weekday() == target_day.weekday()]
        return same_weekday_days or history_days

    if method == "recent_weekday_mean":
        same_weekday_days = [day for day in history_days if day.weekday() == target_day.weekday()]
        if same_weekday_days:
            return same_weekday_days[-max(1, recent_weeks):]
        return history_days[-max(1, moving_window_days):]

    if method == "moving_average":
        return history_days[-max(1, moving_window_days):]

    if method == "seasonal_naive":
        same_weekday_days = [day for day in history_days if day.weekday() == target_day.weekday()]
        if same_weekday_days:
            return [same_weekday_days[-1]]
        return [history_days[-1]]

    if method == "weighted_weekday_mean":
        same_weekday_days = [day for day in history_days if day.weekday() == target_day.weekday()]
        return same_weekday_days or history_days

    raise ValueError(f"Неизвестный метод прогнозирования: {method}")



def _build_profile_for_day(
    *,
    target_day: date,
    daily_series: dict[date, dict[str, dict[str, float]]],
    modalities: list[str],
    history_start: date,
    history_end: date,
    method: str,
    recent_weeks: int,
    moving_window_days: int,
) -> list[dict]:
    history_days = [current_day for current_day in _daterange(history_start, history_end)]
    source_days = _select_source_days(
        target_day=target_day,
        history_days=history_days,
        method=method,
        recent_weeks=recent_weeks,
        moving_window_days=moving_window_days,
    )
    if not source_days:
        return []

    items: list[dict] = []
    for modality in modalities:
        if method == "weighted_weekday_mean":
            study_pairs: list[tuple[float, float]] = []
            up_pairs: list[tuple[float, float]] = []
            for index, source_day in enumerate(source_days, start=1):
                source_values = daily_series.get(source_day, {}).get(modality, {})
                study_pairs.append((float(source_values.get("studies_count") or 0.0), float(index)))
                up_pairs.append((float(source_values.get("total_up") or 0.0), float(index)))
            expected_studies = _weighted_average(study_pairs)
            expected_up = _weighted_average(up_pairs)
        else:
            studies_total = 0.0
            up_total = 0.0
            for source_day in source_days:
                source_values = daily_series.get(source_day, {}).get(modality, {})
                studies_total += float(source_values.get("studies_count") or 0.0)
                up_total += float(source_values.get("total_up") or 0.0)
            denominator = len(source_days)
            expected_studies = studies_total / denominator if denominator else 0.0
            expected_up = up_total / denominator if denominator else 0.0

        if expected_studies <= 0 and expected_up <= 0:
            continue

        items.append(
            {
                "modality": modality,
                "expected_studies": expected_studies,
                "expected_up": expected_up,
            }
        )

    return _sort_modalities(items)



def _safe_ratio(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    if denominator is None or denominator <= 0:
        return fallback
    return numerator / denominator



def _mean_or_default(values: list[float], default: float = 0.0) -> float:
    return mean(values) if values else default



def _get_series_value(series_map: dict[date, float], target_day: date, default: float = 0.0) -> float:
    return float(series_map.get(target_day, default) or 0.0)



def _get_past_values(series_map: dict[date, float], target_day: date, offsets: list[int]) -> list[float]:
    values: list[float] = []
    for offset in offsets:
        values.append(_get_series_value(series_map, target_day - timedelta(days=offset), 0.0))
    return values



def _get_recent_window_values(series_map: dict[date, float], target_day: date, window_days: int) -> list[float]:
    values: list[float] = []
    for offset in range(window_days, 0, -1):
        values.append(_get_series_value(series_map, target_day - timedelta(days=offset), 0.0))
    return values



def _get_same_weekday_values(series_map: dict[date, float], target_day: date, weeks: int) -> list[float]:
    values: list[float] = []
    for offset in range(1, weeks + 1):
        values.append(_get_series_value(series_map, target_day - timedelta(days=7 * offset), 0.0))
    return values



def _build_feature_row(
    *,
    target_day: date,
    series_map: dict[date, float],
    origin_day: date,
    global_mean_value: float,
) -> list[float]:
    lag_1, lag_7, lag_14 = _get_past_values(series_map, target_day, [1, 7, 14])
    recent_7 = _get_recent_window_values(series_map, target_day, 7)
    recent_14 = _get_recent_window_values(series_map, target_day, 14)
    same_weekday_recent = _get_same_weekday_values(series_map, target_day, 4)

    weekday_flags = [1.0 if target_day.weekday() == weekday else 0.0 for weekday in range(7)]
    day_index = float((target_day - origin_day).days)
    month = float(target_day.month)
    day_of_month = float(target_day.day)
    is_weekend = 1.0 if target_day.weekday() >= 5 else 0.0

    return [
        day_index,
        month,
        day_of_month,
        is_weekend,
        *weekday_flags,
        lag_1,
        lag_7,
        lag_14,
        _mean_or_default(recent_7, global_mean_value),
        _mean_or_default(recent_14, global_mean_value),
        _mean_or_default(same_weekday_recent, global_mean_value),
    ]



def _prepare_regression_training_data(
    *,
    series_map: dict[date, float],
    history_days: list[date],
    origin_day: date,
) -> tuple[list[list[float]], list[float]]:
    global_mean_value = _mean_or_default([_get_series_value(series_map, day, 0.0) for day in history_days], 0.0)
    x_rows: list[list[float]] = []
    y_values: list[float] = []

    for current_day in history_days:
        x_rows.append(
            _build_feature_row(
                target_day=current_day,
                series_map=series_map,
                origin_day=origin_day,
                global_mean_value=global_mean_value,
            )
        )
        y_values.append(_get_series_value(series_map, current_day, 0.0))

    return x_rows, y_values



def _forecast_with_linear_regression(
    *,
    history_days: list[date],
    forecast_days: list[date],
    totals_map: dict[date, dict[str, float]],
    target_key: str,
) -> dict[date, float]:
    if LinearRegression is None or np is None:
        raise RuntimeError("scikit-learn недоступен")

    series_map = {day: float((totals_map.get(day) or {}).get(target_key) or 0.0) for day in history_days}
    origin_day = history_days[0]
    x_rows, y_values = _prepare_regression_training_data(
        series_map=series_map,
        history_days=history_days,
        origin_day=origin_day,
    )

    model = LinearRegression()
    model.fit(np.array(x_rows, dtype=float), np.array(y_values, dtype=float))

    predicted_series = dict(series_map)
    result: dict[date, float] = {}
    global_mean_value = _mean_or_default(list(series_map.values()), 0.0)

    for current_day in forecast_days:
        feature_row = _build_feature_row(
            target_day=current_day,
            series_map=predicted_series,
            origin_day=origin_day,
            global_mean_value=global_mean_value,
        )
        prediction = float(model.predict(np.array([feature_row], dtype=float))[0])
        prediction = max(0.0, prediction)
        predicted_series[current_day] = prediction
        result[current_day] = prediction

    return result



def _forecast_with_poisson_regression(
    *,
    history_days: list[date],
    forecast_days: list[date],
    totals_map: dict[date, dict[str, float]],
) -> dict[date, float]:
    if PoissonRegressor is None or np is None:
        raise RuntimeError("scikit-learn недоступен")

    series_map = {day: float((totals_map.get(day) or {}).get("studies_count") or 0.0) for day in history_days}
    origin_day = history_days[0]
    x_rows, y_values = _prepare_regression_training_data(
        series_map=series_map,
        history_days=history_days,
        origin_day=origin_day,
    )

    model = PoissonRegressor(alpha=1e-6, max_iter=1000)
    model.fit(np.array(x_rows, dtype=float), np.array(y_values, dtype=float))

    predicted_series = dict(series_map)
    result: dict[date, float] = {}
    global_mean_value = _mean_or_default(list(series_map.values()), 0.0)

    for current_day in forecast_days:
        feature_row = _build_feature_row(
            target_day=current_day,
            series_map=predicted_series,
            origin_day=origin_day,
            global_mean_value=global_mean_value,
        )
        prediction = float(model.predict(np.array([feature_row], dtype=float))[0])
        prediction = max(0.0, prediction)
        predicted_series[current_day] = prediction
        result[current_day] = prediction

    return result



def _forecast_with_holt_winters(
    *,
    history_days: list[date],
    forecast_days: list[date],
    totals_map: dict[date, dict[str, float]],
    target_key: str,
    seasonal_periods: int = DEFAULT_HOLT_WINTERS_SEASONAL_PERIODS,
) -> dict[date, float]:
    if ExponentialSmoothing is None:
        raise RuntimeError("statsmodels недоступен")

    values = [float((totals_map.get(day) or {}).get(target_key) or 0.0) for day in history_days]
    if len(values) < seasonal_periods * 2:
        raise RuntimeError("Недостаточно истории для Holt-Winters")

    model = ExponentialSmoothing(
        values,
        trend="add",
        seasonal="add",
        seasonal_periods=seasonal_periods,
        initialization_method="estimated",
    )
    fitted_model = model.fit(optimized=True)
    fitted_values = list(fitted_model.fittedvalues)
    fitted_by_day = {
        current_day: max(0.0, float(fitted_value))
        for current_day, fitted_value in zip(history_days, fitted_values)
    }

    history_end = history_days[-1]
    future_days = [current_day for current_day in forecast_days if current_day > history_end]
    future_by_day: dict[date, float] = {}
    if future_days:
        max_horizon = max((current_day - history_end).days for current_day in future_days)
        forecast_values = fitted_model.forecast(max_horizon)
        for current_day in future_days:
            horizon_index = (current_day - history_end).days - 1
            future_by_day[current_day] = max(0.0, float(forecast_values[horizon_index]))

    result: dict[date, float] = {}
    for current_day in forecast_days:
        if current_day in fitted_by_day:
            result[current_day] = fitted_by_day[current_day]
        else:
            result[current_day] = future_by_day.get(current_day, 0.0)
    return result



def _forecast_model_based_totals(
    *,
    forecast_days: list[date],
    history_start: date,
    history_end: date,
    totals_map: dict[date, dict[str, float]],
    method: str,
) -> dict[date, dict[str, float]]:
    history_days = [current_day for current_day in _daterange(history_start, history_end)]
    if not history_days:
        return {current_day: {"studies_count": 0.0, "total_up": 0.0} for current_day in forecast_days}

    if method == "linear_regression":
        predicted_studies = _forecast_with_linear_regression(
            history_days=history_days,
            forecast_days=forecast_days,
            totals_map=totals_map,
            target_key="studies_count",
        )
        predicted_up = _forecast_with_linear_regression(
            history_days=history_days,
            forecast_days=forecast_days,
            totals_map=totals_map,
            target_key="total_up",
        )
        return {
            current_day: {
                "studies_count": predicted_studies.get(current_day, 0.0),
                "total_up": predicted_up.get(current_day, 0.0),
            }
            for current_day in forecast_days
        }

    if method == "poisson_regression":
        predicted_studies = _forecast_with_poisson_regression(
            history_days=history_days,
            forecast_days=forecast_days,
            totals_map=totals_map,
        )
        weekday_ratios: dict[int, float] = {}
        global_ratio = _safe_ratio(
            sum(float((totals_map.get(day) or {}).get("total_up") or 0.0) for day in history_days),
            sum(float((totals_map.get(day) or {}).get("studies_count") or 0.0) for day in history_days),
            0.0,
        )
        for weekday in range(7):
            weekday_days = [day for day in history_days if day.weekday() == weekday]
            weekday_ratios[weekday] = _safe_ratio(
                sum(float((totals_map.get(day) or {}).get("total_up") or 0.0) for day in weekday_days),
                sum(float((totals_map.get(day) or {}).get("studies_count") or 0.0) for day in weekday_days),
                global_ratio,
            )

        return {
            current_day: {
                "studies_count": predicted_studies.get(current_day, 0.0),
                "total_up": predicted_studies.get(current_day, 0.0) * weekday_ratios.get(current_day.weekday(), global_ratio),
            }
            for current_day in forecast_days
        }

    if method == "holt_winters":
        predicted_studies = _forecast_with_holt_winters(
            history_days=history_days,
            forecast_days=forecast_days,
            totals_map=totals_map,
            target_key="studies_count",
        )
        predicted_up = _forecast_with_holt_winters(
            history_days=history_days,
            forecast_days=forecast_days,
            totals_map=totals_map,
            target_key="total_up",
        )
        return {
            current_day: {
                "studies_count": predicted_studies.get(current_day, 0.0),
                "total_up": predicted_up.get(current_day, 0.0),
            }
            for current_day in forecast_days
        }

    raise ValueError(f"Неизвестный модельный метод прогнозирования: {method}")



def _rescale_profile_items(profile_items: list[dict], *, target_studies: float, target_up: float) -> list[dict]:
    if not profile_items:
        return []

    total_profile_studies = sum(float(item.get("expected_studies") or 0.0) for item in profile_items)
    total_profile_up = sum(float(item.get("expected_up") or 0.0) for item in profile_items)

    studies_scale = _safe_ratio(target_studies, total_profile_studies, 0.0) if total_profile_studies > 0 else 0.0
    up_scale = _safe_ratio(target_up, total_profile_up, 0.0) if total_profile_up > 0 else 0.0

    if total_profile_studies <= 0 and total_profile_up <= 0:
        return []

    return _sort_modalities(
        [
            {
                "modality": item["modality"],
                "expected_studies": float(item.get("expected_studies") or 0.0) * studies_scale,
                "expected_up": float(item.get("expected_up") or 0.0) * up_scale,
            }
            for item in profile_items
        ]
    )



def _build_day_forecast(
    *,
    day: date,
    profile_items: list[dict],
    capacity_context: dict,
    scheduled_doctors_map: dict[date, int],
):
    avg_daily_capacity = float(capacity_context["avg_daily_capacity"] or 7.2)
    capacity_by_modality = capacity_context["capacity_by_modality"]

    required_modalities = []
    expected_studies_total = 0.0
    expected_up_total = 0.0

    for item in profile_items:
        modality = _forecast_modality_group(item.get("modality"))

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



def build_shift_forecast(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    method: str = "weekday_mean",
    recent_weeks: int = DEFAULT_RECENT_WEEKS,
    moving_window_days: int = DEFAULT_MOVING_WINDOW_DAYS,
    history_start_override: date | None = None,
    history_end_override: date | None = None,
):
    forecast_date_from, forecast_date_to = _normalize_date_range(date_from, date_to)
    history_start, history_end = _get_history_bounds()

    if history_start_override is not None:
        history_start = history_start_override
    if history_end_override is not None:
        history_end = history_end_override

    if not history_start or not history_end:
        return {
            "date_from": forecast_date_from.isoformat(),
            "date_to": forecast_date_to.isoformat(),
            "history_start_date": None,
            "history_end_date": None,
            "generated_at": timezone.now().isoformat(),
            "method": method,
            "method_label": FORECAST_METHODS.get(method, method),
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

    if history_start > history_end:
        raise ValueError("Недостаточно исторических данных для выбранного периода обучения.")

    if method not in FORECAST_METHODS:
        raise ValueError(
            f"Неизвестный метод прогнозирования: {method}. Доступно: {', '.join(FORECAST_METHODS)}"
        )

    daily_series, modalities = _load_daily_series(history_start, history_end)
    totals_map = _load_daily_totals(history_start, history_end)
    capacity_context = _get_capacity_context()
    scheduled_doctors_map = _get_scheduled_doctors_map(forecast_date_from, forecast_date_to)
    forecast_days = [current_day for current_day in _daterange(forecast_date_from, forecast_date_to)]

    day_profiles: dict[date, list[dict]] = {}
    model_warning = None

    if method in SIMPLE_PROFILE_METHODS:
        for current_day in forecast_days:
            day_profiles[current_day] = _build_profile_for_day(
                target_day=current_day,
                daily_series=daily_series,
                modalities=modalities,
                history_start=history_start,
                history_end=history_end,
                method=method,
                recent_weeks=recent_weeks,
                moving_window_days=moving_window_days,
            )
    else:
        try:
            predicted_totals = _forecast_model_based_totals(
                forecast_days=forecast_days,
                history_start=history_start,
                history_end=history_end,
                totals_map=totals_map,
                method=method,
            )
            for current_day in forecast_days:
                baseline_profile = _build_profile_for_day(
                    target_day=current_day,
                    daily_series=daily_series,
                    modalities=modalities,
                    history_start=history_start,
                    history_end=history_end,
                    method="weekday_mean",
                    recent_weeks=recent_weeks,
                    moving_window_days=moving_window_days,
                )
                total_values = predicted_totals.get(current_day, {"studies_count": 0.0, "total_up": 0.0})
                day_profiles[current_day] = _rescale_profile_items(
                    baseline_profile,
                    target_studies=float(total_values.get("studies_count") or 0.0),
                    target_up=float(total_values.get("total_up") or 0.0),
                )
        except Exception as exc:
            model_warning = (
                f"Метод '{FORECAST_METHODS[method]}' не удалось применить: {exc}. "
                "Использован fallback на метод 'Среднее по одинаковым дням недели'."
            )
            for current_day in forecast_days:
                day_profiles[current_day] = _build_profile_for_day(
                    target_day=current_day,
                    daily_series=daily_series,
                    modalities=modalities,
                    history_start=history_start,
                    history_end=history_end,
                    method="weekday_mean",
                    recent_weeks=recent_weeks,
                    moving_window_days=moving_window_days,
                )

    days = [
        _build_day_forecast(
            day=current_day,
            profile_items=day_profiles.get(current_day, []),
            capacity_context=capacity_context,
            scheduled_doctors_map=scheduled_doctors_map,
        )
        for current_day in forecast_days
    ]

    chart = [
        {
            "date": item["date"],
            "label": item["label"],
            "expected_studies_total": item["expected_studies_total"],
            "expected_up_total": item["expected_up_total"],
            "min_doctors": item["min_doctors"],
        }
        for item in days
    ]

    seen_modalities = set()
    modalities_result = []
    for day in days:
        for item in day["required_modalities"]:
            modality = item["modality"]
            if modality not in seen_modalities:
                seen_modalities.add(modality)
                modalities_result.append(modality)

    message = (
        "Прогноз рассчитан по всем доступным исследованиям в БД "
        f"за период {history_start.isoformat()}–{history_end.isoformat()} "
        f"методом '{FORECAST_METHODS[method]}' и построен для диапазона "
        f"{forecast_date_from.isoformat()}–{forecast_date_to.isoformat()}."
    )
    if model_warning:
        message = f"{message} {model_warning}"

    return {
        "date_from": forecast_date_from.isoformat(),
        "date_to": forecast_date_to.isoformat(),
        "history_start_date": history_start.isoformat(),
        "history_end_date": history_end.isoformat(),
        "generated_at": timezone.now().isoformat(),
        "method": method,
        "method_label": FORECAST_METHODS[method],
        "summary": {
            "total_expected_studies": _round_float(sum(item["expected_studies_total"] for item in days), 1),
            "total_expected_up": _round_float(sum(item["expected_up_total"] for item in days), 2),
            "max_min_doctors_per_shift": max((item["min_doctors"] for item in days), default=0),
            "modalities": modalities_result,
        },
        "chart": chart,
        "days": days,
        "message": message,
    }



def _load_actual_day_totals(date_from: date, date_to: date) -> dict[date, dict[str, float]]:
    return _load_daily_totals(date_from, date_to)



def evaluate_forecast_methods(
    *,
    methods: list[str] | None = None,
    evaluation_start_date: date | None = None,
    evaluation_end_date: date | None = None,
    evaluation_days: int = DEFAULT_EVALUATION_DAYS,
    recent_weeks: int = DEFAULT_RECENT_WEEKS,
    moving_window_days: int = DEFAULT_MOVING_WINDOW_DAYS,
    min_train_days: int = DEFAULT_MIN_TRAIN_DAYS,
):
    history_start, history_end = _get_history_bounds()
    if not history_start or not history_end:
        return {
            "history_start_date": None,
            "history_end_date": None,
            "evaluation_start_date": None,
            "evaluation_end_date": None,
            "results": [],
            "message": "Недостаточно исторических исследований для сравнения методов.",
        }

    all_days = list(_daterange(history_start, history_end))
    if len(all_days) <= min_train_days:
        return {
            "history_start_date": history_start.isoformat(),
            "history_end_date": history_end.isoformat(),
            "evaluation_start_date": None,
            "evaluation_end_date": None,
            "results": [],
            "message": "Недостаточно истории для backtest-сравнения методов.",
        }

    resolved_methods = methods or list(FORECAST_COMPARE_METHODS)
    for method in resolved_methods:
        if method not in FORECAST_METHODS:
            raise ValueError(f"Неизвестный метод прогнозирования: {method}")

    if evaluation_start_date is not None or evaluation_end_date is not None:
        if evaluation_start_date is None or evaluation_end_date is None:
            raise ValueError("evaluation_start_date и evaluation_end_date нужно передавать вместе.")
        if evaluation_start_date > evaluation_end_date:
            raise ValueError("evaluation_end_date не может быть раньше evaluation_start_date.")
        if evaluation_start_date < history_start or evaluation_end_date > history_end:
            raise ValueError(
                "Диапазон оценки должен лежать внутри истории: "
                f"{history_start.isoformat()}–{history_end.isoformat()}."
            )
        evaluation_days_list = [
            current_day
            for current_day in all_days
            if evaluation_start_date <= current_day <= evaluation_end_date
        ]
    else:
        evaluation_start_index = max(min_train_days, len(all_days) - evaluation_days)
        evaluation_days_list = all_days[evaluation_start_index:]

    evaluation_start = evaluation_days_list[0]
    evaluation_end = evaluation_days_list[-1]
    actual_totals = _load_actual_day_totals(evaluation_start, evaluation_end)

    results = []
    for method in resolved_methods:
        errors_studies = []
        errors_up = []
        ape_studies = []
        ape_up = []
        day_details = []

        for target_day in evaluation_days_list:
            forecast = build_shift_forecast(
                date_from=target_day,
                date_to=target_day,
                method=method,
                recent_weeks=recent_weeks,
                moving_window_days=moving_window_days,
                history_start_override=history_start,
                history_end_override=history_end,
            )
            day_forecast = forecast["days"][0]
            actual = actual_totals.get(target_day, {"studies_count": 0.0, "total_up": 0.0})

            forecast_studies = float(day_forecast["expected_studies_total"])
            forecast_up = float(day_forecast["expected_up_total"])
            actual_studies = float(actual["studies_count"])
            actual_up = float(actual["total_up"])

            study_error = abs(forecast_studies - actual_studies)
            up_error = abs(forecast_up - actual_up)
            errors_studies.append(study_error)
            errors_up.append(up_error)

            if actual_studies > 0:
                ape_studies.append(study_error / actual_studies)
            if actual_up > 0:
                ape_up.append(up_error / actual_up)

            day_details.append(
                {
                    "date": target_day.isoformat(),
                    "forecast_studies": _round_float(forecast_studies, 1),
                    "actual_studies": _round_float(actual_studies, 1),
                    "forecast_up": _round_float(forecast_up, 2),
                    "actual_up": _round_float(actual_up, 2),
                    "abs_error_studies": _round_float(study_error, 1),
                    "abs_error_up": _round_float(up_error, 2),
                }
            )

        results.append(
            {
                "method": method,
                "method_label": FORECAST_METHODS[method],
                "days_evaluated": len(day_details),
                "mae_studies": _round_float(mean(errors_studies), 2) if errors_studies else 0.0,
                "mae_up": _round_float(mean(errors_up), 2) if errors_up else 0.0,
                "mape_studies_pct": _round_float(100 * mean(ape_studies), 2) if ape_studies else None,
                "mape_up_pct": _round_float(100 * mean(ape_up), 2) if ape_up else None,
                "day_details": day_details,
            }
        )

    results.sort(key=lambda item: (item["mae_up"], item["mae_studies"]))

    return {
        "history_start_date": history_start.isoformat(),
        "history_end_date": history_end.isoformat(),
        "evaluation_start_date": evaluation_start.isoformat(),
        "evaluation_end_date": evaluation_end.isoformat(),
        "results": results,
        "message": (
            "Методы оценены на выбранном диапазоне с использованием всей доступной "
            "истории. Отсортировано по MAE по УП: чем меньше, тем лучше."
        ),
    }
