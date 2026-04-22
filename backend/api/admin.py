"""
Модуль административной панели Django.
"""
from django.contrib import admin

from .models import Doctor, Schedule, Study, StudyType
from .services.schedule_status import get_day_status_label


class ModalityListFilter(admin.SimpleListFilter):
    title = "Модальность"
    parameter_name = "modality"

    def lookups(self, request, model_admin):
        modalities = set()
        queryset = model_admin.get_queryset(request)
        for doctor in queryset:
            modalities.update(doctor.modality or [])
        return [(mod, mod) for mod in sorted(modalities)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.extra(
                where=["modality @> ARRAY[%s]::text[]"],
                params=[self.value()],
            )
        return queryset


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "fio_alias", "position_type", "modality", "max_up_per_day", "is_active")
    list_display_links = ("id", "fio_alias")
    list_filter = ("is_active", "position_type", ModalityListFilter)
    search_fields = ("fio_alias", "id", "position_type")


@admin.register(StudyType)
class StudyTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "modality", "up_value")
    list_display_links = ("id", "name")
    search_fields = ("name", "modality", "id")
    list_filter = ("modality",)
    readonly_fields = ("id",)


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "doctor",
        "work_date",
        "day_status",
        "day_status_label",
        "time_start",
        "time_end",
        "is_day_off_status",
        "planned_up",
    )
    list_display_links = ("id", "doctor")
    list_filter = ("day_status", "is_day_off", "doctor", "work_date")
    search_fields = ("doctor__fio_alias", "id")
    date_hierarchy = "work_date"
    readonly_fields = ("id",)
    list_select_related = ("doctor",)

    @admin.display(description="Статус графика")
    def day_status_label(self, obj):
        return get_day_status_label(getattr(obj, "day_status", 0))

    @admin.display(description="Нерабочий день", boolean=True)
    def is_day_off_status(self, obj):
        return bool(obj.is_day_off)


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    list_display = ("research_number", "study_type", "diagnostician", "created_at", "planned_at", "status", "study_modality")
    list_display_links = ("research_number", "study_type")
    search_fields = ("research_number", "diagnostician__fio_alias")
    list_filter = ("study_type__modality", "status", "priority")
    date_hierarchy = "created_at"
    readonly_fields = ("research_number", "created_at")
    list_select_related = ("study_type", "diagnostician")
    list_per_page = 100

    @admin.display(description="Модальность")
    def study_modality(self, obj):
        if not obj.study_type:
            return "—"
        return obj.study_type.modality
