from django.db.models import Case, IntegerField, QuerySet, When

from ..models import Study


PRIORITY_ORDER = Case(
    When(priority="cito", then=0),
    When(priority="asap", then=1),
    When(priority="normal", then=2),
    default=99,
    output_field=IntegerField(),
)


def get_pending_studies_queryset() -> QuerySet[Study]:
    return (
        Study.objects.filter(diagnostician_id__isnull=True)
        .select_related("study_type", "diagnostician")
        .order_by(PRIORITY_ORDER, "created_at")
    )


def get_priority_studies_queryset(priority: str) -> QuerySet[Study]:
    return (
        Study.objects.filter(priority=priority)
        .select_related("study_type", "diagnostician")
        .order_by("created_at")
    )
