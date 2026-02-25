"""
Модуль для определения моделей базы данных приложения.

Этот модуль содержит модели Django, представляющие основные сущности системы:
- Doctor: Представляет медицинского работника с его атрибутами и возможностями.
- StudyType: Определяет типы медицинских исследований с соответствующими 
модальностями и значениями УП.
- Schedule: Управляет расписанием врачей, включая рабочие часы и выходные дни.
- Study: Представляет отдельные медицинские исследования со статусом, приоритетом и назначениями.

Каждая модель соответствует определённой таблице базы данных и включает соответствующие поля
и метаданные для интеграции с существующей схемой базы данных.
"""

from django.db import models
from django.contrib.postgres.fields import ArrayField

class Doctor(models.Model):
    """
    Модель врача.

    Представляет медицинского работника с его основными атрибутами:
    - id: Уникальный идентификатор врача
    - fio_alias: ФИО диагноста
    - position_type: Должность врача
    - max_up_per_day: Максимальное количество УП (условных пунктов) в день
    - is_active: Статус активности врача
    - modality: Список модальностей, в которых работает врач

    Модель привязана к таблице 'doctors' в базе данных.
    """
    id = models.IntegerField(primary_key=True, verbose_name="Идентификатор врача")
    fio_alias = models.CharField(
        max_length=255, blank=True, null=True, verbose_name="ФИО диагноста"
    )
    position_type = models.CharField(
        max_length=50, blank=True, null=True, verbose_name="Должность"
    )
    max_up_per_day = models.IntegerField(
        default=120, blank=True, null=True, verbose_name="Максимально УП в день"
    )
    is_active = models.BooleanField(
        default=True, blank=True, null=True, verbose_name="Статус активности"
    )
    modality = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        verbose_name="Модальности",
    )

    class Meta:
        db_table = "doctors"
        managed = False

    def __str__(self):
        return str(self.fio_alias) if self.fio_alias else f"Doctor {self.id}"


class StudyType(models.Model):
    """
    Модель типа исследования.

    Определяет виды медицинских исследований с их характеристиками:
    - id: Уникальный идентификатор типа исследования
    - name: Название вида исследования
    - modality: Модальность исследования (массив для совместимости)
    - up_value: Количество условных пунктов (УП) за выполнение исследования

    Модель привязана к таблице 'study_types' в базе данных.
    """
    id = models.IntegerField(
        primary_key=True, verbose_name="Идентификатор типа исследований"
    )
    name = models.CharField(
        max_length=500, blank=True, null=True, verbose_name="Название вида исследования"
    )
    modality = ArrayField(
        models.CharField(max_length=50),
        blank=True,
        default=list,
        verbose_name="Модальности",
    )
    up_value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="УП за исследование",
    )

    class Meta:
        db_table = "study_types"
        managed = False

    def __str__(self):
        return str(f"{self.id} - {self.name}" if self.name else f"StudyType {self.id}")


class Schedule(models.Model):
    """
    Модель расписания врача.

    Управляет рабочим расписанием врачей:
    - id: Уникальный идентификатор расписания
    - doctor: Врач, для которого составлено расписание
    - work_date: Дата работы
    - time_start: Время начала работы
    - time_end: Время окончания работы
    - is_day_off: Статус выходного дня (0 - рабочий день, 1 - выходной)
    - planned_up: Планируемое количество УП на день

    Модель привязана к таблице 'schedules' в базе данных.
    Расписания упорядочены по дате и времени начала работы.
    """
    id = models.IntegerField(primary_key=True, verbose_name="Идентификатор расписания")
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
    is_day_off = models.IntegerField(
        default=0, blank=True, null=True, verbose_name="Статус выходного"
    )
    planned_up = models.IntegerField(blank=True, null=True, verbose_name="План УП")

    class Meta:
        db_table = "schedules"
        managed = False
        ordering = ["work_date", "time_start"]

    def __str__(self):
        return f"Schedule {self.id} - {self.work_date}"


class Study(models.Model):
    """
    Модель исследования.

    Представляет отдельное медицинское исследование с его параметрами:
    - id: Уникальный идентификатор исследования
    - research_number: Уникальный номер исследования
    - study_type: Тип исследования
    - status: Статус исследования
    - priority: Приоритет исследования (normal, cito, asap)
    - created_at: Дата и время создания записи об исследовании
    - planned_at: Плановая дата и время проведения исследования
    - diagnostician: Диагност, назначенный для выполнения исследования

    Модель привязана к таблице 'studies' в базе данных.
    Исследования упорядочены по дате создания (сначала новые).
    """
    id = models.IntegerField(
        primary_key=True, verbose_name="Идентификатор исследования"
    )
    research_number = models.CharField(
        max_length=50, unique=True, verbose_name="Номер исследования"
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
        max_length=50, blank=True, null=True, verbose_name="Статус исследования",
        choices=[
            ("pending", "Ожидает назначения"),
            ("confirmed", "Назначено"),
            ("signed", "Выполнено")
        ]
    )
    priority = models.CharField(
        max_length=20,
        default="normal",
        blank=True,
        null=True,
        verbose_name="Приоритет исследования",
        choices=[
            ("normal", "Нормальный"),
            ("cito", "Cito"),
            ("asap", "Asap")
        ]
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

    class Meta:
        db_table = "studies"
        managed = False
        ordering = ["-created_at"]

    def __str__(self):
        return self.research_number
