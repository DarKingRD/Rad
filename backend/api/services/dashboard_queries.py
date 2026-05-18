from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Count, Max, Min, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from ..models import Doctor, Study


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
