from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from ..models import Doctor, Study


def parse_dashboard_range(date_from: str | None, date_to: str | None):
    """
    Возвращает (start_dt, end_dt_exclusive).
    Если даты не переданы — текущий месяц до текущего момента.
    """
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

    return {
        "total_studies": studies_agg["total_studies"] or 0,
        "completed_studies": studies_agg["completed_studies"] or 0,
        "pending_studies": studies_agg["pending_studies"] or 0,
        "active_doctors": active_doctors,
        "avg_load_per_doctor": avg_load,
        "cito_studies": studies_agg["cito_studies"] or 0,
        "asap_studies": studies_agg["asap_studies"] or 0,
    }


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
