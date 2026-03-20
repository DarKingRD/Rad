from datetime import datetime
import uuid

from django.core.cache import cache
from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from ..models import Doctor, Schedule, Study
from .distribution import DistributionService

PREVIEW_CACHE_TIMEOUT = 3600
PREVIEW_CACHE_PREFIX = "distribution_preview_"


def preview_cache_key(distribution_id: str) -> str:
    return f"{PREVIEW_CACHE_PREFIX}{distribution_id}"


def parse_distribution_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_distribution_datetime_start(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def parse_distribution_datetime_end(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")


def get_distribution_info(target_date=None):
    target_date = target_date or timezone.now().date()

    date_range = Study.objects.aggregate(
        min_date=Min("created_at__date"),
        max_date=Max("created_at__date"),
    )

    schedule_range = Schedule.objects.aggregate(
        min_date=Min("work_date"),
        max_date=Max("work_date"),
    )

    pending = Study.objects.filter(diagnostician__isnull=True).count()

    doctors = (
        Doctor.objects.filter(
            is_active=True,
            schedule__work_date=target_date,
            schedule__is_day_off=0,
        )
        .distinct()
        .count()
    )

    return {
        "pending_studies": pending,
        "available_doctors": doctors,
        "study_date_range": {
            "min": date_range["min_date"].isoformat() if date_range["min_date"] else None,
            "max": date_range["max_date"].isoformat() if date_range["max_date"] else None,
        },
        "schedule_date_range": {
            "min": schedule_range["min_date"].isoformat() if schedule_range["min_date"] else None,
            "max": schedule_range["max_date"].isoformat() if schedule_range["max_date"] else None,
        },
        "message": "Отправьте POST-запрос с параметром date для распределения",
    }


def get_distribution_preview_info(target_date):
    pending = Study.objects.filter(
        diagnostician__isnull=True,
        created_at__date__lte=target_date,
    ).count()

    doctors = (
        Doctor.objects.filter(
            is_active=True,
            schedule__work_date=target_date,
            schedule__is_day_off=0,
        )
        .distinct()
        .count()
    )

    return {
        "pending_studies": pending,
        "available_doctors": doctors,
        "target_date": target_date.isoformat(),
        "message": "Готов к распределению" if pending > 0 and doctors > 0 else "Нет данных",
    }


def run_distribution(*, target_date=None, preview=True, date_from=None, date_to=None, use_mip=True):
    service = DistributionService(target_date=target_date)
    service.set_preview_mode(preview)

    result = service.distribute(
        use_mip=use_mip,
        date_from=date_from,
        date_to=date_to,
    )

    if preview:
        distribution_id = str(uuid.uuid4())
        cache.set(
            preview_cache_key(distribution_id),
            result,
            timeout=PREVIEW_CACHE_TIMEOUT,
        )
        result["distribution_id"] = distribution_id
        result["message"] = (
            "Предварительное распределение выполнено. "
            "Отправьте POST на /api/distribute/confirm/ для сохранения."
        )

    return result


@transaction.atomic
def confirm_distribution_result(distribution_id: str):
    preview_data = cache.get(preview_cache_key(distribution_id))
    if not preview_data:
        return None

    assignments = preview_data.get("assignments", [])
    assignment_dict = {
        item.get("study_number"): item["doctor_id"]
        for item in assignments
        if item.get("study_number") and item.get("doctor_id") is not None
    }

    if assignment_dict:
        studies = list(
            Study.objects.filter(research_number__in=assignment_dict.keys())
        )

        for study in studies:
            doctor_id = assignment_dict.get(study.research_number)
            if doctor_id is not None:
                study.diagnostician_id = doctor_id
                study.status = "confirmed"

        Study.objects.bulk_update(studies, ["diagnostician_id", "status"])

    cache.delete(preview_cache_key(distribution_id))

    return {
        "status": "confirmed",
        "assigned": len(assignment_dict),
        "distribution_id": distribution_id,
        "message": f"Успешно сохранено {len(assignment_dict)} назначений",
    }
