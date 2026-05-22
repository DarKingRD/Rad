from __future__ import annotations

from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from api.models import Doctor, Schedule, Study, StudyType
from api.services.modality_catalog import (
    CT,
    CT_CONTRAST,
    ECG,
    MRI,
    XRAY,
    get_modality_up_value,
)


DEMO_DOCTOR_ID_START = 910001
DEMO_STUDY_TYPE_ID_START = 920001
DEMO_RESEARCH_PREFIX = "DEMO-"

DEMO_DOCTORS = [
    ("Кашлев А.С.", "Врач-рентгенолог", [XRAY, CT]),
    ("Воробьева Е.А.", "Врач-рентгенолог", [XRAY, CT, CT_CONTRAST]),
    ("Зеленова М.А.", "Врач-рентгенолог", [MRI, CT]),
    ("Островская Е.В.", "Врач функциональной диагностики", [ECG, XRAY]),
    ("Миронов П.Д.", "Врач-рентгенолог", [MRI, CT_CONTRAST]),
    ("Соколова Н.И.", "Врач-рентгенолог", [XRAY, MRI]),
]

DEMO_STUDY_TYPES = [
    ("Рентгенография органов грудной клетки", XRAY),
    ("Рентгенография костей и суставов", XRAY),
    ("Компьютерная томография головного мозга", CT),
    ("КТ органов грудной клетки с контрастом", CT_CONTRAST),
    ("МРТ головного мозга", MRI),
    ("Электрокардиография", ECG),
]

PRIORITY_PATTERN = [
    "normal",
    "normal",
    "asap",
    "normal",
    "cito",
    "normal",
    "asap",
    "normal",
    "normal",
    "cito",
    "normal",
    "asap",
]


class Command(BaseCommand):
    help = "Создает демонстрационные данные на несколько дней для показа работы системы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-date",
            help="Первый день демо-периода в формате YYYY-MM-DD. По умолчанию сегодня.",
        )
        parser.add_argument(
            "--days",
            type=int,
            default=4,
            help="Количество дней демо-периода. По умолчанию 4.",
        )
        parser.add_argument(
            "--studies-per-day",
            type=int,
            default=45,
            help="Сколько ожидающих исследований создать на каждый день. По умолчанию 45.",
        )

    def handle(self, *args, **options):
        days = max(1, int(options["days"]))
        studies_per_day = max(1, int(options["studies_per_day"]))
        start_date = self._parse_start_date(options.get("start_date"))

        with transaction.atomic():
            self._clear_previous_demo()
            doctors = self._create_doctors()
            study_types = self._create_study_types()
            schedules_count = self._create_schedules(doctors, start_date, days)
            studies_count = self._create_studies(study_types, start_date, days, studies_per_day)

        self.stdout.write(self.style.SUCCESS("\nДемо-данные готовы"))
        self.stdout.write(f"  Период: {start_date.isoformat()} - {(start_date + timedelta(days=days - 1)).isoformat()}")
        self.stdout.write(f"  Врачей: {len(doctors)}")
        self.stdout.write(f"  Расписаний: {schedules_count}")
        self.stdout.write(f"  Типов исследований: {len(study_types)}")
        self.stdout.write(f"  Ожидающих исследований: {studies_count}")
        self.stdout.write(
            self.style.HTTP_INFO(
                "\nЗапуск: python manage.py generate_demo_data --days 4"
            )
        )

    def _parse_start_date(self, value):
        if not value:
            return timezone.localdate()
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _clear_previous_demo(self):
        demo_doctor_ids = [
            DEMO_DOCTOR_ID_START + offset for offset in range(len(DEMO_DOCTORS))
        ]
        demo_study_type_ids = [
            DEMO_STUDY_TYPE_ID_START + offset for offset in range(len(DEMO_STUDY_TYPES))
        ]
        Study.objects.filter(research_number__startswith=DEMO_RESEARCH_PREFIX).delete()
        Schedule.objects.filter(doctor_id__in=demo_doctor_ids).delete()
        Doctor.objects.filter(id__in=demo_doctor_ids).delete()
        StudyType.objects.filter(id__in=demo_study_type_ids).delete()

    def _create_doctors(self):
        doctors = []
        for offset, (name, position, modalities) in enumerate(DEMO_DOCTORS):
            doctor = Doctor.objects.create(
                id=DEMO_DOCTOR_ID_START + offset,
                fio_alias=name,
                position_type=position,
                max_up_per_day=8,
                is_active=True,
                modality=modalities,
            )
            doctors.append(doctor)
        return doctors

    def _create_study_types(self):
        study_types = []
        for offset, (name, modality) in enumerate(DEMO_STUDY_TYPES):
            study_type = StudyType.objects.create(
                id=DEMO_STUDY_TYPE_ID_START + offset,
                name=name,
                modality=modality,
                up_value=get_modality_up_value(modality),
            )
            study_types.append(study_type)
        return study_types

    def _create_schedules(self, doctors, start_date, days):
        created = 0
        for day_offset in range(days):
            work_date = start_date + timedelta(days=day_offset)
            for doctor_index, doctor in enumerate(doctors):
                starts_late = doctor_index % 3 == 2
                Schedule.objects.create(
                    doctor=doctor,
                    work_date=work_date,
                    time_start=time(10, 0) if starts_late else time(8, 0),
                    time_end=time(18, 0) if starts_late else time(16, 0),
                    break_start=time(13, 0),
                    break_end=time(13, 30),
                    is_day_off=0,
                    day_status=0,
                    planned_up=8,
                )
                created += 1
        return created

    def _create_studies(self, study_types, start_date, days, studies_per_day):
        created = 0
        now = timezone.now()

        for day_offset in range(days):
            base_day = start_date + timedelta(days=day_offset)
            base_dt = timezone.make_aware(datetime.combine(base_day, time(7, 30)))

            for index in range(studies_per_day):
                study_type = study_types[(index + day_offset) % len(study_types)]
                priority = PRIORITY_PATTERN[(index + day_offset * 3) % len(PRIORITY_PATTERN)]
                created_at = base_dt + timedelta(minutes=index * 17)

                if priority == "cito":
                    created_at = min(created_at, now - timedelta(hours=3 + index % 4))
                elif priority == "asap" and index % 2 == 0:
                    created_at = min(created_at, now - timedelta(hours=26 + index % 6))

                Study.objects.create(
                    research_number=f"{DEMO_RESEARCH_PREFIX}{base_day:%Y%m%d}-{index + 1:03d}",
                    study_type=study_type,
                    status="pending",
                    priority=priority,
                    created_at=created_at,
                    planned_at=None,
                    diagnostician=None,
                )
                created += 1

        return created
