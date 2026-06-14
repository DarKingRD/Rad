from datetime import date as date_class, datetime
from decimal import Decimal

from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Doctor, Schedule, Study

MONTHLY_NORM = 50
DAILY_NORM = 8


def format_time_hhmm(value):
    return value.strftime("%H:%M") if value else None


def get_break_duration_minutes(schedule) -> int:
    if not schedule or not schedule.break_start or not schedule.break_end:
        return 0

    break_start_dt = datetime.combine(date_class.today(), schedule.break_start)
    break_end_dt = datetime.combine(date_class.today(), schedule.break_end)
    delta_seconds = (break_end_dt - break_start_dt).total_seconds()

    return int(delta_seconds // 60) if delta_seconds > 0 else 0


def get_daily_limit(doctor: Doctor) -> int:
    """
    Дневной лимит УП.
    По текущей бизнес-логике проекта оставляем 8 УП в день.
    """
    if doctor.max_up_per_day:
        return int(doctor.max_up_per_day)
    return DAILY_NORM


def get_doctor_specialty(doctor: Doctor) -> str:
    if doctor.position_type == "radiologist":
        return "Рентгенолог"
    if doctor.position_type == "diagnostician":
        return "КТ-диагност"
    return doctor.position_type or ""


def get_doctors_with_load_context():
    now = timezone.now()
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if now.month == 12:
        month_end = now.replace(year=now.year + 1, month=1, day=1)
    else:
        month_end = now.replace(month=now.month + 1, day=1)

    completed_load_subquery = (
        Study.objects.filter(
            diagnostician_id=OuterRef("pk"),
            created_at__gte=month_start,
            created_at__lt=month_end,
            status="signed",
        )
        .values("diagnostician_id")
        .annotate(total=Sum("study_type__up_value"))
        .values("total")[:1]
    )

    doctors_qs = (
        Doctor.objects.all()
        .annotate(
            current_load=Coalesce(
                Subquery(
                    completed_load_subquery,
                    output_field=DecimalField(max_digits=10, decimal_places=3),
                ),
                Value(Decimal("0.000")),
                output_field=DecimalField(max_digits=10, decimal_places=3),
            ),
            active_studies=Count(
                "studies",
                filter=Q(
                    studies__created_at__gte=month_start,
                    studies__created_at__lt=month_end,
                    studies__status__in=["confirmed", "pending"],
                ),
                distinct=True,
            ),
        )
    )

    today_schedules = {
        schedule.doctor_id: schedule
        for schedule in Schedule.objects.filter(work_date=today, is_day_off=0).only(
            "doctor_id",
            "time_start",
            "time_end",
            "break_start",
            "break_end",
        )
    }

    return doctors_qs, today_schedules
