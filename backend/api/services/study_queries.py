from datetime import datetime, timedelta

from django.db.models import Case, IntegerField, QuerySet, When
from django.utils import timezone

from ..models import Study


PRIORITY_ORDER = Case(
    When(priority="cito", then=0),
    When(priority="asap", then=1),
    When(priority="normal", then=2),
    default=99,
    output_field=IntegerField(),
)


def _date_start(value: str):
    parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return timezone.make_aware(datetime.combine(parsed, datetime.min.time()))


def _date_exclusive_end(value: str):
    return _date_start(value) + timedelta(days=1)


def get_pending_studies_queryset(
    *,
    priority: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    modality: str | None = None,
) -> QuerySet[Study]:
    qs = Study.objects.filter(diagnostician_id__isnull=True)
    if priority:
        qs = qs.filter(priority=priority)
    if date_from:
        qs = qs.filter(created_at__gte=_date_start(date_from))
    if date_to:
        qs = qs.filter(created_at__lt=_date_exclusive_end(date_to))
    if modality:
        qs = qs.filter(study_type__name__icontains=modality)
    return (
        qs
            .select_related("study_type", "diagnostician")
            .order_by(PRIORITY_ORDER, "created_at")
    )


def get_priority_studies_queryset(priority: str) -> QuerySet[Study]:
    return (
        Study.objects.filter(priority=priority)
        .select_related("study_type", "diagnostician")
        .order_by("created_at")
    )
