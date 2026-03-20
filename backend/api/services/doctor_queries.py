from datetime import datetime, date as date_class
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..models import Doctor, Schedule

MONTHLY_NORM = 50


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
    if doctor.max_up_per_day:
        return doctor.max_up_per_day
    return 6 if doctor.position_type == "head" else 8


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

    doctors_qs = (
        Doctor.objects.all()
        .annotate(
            current_load=Coalesce(
                Sum(
                    "studies__study_type__up_value",
                    filter=Q(
                        studies__created_at__gte=month_start,
                        studies__created_at__lt=month_end,
                        studies__status__in=["confirmed", "pending", "signed"],
                    ),
                ),
                Value(Decimal("0.00")),
                output_field=DecimalField(max_digits=10, decimal_places=2),
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