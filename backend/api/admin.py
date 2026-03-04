"""
Модуль административной панели Django.

Содержит регистрации моделей для управления через админку Django.
Позволяет администраторам просматривать, создавать, редактировать и удалять
записи в базе данных для всех основных сущностей системы.
"""
from django.contrib import admin
from .models import Doctor, StudyType, Schedule, Study


class ModalityListFilter(admin.SimpleListFilter):
    title = 'Модальность'
    parameter_name = 'modality'

    def lookups(self, request, model_admin):
        modalities = set()
        queryset = model_admin.get_queryset(request)
        for doctor in queryset:
            modalities.update(doctor.modality)
        return [(mod, mod) for mod in sorted(modalities)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.extra(
                where=["modality @> ARRAY[%s]::text[]"],
                params=[self.value()]
            )
        return queryset

@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    """
    Настройка админки для модели Врач.
    """
    list_display = ('id', 'fio_alias', 'position_type', 'modality', 'max_up_per_day', 'is_active')
    list_display_links = ('id', 'fio_alias')
    list_filter = ('is_active', 'position_type', ModalityListFilter)
    search_fields = ('fio_alias', 'id', 'position_type')


    def modality_filter(self, obj) -> str:
        return ", ".join(obj.modality)

@admin.register(StudyType)
class StudyTypeAdmin(admin.ModelAdmin):
    """
    Настройка админки для типов исследований.
    """
    list_display = ('id', 'name', 'modality', 'up_value')
    list_display_links = ('id', 'name')
    search_fields = ('name', 'modality', 'id')
    list_filter = ('modality',)
    readonly_fields = ('id',)


@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    """
    Настройка админки для расписания.
    Важно: используем date_hierarchy для удобной навигации по датам.
    """
    list_display = ('id', 'doctor', 'work_date', 'time_start',
                    'time_end', 'is_day_off_status', 'planned_up')
    list_display_links = ('id', 'doctor')
    list_filter = ('is_day_off', 'doctor', 'work_date')
    search_fields = ('doctor__fio_alias', 'id')
    date_hierarchy = 'work_date'
    readonly_fields = ('id',)
    
    # Оптимизация запросов: сразу забираем данные врача, чтобы не было N+1 запроса
    list_select_related = ('doctor',)

    @admin.display(description='Статус дня', boolean=True)
    def is_day_off_status(self, obj):
        return bool(obj.is_day_off)


@admin.register(Study)
class StudyAdmin(admin.ModelAdmin):
    """
    Настройка админки для исследований.
    Самая нагруженная модель, поэтому важно настроить фильтры и поиск.
    """
    list_display = ('research_number', 'study_type', 'diagnostician', 
                    'created_at', 'planned_at', 'status', 'study_type__modality')
    list_display_links = ('research_number', 'study_type')
    search_fields = ('research_number', 'doctor__fio_alias')
    list_filter = ('study_type__modality', 'status', 'priority',)
    date_hierarchy = 'created_at'
    readonly_fields = ('research_number', 'created_at')
    list_select_related = ('study_type', 'diagnostician')
    list_per_page = 100
