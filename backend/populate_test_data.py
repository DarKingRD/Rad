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
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rengenols.settings')
django.setup()

from api.models import Doctor, Schedule, Study, StudyType

# Список тестовых врачей
TEST_DOCTORS = [
    {"id": 1, "fio_alias": "Иванов Иван Иванович", "position_type": "radiologist", "max_up_per_day": 120, "is_active": True, "modality": ["CT", "MRI"]},
    {"id": 2, "fio_alias": "Петров Петр Петрович", "position_type": "radiologist", "max_up_per_day": 120, "is_active": True, "modality": ["CT"]},
    {"id": 3, "fio_alias": "Сидоров Сидор Сидорович", "position_type": "diagnostician", "max_up_per_day": 120, "is_active": True, "modality": ["XRAY"]},
    {"id": 4, "fio_alias": "Козлов Алексей Владимирович", "position_type": "diagnostician", "max_up_per_day": 120, "is_active": True, "modality": ["XRAY", "MRI"]}, 
    {"id": 5, "fio_alias": "Морозова Елена Сергеевна", "position_type": "radiologist", "max_up_per_day": 120, "is_active": True, "modality": ["XRAY", "CT"]}
]

# Типы исследований
STUDY_TYPES = [
    {"id": 1, "name": "Рентгенография грудной клетки", "modality": "XRAY", "up_value": 1.3},
    {"id": 2, "name": "Рентгенография черепа", "modality": "XRAY", "up_value": 1.3},
    {"id": 3, "name": "Рентгенография кисти", "modality": "XRAY", "up_value": 1.3},
    {"id": 4, "name": "КТ головного мозга", "modality": "CT", "up_value": 1.6},
    {"id": 5, "name": "КТ органов грудной клетки", "modality": "CT", "up_value": 1.6},
    {"id": 6, "name": "МРТ", "modality": "MRI", "up_value": 1.7},
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
            id=doctor_data["id"],
            defaults=doctor_data
        )
        if created:
            print(f"Создан врач: {doctor.fio_alias}")
        else:
            print(f"Обновлен врач: {doctor.fio_alias}")

def create_schedules():
    """Создание расписаний на сегодня"""
    print("Создание расписаний на сегодня...")
    today = timezone.now().date()
    
    # Получаем максимальный ID из существующих расписаний
    max_schedule_id = Schedule.objects.aggregate(models.Max('id'))['id__max'] or 0
    
    for i, doctor_data in enumerate(TEST_DOCTORS):
        schedule_data = {
            "id": max_schedule_id + i + 1,  # Уникальный ID для каждого расписания
            "doctor_id": doctor_data["id"],
            "work_date": today,
            "time_start": time(9, 0),
            "time_end": time(17, 0),
            "is_day_off": 0,
            "planned_up": 120
        }
        
        schedule, created = Schedule.objects.update_or_create(
            doctor_id=schedule_data["doctor_id"],
            work_date=schedule_data["work_date"],
            defaults=schedule_data
        )
        
        if created:
            print(f"Создано расписание для: {doctor_data['fio_alias']}")
        else:
            print(f"Обновлено расписание для: {doctor_data['fio_alias']}")

def create_study_types():
    """Создание типов исследований"""
    print("Создание типов исследований...")
    for study_type_data in STUDY_TYPES:
        study_type, created = StudyType.objects.update_or_create(
            id=study_type_data["id"],
            defaults=study_type_data
        )
        if created:
            print(f"Создан тип исследования: {study_type.name}")
        else:
            print(f"Обновлен тип исследования: {study_type.name}")

def create_studies(count=1500):
    """Создание исследований без назначенных врачей"""
    print(f"Создание {count} исследований...")
    
    # Получаем все типы исследований
    study_types = list(StudyType.objects.all())
    if not study_types:
        print("Нет доступных типов исследований")
        return
    
    # Получаем максимальный ID из существующих исследований
    max_study_id = Study.objects.aggregate(models.Max('id'))['id__max'] or 0
    
    # Приоритеты
    priorities = ["normal", "cito", "asap"]
    priority_weights = [0.5, 0.3, 0.2]  # 50% normal, 30% cito, 20% asap
    
    created_count = 0
    for i in range(count):
        # Генерируем уникальный номер исследования
        research_number = f"TEST-{timezone.now().strftime('%Y%m%d')}-{i+1:06d}"
        
        # Выбираем случайный тип исследования
        study_type = random.choice(study_types)
        
        # Выбираем приоритет
        priority = random.choices(priorities, weights=priority_weights)[0]
        
        # Генерируем дату создания (в пределах последних 3 дней для более реалистичного распределения)
        created_at = timezone.now() - timezone.timedelta(
            days=random.randint(0, 2),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59)
        )
        
        # Генерируем плановую дату (в пределах сегодняшнего дня для более реалистичного распределения)
        planned_at = timezone.now() + timezone.timedelta(
            hours=random.randint(-2, 8),  # В пределах сегодняшнего дня с небольшим отклонением
            minutes=random.randint(0, 59)
        )
        
        study_data = {
            "id": max_study_id + i + 1,  # Уникальный ID для каждого исследования
            "research_number": research_number,
            "study_type_id": study_type.id,
            "status": "pending",
            "priority": priority,
            "created_at": created_at,
            "planned_at": planned_at,
            "diagnostician_id": None  # Без назначенного врача
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
    create_studies(1500)
    
    print("Заполнение тестовыми данными завершено")

if __name__ == "__main__":
    main()
