"""
Модуль для определения моделей базы данных приложения.

Этот модуль содержит модели Django, представляющие основные сущности системы:
- Doctor: Представляет медицинского работника с его атрибутами и возможностями.
- StudyType: Определяет типы медицинских исследований с соответствующими
  модальностями и значениями УП.
- Schedule: Управляет расписанием врачей, включая рабочие часы и выходные дни.
- Study: Представляет отдельные медицинские исследования со статусом, приоритетом и назначениями.
"""
from typing import TYPE_CHECKING

from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models.manager import Manager


MANAGED = True


class Doctor(models.Model):
    """
    Модель врача.

    max_up_per_day хранит дневной лимит УП. По текущей логике проекта
    оставляем 8 УП в день как рабочее значение по умолчанию.
    """

    id = models.IntegerField(primary_key=True, verbose_name="Идентификатор врача")
    fio_alias = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="ФИО диагноста"
    )
    position_type = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Должность"
    )
    max_up_per_day = models.IntegerField(
        default=8, blank=True, null=True, verbose_name="Максимально УП в день"
    )
    is_active = models.BooleanField(
        default=True, blank=True, null=True, verbose_name="Статус активности"
    )
    modality = ArrayField(
        models.CharField(max_length=255),
        blank=True,
        default=list,
        verbose_name="Модальности",
    )

    if TYPE_CHECKING:
        objects: Manager["Doctor"]

    class Meta:
        db_table = "doctors"
        managed = MANAGED
        verbose_name = "Врач"
        verbose_name_plural = "Врачи"
        indexes = [
            models.Index(fields=["fio_alias"], name="doctor_fio_idx"),
            models.Index(fields=["position_type"], name="doctor_position_idx"),
            models.Index(fields=["is_active"], name="doctor_active_idx"),
            GinIndex(fields=["modality"], name="doctor_modality_gin_idx"),
        ]

    def __str__(self):
        return str(self.fio_alias) if self.fio_alias else f"Doctor {self.id}"


class StudyType(models.Model):
    """
    Модель типа исследования.
    """

    id = models.IntegerField(
        primary_key=True, verbose_name="Идентификатор типа исследований"
    )
    name = models.CharField(
        max_length=500, blank=True, null=True, verbose_name="Название вида исследования"
    )
    modality = models.CharField(max_length=255, verbose_name="Модальность")
    up_value = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        blank=True,
        null=True,
        verbose_name="УП за исследование",
    )

    if TYPE_CHECKING:
        objects: Manager["StudyType"]

    class Meta:
        db_table = "study_types"
        managed = MANAGED
        verbose_name = "Тип исследования"
        verbose_name_plural = "Типы исследований"
        indexes = [
            models.Index(fields=["modality"], name="studytype_modality_idx"),
            models.Index(fields=["name"], name="studytype_name_idx"),
        ]

    def __str__(self):
        return str(f"{self.id} - {self.name}" if self.name else f"StudyType {self.id}")


class Schedule(models.Model):
    """
    Модель расписания врача.
    """

    id = models.AutoField(primary_key=True, verbose_name="Идентификатор расписания")
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        db_column="doctor_id",
        blank=True,
        null=True,
        verbose_name="Врач",
    )
    work_date = models.DateField(blank=True, null=True, verbose_name="Дата")
    time_start = models.TimeField(blank=True, null=True, verbose_name="Начало работы")
    time_end = models.TimeField(blank=True, null=True, verbose_name="Конец работы")
    break_start = models.TimeField(blank=True, null=True, verbose_name="Начало перерыва")
    break_end = models.TimeField(blank=True, null=True, verbose_name="Конец перерыва")
    is_day_off = models.IntegerField(
        default=0, blank=True, null=True, verbose_name="Признак нерабочего дня"
    )
    day_status = models.IntegerField(
        default=0,
        blank=True,
        null=True,
        verbose_name="Исходный статус дня из графика",
    )
    planned_up = models.IntegerField(blank=True, null=True, verbose_name="План УП")

    if TYPE_CHECKING:
        objects: Manager["Schedule"]

    class Meta:
        db_table = "schedules"
        managed = MANAGED
        ordering = ["work_date", "time_start"]
        verbose_name = "Расписание"
        verbose_name_plural = "Расписания"
        indexes = [
            models.Index(fields=["doctor", "work_date"], name="schedule_doctor_date_idx"),
            models.Index(fields=["work_date", "time_start"], name="schedule_date_time_idx"),
            models.Index(fields=["doctor", "work_date", "is_day_off"], name="schedule_doc_date_dayoff_idx"),
            models.Index(fields=["work_date", "day_status"], name="schedule_date_status_idx"),
        ]

    def __str__(self):
        return f"Schedule {self.id} - {self.work_date}"


class Study(models.Model):
    """
    Модель исследования.
    """

    research_number = models.CharField(
        max_length=50, primary_key=True, verbose_name="Номер исследования"
    )
    study_type = models.ForeignKey(
        StudyType,
        on_delete=models.CASCADE,
        db_column="study_type_id",
        blank=True,
        null=True,
        verbose_name="Тип исследования",
    )
    status = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Статус исследования",
        choices=[
            ("pending", "Ожидает назначения"),
            ("confirmed", "Назначено"),
            ("signed", "Выполнено"),
        ],
    )
    priority = models.CharField(
        max_length=20,
        default="normal",
        blank=True,
        null=True,
        verbose_name="Приоритет исследования",
        choices=[("normal", "Нормальный"), ("cito", "Cito"), ("asap", "Asap")],
    )
    created_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Дата создания"
    )
    planned_at = models.DateTimeField(
        blank=True, null=True, verbose_name="Плановая дата исследования"
    )
    diagnostician = models.ForeignKey(
        Doctor,
        on_delete=models.CASCADE,
        db_column="diagnostician_id",
        blank=True,
        null=True,
        related_name="studies",
        verbose_name="Диагност",
    )

    if TYPE_CHECKING:
        objects: Manager["Study"]

    class Meta:
        db_table = "studies"
        managed = MANAGED
        ordering = ["-created_at"]
        verbose_name = "Исследование"
        verbose_name_plural = "Исследования"
        indexes = [
            models.Index(fields=["status"], name="study_status_idx"),
            models.Index(fields=["priority"], name="study_priority_idx"),
            models.Index(fields=["created_at"], name="study_created_idx"),
            models.Index(fields=["planned_at"], name="study_planned_idx"),
            models.Index(fields=["diagnostician", "status"], name="study_diag_status_idx"),
            models.Index(fields=["status", "planned_at"], name="study_status_planned_idx"),
            models.Index(
                fields=["created_at"],
                name="study_unasg_created_idx",
                condition=Q(diagnostician__isnull=True),
            ),
            models.Index(
                fields=["priority", "created_at"],
                name="study_unasg_prio_cr_idx",
                condition=Q(diagnostician__isnull=True),
            ),
        ]

    def __str__(self):
        return self.research_number
