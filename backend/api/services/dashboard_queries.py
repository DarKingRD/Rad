from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Count, DecimalField, Max, Min, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncDate
from django.utils import timezone

from ..models import Doctor, Study
from .modality_catalog import (
    CT,
    CT_CONTRAST,
    FLUOROGRAPHY,
    MRI,
    MRI_CONTRAST,
    OTHER_MODALITY,
    XRAY,
    normalize_modality_name,
)

REPORT_MAIN_MODALITIES = {
    FLUOROGRAPHY,
    XRAY,
    CT,
    CT_CONTRAST,
    MRI,
    MRI_CONTRAST,
}
REPORT_OTHER_MODALITY = "Прочее"


def parse_dashboard_range(date_from: str | None, date_to: str | None, include_all: bool = False):
    """
    Возвращает (start_dt, end_dt_exclusive).
    Если даты не переданы — текущий месяц до текущего момента.
    """
    if include_all:
        bounds = Study.objects.aggregate(
            min_created=Min("created_at"),
            max_created=Max("created_at"),
        )
        if bounds["min_created"] and bounds["max_created"]:
            start_dt = bounds["min_created"].replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = bounds["max_created"] + timedelta(days=1)
            return start_dt, end_dt

        now = timezone.now()
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now

    if not date_from or not date_to:
        now = timezone.now()
        start_dt = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end_dt = now
        return start_dt, end_dt

    start_dt = datetime.strptime(date_from, "%Y-%m-%d")
    end_dt = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
    return start_dt, end_dt


def get_dashboard_stats_data(start_dt, end_dt):
    """
    Возвращает словарь для DashboardStatsSerializer.
    """
    studies_qs = Study.objects.filter(
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    )

    studies_agg = studies_qs.aggregate(
        total_studies=Count("research_number"),
        completed_studies=Count(
            "research_number",
            filter=Q(status="signed"),
        ),
        pending_studies=Count(
            "research_number",
            filter=Q(diagnostician_id__isnull=True),
        ),
        cito_studies=Count(
            "research_number",
            filter=Q(priority="cito"),
        ),
        asap_studies=Count(
            "research_number",
            filter=Q(priority="asap"),
        ),
        total_up=Sum(
            "study_type__up_value",
            filter=Q(diagnostician_id__isnull=False),
        ),
    )

    active_doctors = (
        Doctor.objects.filter(
            studies__created_at__gte=start_dt,
            studies__created_at__lt=end_dt,
        )
        .distinct()
        .count()
    )

    total_up = studies_agg["total_up"] or Decimal("0")
    avg_load = int(total_up / active_doctors) if active_doctors > 0 else 0
    doctor_performance = get_doctor_performance_data(studies_qs)
    modality_breakdown = get_modality_breakdown_data(studies_qs)
    daily_up_values = [
        item["daily_up"]
        for item in get_completed_daily_up_by_doctor(studies_qs)
        if item["daily_up"] is not None
    ]

    return {
        "total_studies": studies_agg["total_studies"] or 0,
        "completed_studies": studies_agg["completed_studies"] or 0,
        "pending_studies": studies_agg["pending_studies"] or 0,
        "active_doctors": active_doctors,
        "avg_load_per_doctor": avg_load,
        "cito_studies": studies_agg["cito_studies"] or 0,
        "asap_studies": studies_agg["asap_studies"] or 0,
        "doctor_daily_up_stats": {
            "median": round(float(median(daily_up_values)), 3) if daily_up_values else 0,
            "min": round(float(min(daily_up_values)), 3) if daily_up_values else 0,
            "max": round(float(max(daily_up_values)), 3) if daily_up_values else 0,
        },
        "doctor_performance": doctor_performance,
        "modality_breakdown": modality_breakdown,
    }


def get_completed_daily_up_by_doctor(studies_qs):
    """
    Возвращает дневную УП-нагрузку по врачам для выполненных исследований.
    В выборку попадают только дни, где у врача были подписанные исследования.
    """
    return (
        studies_qs.filter(status="signed", diagnostician_id__isnull=False)
        .annotate(day=TruncDate("created_at"))
        .values("diagnostician_id", "day")
        .annotate(daily_up=Sum("study_type__up_value"))
        .order_by("diagnostician_id", "day")
    )


