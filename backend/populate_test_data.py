"""
Скрипт для заполнения тестовыми данными базы данных системы распределения исследований.
"""

import os
import sys
import random
import django
from datetime import datetime, date, time, timedelta  # Добавлен timedelta
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

# Дедлайны в часах по приоритетам
DEADLINE_HOURS = {
    "cito": 2,
    "asap": 24,
    "normal": 72
}


def clear_data():
    """Очистка таблиц"""
    print("Очистка таблиц...")
    # Используем delete() напрямую на QuerySet
    Study.objects.all().delete()
    Schedule.objects.all().delete()
    Doctor.objects.all().delete()
    StudyType.objects.all().delete()
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
    """Создание расписаний с 03.03 по 07.03 (чтобы покрыть дедлайны исследований)"""
    print("Создание расписаний...")
    
    # Расширяем диапазон дат, чтобы хватило на normal priority (72 часа = 3 дня)
    # Start: 3 марта, End: 6 марта (включительно)
    start_date = date(2026, 3, 3)
    end_date = date(2026, 3, 6)
    
    current_date = start_date
    target_dates = []
    while current_date <= end_date:
        target_dates.append(current_date)
        current_date += timedelta(days=1)

    # Получаем текущий максимальный ID
    agg = Schedule.objects.aggregate(models.Max("id"))
    current_id = agg["id__max"] or 0

    for work_date in target_dates:
        for i, doctor_data in enumerate(TEST_DOCTORS):
            current_id += 1
            schedule_data = {
                "id": current_id,
                "doctor_id": doctor_data["id"],
                "work_date": work_date,
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
            
    print(f"Расписания созданы на {len(target_dates)} дней (с {start_date} по {end_date})")


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
    """Создание исследований с расчетом плановой даты от дедлайна"""
    print(f"Создание {count} исследований...")

    study_types = list(StudyType.objects.all())
    if not study_types:
        print("Нет доступных типов исследований")
        return

    agg = Study.objects.aggregate(models.Max("id"))
    max_study_id = agg["id__max"] or 0
    
    priorities = ["normal", "cito", "asap"]
    # Веса приоритетов: чаще нормальные, реже срочные
    priority_weights = [0.6, 0.01, 0.39]

    # Базовая дата создания исследований (3 марта)
    base_created_date = date(2026, 3, 2)

    created_count = 0
    for i in range(count):
        research_number = f"TEST-20260303-{i + 1:06d}"
        study_type = random.choice(study_types)
        priority = random.choices(priorities, weights=priority_weights)[0]

        # 1. Генерируем дату создания (3 марта, случайное время)
        created_time = time(random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
        created_at_naive = datetime.combine(base_created_date, created_time)
        created_at = timezone.make_aware(created_at_naive)

        # 2. Рассчитываем плановую дату на основе дедлайна
        deadline_hours = DEADLINE_HOURS[priority]
        planned_at = created_at + timedelta(hours=deadline_hours)

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
    print(f"Диапазон плановых дат: от {base_created_date} до {base_created_date + timedelta(hours=72)}")


def main():
    """Основная функция"""
    print("Начало заполнения тестовыми данными...")

    # Очистка данных
    clear_data()

    # Создание данных
    create_doctors()
    create_study_types()
    create_schedules()
    create_studies(900)

    print("Заполнение тестовыми данными завершено")


if __name__ == "__main__":
    main()