"""
Скрипт для заполнения тестовыми данными базы данных системы распределения исследований.
"""

import os
import sys
import random
import django
from datetime import datetime, date, time
from django.utils import timezone
from django.db import models

# Добавляем путь к проекту в sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rengenols.settings")
django.setup()

from api.models import Doctor, Schedule, Study, StudyType

# Список тестовых врачей
TEST_DOCTORS = [
    {
        "id": 1,
        "fio_alias": "Иванов Иван Иванович",
        "position_type": "radiologist",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["CT", "MRI"],
    },
    {
        "id": 2,
        "fio_alias": "Петров Петр Петрович",
        "position_type": "radiologist",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["CT"],
    },
    {
        "id": 3,
        "fio_alias": "Сидоров Сидор Сидорович",
        "position_type": "diagnostician",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["XRAY"],
    },
    {
        "id": 4,
        "fio_alias": "Козлов Алексей Владимирович",
        "position_type": "diagnostician",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["XRAY", "MRI"],
    },
    {
        "id": 5,
        "fio_alias": "Морозова Елена Сергеевна",
        "position_type": "radiologist",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["XRAY", "CT", "MRI"],
    },
        {
        "id": 6,
        "fio_alias": "Баранов Денис Алексеевич",
        "position_type": "radiologist",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["MRI"],
    },
      {
        "id": 7,
        "fio_alias": "Баранов Алексей Алексеевич",
        "position_type": "radiologist",
        "max_up_per_day": 50,
        "is_active": True,
        "modality": ["MRI", "CT"],
    },
]

# Типы исследований
STUDY_TYPES = [
    {
        "id": 1,
        "name": "Рентгенография грудной клетки",
        "modality": "XRAY",
        "up_value": 0.083,
    },
    {"id": 2, "name": "Рентгенография черепа", "modality": "XRAY", "up_value": 0.083},
    {"id": 3, "name": "Рентгенография кисти", "modality": "XRAY", "up_value": 0.083},
    {"id": 4, "name": "КТ головного мозга", "modality": "CT", "up_value": 0.25},
    {"id": 5, "name": "КТ органов грудной клетки", "modality": "CT", "up_value": 0.25},
    {"id": 6, "name": "МРТ", "modality": "MRI", "up_value": 0.333},
]


def clear_data():
    """Очистка таблиц"""
    print("Очистка таблиц...")
    Study.objects.all().delete()
    Schedule.objects.all().delete()
    print("Таблицы очищены")


def create_doctors():
    """Создание записей о врачах"""
    print("Создание записей о врачах...")
    for doctor_data in TEST_DOCTORS:
        doctor, created = Doctor.objects.update_or_create(
            id=doctor_data["id"], defaults=doctor_data
        )
        if created:
            print(f"Создан врач: {doctor.fio_alias}")
        else:
            print(f"Обновлен врач: {doctor.fio_alias}")


def create_schedules():
    """Создание расписаний на 01.03 и 02.03"""
    print("Создание расписаний на 01.03 и 02.03...")
    
    # Фиксируем даты
    target_dates = [date(2026, 3, 2)]
    
    current_id = Schedule.objects.aggregate(models.Max("id"))["id__max"] or 0

    for work_date in target_dates:
        for i, doctor_data in enumerate(TEST_DOCTORS):
            current_id += 1
            schedule_data = {
                "id": current_id,
                "doctor_id": doctor_data["id"],
                "work_date": work_date,  # <-- Используем дату из цикла
                "time_start": time(9, 0),
                "time_end": time(17, 0),
                "is_day_off": 0,
                "planned_up": 50,
            }

            Schedule.objects.update_or_create(
                doctor_id=schedule_data["doctor_id"],
                work_date=schedule_data["work_date"],
                defaults=schedule_data,
            )
            
    print(f"Расписания созданы на {len(target_dates)} дня")


def create_study_types():
    """Создание типов исследований"""
    print("Создание типов исследований...")
    for study_type_data in STUDY_TYPES:
        study_type, created = StudyType.objects.update_or_create(
            id=study_type_data["id"], defaults=study_type_data
        )
        if created:
            print(f"Создан тип исследования: {study_type.name}")
        else:
            print(f"Обновлен тип исследования: {study_type.name}")


def create_studies(count):
    """Создание исследований без назначенных врачей"""
    print(f"Создание {count} исследований...")

    study_types = list(StudyType.objects.all())
    if not study_types:
        print("Нет доступных типов исследований")
        return

    max_study_id = Study.objects.aggregate(models.Max("id"))["id__max"] or 0
    priorities = ["normal", "cito", "asap"]
    priority_weights = [0.5, 0.3, 0.2]

    # Даты для генерации исследований
    target_dates = [date(2026, 3, 1), date(2026, 3, 2)]

    created_count = 0
    for i in range(count):
        research_number = f"TEST-20260301-{i + 1:06d}"
        study_type = random.choice(study_types)
        priority = random.choices(priorities, weights=priority_weights)[0]

        # 1. Генерируем дату создания (за 1-2 дня до плановой)
        planned_date = random.choice(target_dates)
        created_at = timezone.make_aware(
            datetime.combine(planned_date, time(0, 0)) - timezone.timedelta(days=random.randint(1, 2))
        )

        # 2. Генерируем плановую дату (только 01.03 или 02.03 в рабочее время)
        planned_at = timezone.make_aware(
            datetime.combine(planned_date, time(random.randint(9, 16), random.randint(0, 59)))
        )

        study_data = {
            "id": max_study_id + i + 1,
            "research_number": research_number,
            "study_type_id": study_type.id,
            "status": "pending",
            "priority": priority,
            "created_at": created_at,
            "planned_at": planned_at,
            "diagnostician_id": None,
        }

        try:
            Study.objects.create(**study_data)
            created_count += 1
        except Exception as e:
            print(f"Ошибка при создании исследования {research_number}: {e}")
            continue

    print(f"Создано {created_count} исследований")


def main():
    """Основная функция"""
    print("Начало заполнения тестовыми данными...")

    # Очистка данных
    clear_data()

    # Создание данных
    create_doctors()
    create_study_types()
    create_schedules()
    create_studies(400)

    print("Заполнение тестовыми данными завершено")


if __name__ == "__main__":
    main()