def get_doctor_performance_data(studies_qs):
    """
    Возвращает выполненные исследования и УП по каждому врачу.
    Врачи без выполненных исследований остаются в отчете с нулевыми значениями.
    """
    completed_by_doctor = {
        item["diagnostician_id"]: item
        for item in studies_qs.filter(status="signed", diagnostician_id__isnull=False)
        .values("diagnostician_id")
        .annotate(
            completed_studies=Count("research_number"),
            completed_up=Sum("study_type__up_value"),
        )
    }
    daily_up_by_doctor = defaultdict(list)
    for item in get_completed_daily_up_by_doctor(studies_qs):
        daily_up_by_doctor[item["diagnostician_id"]].append(
            float(item["daily_up"] or 0)
        )

    doctors = Doctor.objects.all().order_by("fio_alias", "id")
    rows = []
    for doctor in doctors:
        stats = completed_by_doctor.get(doctor.id, {})
        daily_values = daily_up_by_doctor.get(doctor.id, [])
        completed_up = float(stats.get("completed_up") or 0)
        rows.append(
            {
                "doctor_id": doctor.id,
                "doctor_name": doctor.fio_alias or f"Врач {doctor.id}",
                "completed_studies": stats.get("completed_studies", 0) or 0,
                "completed_up": round(completed_up, 3),
                "completed_days": len(daily_values),
                "avg_up_per_day": (
                    round(completed_up / len(daily_values), 3)
                    if daily_values
                    else 0
                ),
                "median_up_per_day": (
                    round(float(median(daily_values)), 3) if daily_values else 0
                ),
                "min_daily_completed_up": (
                    round(min(daily_values), 3) if daily_values else 0
                ),
                "max_daily_completed_up": (
                    round(max(daily_values), 3) if daily_values else 0
                ),
            }
        )

    return sorted(
        rows,
        key=lambda item: (
            -item["completed_studies"],
            -item["completed_up"],
            item["doctor_name"],
        ),
    )


def get_modality_breakdown_data(studies_qs):
    """
    Возвращает управленческую сводку по основным модальностям.
    Считаем весь поток, выполненный поток, очередь и УП внутри выбранного периода.
    """
    total_studies = studies_qs.count()
    rows = (
        studies_qs.values("study_type__modality")
        .annotate(
            studies_count=Count("research_number"),
            completed_studies=Count("research_number", filter=Q(status="signed")),
            pending_studies=Count("research_number", filter=Q(diagnostician_id__isnull=True)),
            total_up=Coalesce(
                Sum("study_type__up_value"),
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            ),
            completed_up=Coalesce(
                Sum("study_type__up_value", filter=Q(status="signed")),
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=12, decimal_places=3),
            ),
        )
    )

    grouped_result: dict[str, dict] = {}
    for row in rows:
        normalized_modality = normalize_modality_name(row["study_type__modality"])
        modality = (
            normalized_modality
            if normalized_modality in REPORT_MAIN_MODALITIES
            else REPORT_OTHER_MODALITY
        )
        if normalized_modality == OTHER_MODALITY:
            modality = REPORT_OTHER_MODALITY

        studies_count = int(row["studies_count"] or 0)
        completed_studies = int(row["completed_studies"] or 0)
        pending_studies = int(row["pending_studies"] or 0)
        total_up = float(row["total_up"] or 0)
        completed_up = float(row["completed_up"] or 0)

        current = grouped_result.setdefault(
            modality,
            {
                "modality": modality,
                "studies_count": 0,
                "completed_studies": 0,
                "pending_studies": 0,
                "total_up": 0.0,
                "completed_up": 0.0,
                "share_percent": 0.0,
                "completion_rate_percent": 0.0,
            },
        )
        current["studies_count"] += studies_count
        current["completed_studies"] += completed_studies
        current["pending_studies"] += pending_studies
        current["total_up"] += total_up
        current["completed_up"] += completed_up

    result = []
    for item in grouped_result.values():
        studies_count = item["studies_count"]
        completed_studies = item["completed_studies"]
        item["total_up"] = round(item["total_up"], 3)
        item["completed_up"] = round(item["completed_up"], 3)
        item["share_percent"] = round((studies_count / total_studies) * 100, 2) if total_studies else 0
        item["completion_rate_percent"] = (
            round((completed_studies / studies_count) * 100, 2) if studies_count else 0
        )
        result.append(item)

    return sorted(
        result,
        key=lambda item: (
            -item["studies_count"],
            -item["total_up"],
            item["modality"],
        ),
    )


def get_chart_data(start_date, end_date):
    """
    Возвращает список точек графика по дням.
    Делает один grouped query вместо запросов в цикле.
    """
    grouped = (
        Study.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            plan=Count("research_number"),
            actual=Count("research_number", filter=Q(status="signed")),
        )
        .order_by("day")
    )

    grouped_map = {
        item["day"]: {
            "plan": item["plan"],
            "actual": item["actual"],
        }
        for item in grouped
    }

    result = []
    current_date = start_date

    while current_date <= end_date:
        day_data = grouped_map.get(current_date, {"plan": 0, "actual": 0})
        result.append(
            {
                "name": current_date.strftime("%d.%m"),
                "plan": day_data["plan"],
                "actual": day_data["actual"],
            }
        )
        current_date += timedelta(days=1)

    return result
