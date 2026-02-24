"""
Модуль административной панели Django.

Содержит регистрации моделей для управления через админку Django.
Позволяет администраторам просматривать, создавать, редактировать и удалять
записи в базе данных для всех основных сущностей системы.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Doctor, StudyType, Schedule, Study


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    """
    Настройка админки для модели Врач.
    """
    list_display = ('id', 'fio_alias', 'position_type', 'max_up_per_day', 'is_active', 'get_modality_count')
    list_display_links = ('id', 'fio_alias')
    list_filter = ('is_active', 'position_type', 'modality')
    search_fields = ('fio_alias', 'id', 'position_type')
    list_editable = ('is_active',)
    readonly_fields = ('id',)
    
    # Оптимизация: если бы были связи, использовали бы list_select_related
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('id', 'fio_alias', 'position_type', 'is_active')
        }),
        ('Параметры работы', {
            'fields': ('max_up_per_day', 'modality')
        }),
    )

    @admin.display(description='Кол-во модальностей')
    def get_modality_count(self, obj):
        return len(obj.modality) if obj.modality else 0


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
    list_display = ('id', 'doctor', 'work_date', 'time_start', 'time_end', 'is_day_off_status', 'planned_up')
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
    list