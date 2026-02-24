"""
Сервис автоматизированного распределения исследований по врачам.

Реализует критерий минимизации просрочек:
MIN Z = Σᵢ max(0, C_i - d_i)

где:
- C_i — время завершения исследования i
- d_i — дедлайн исследования i
"""

from datetime import timedelta
from datetime import datetime
from django.utils import timezone
from api.models import Study, Doctor, Schedule, StudyType
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class StudyData:
    """Данные исследования для распределения"""
    id: int
    research_number: str
    priority: str
    created_at: datetime
    study_type_id: int
    modality: str
    up_value: float
    deadline: datetime
    
    @property
    def deadline_hours(self) -> int:
        """Срок выполнения в часах"""
        if self.priority == 'cito':
            return 2
        elif self.priority == 'asap':
            return 24
        else:
            return 72


@dataclass
class DoctorData:
    """Данные врача для распределения"""
    id: int
    fio_alias: str
    modality: List[str]
    max_up_per_day: int
    current_load: float = 0.0
    available_time: Optional[datetime] = None


class DistributionService:
    """
    Сервис распределения исследований.
    
    Алгоритм:
    1. Получить все нераспределённые исследования
    2. Отфильтровать врачей по смене на сегодня
    3. Сопоставить модальности
    4. Назначить исследования с минимизацией просрочек
    """
    
    # Дедлайны по приоритетам (часы)
    DEADLINES = {
        'cito': 2,
        'asap': 24,
        'normal': 72,
    }
    
    def __init__(self):
        # ✅ ИСПРАВЛЕНО: получаем текущее время
        self.now = timezone.now()
    
    def make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        ✅ НОВАЯ ФУНКЦИЯ: Делает datetime timezone-aware
        
        Если datetime уже aware — возвращает как есть
        Если naive — добавляет текущий timezone
        Если None — возвращает None
        """
        if dt is None:
            return None
        
        if timezone.is_aware(dt):
            return dt
        
        # Делаем aware с текущим timezone
        return timezone.make_aware(dt)
    
    def get_deadline(self, study: Study) -> datetime:
        """
        Рассчитать дедлайн исследования.
        
        Формула из отчёта (стр. 30):
        d_i = t_i + норматив
        """
        priority = study.priority or 'normal'
        hours = self.DEADLINES.get(priority, 72)
        
        # ✅ ИСПРАВЛЕНО: делаем created_at aware перед сложением
        created_at = self.make_aware(study.created_at)
        
        if created_at is None:
            created_at = self.now
        
        return created_at + timedelta(hours=hours)
    
    def get_pending_studies(self) -> List[Study]:
        """
        Получить исследования, ожидающие назначения.
        
        Статусы: pending, confirmed (без назначенного врача)
        """
        return Study.objects.filter(
            diagnostician__isnull=True,
            status__in=['pending', 'confirmed', None]
        ).select_related('study_type').order_by(
            '-priority',  # CITO сначала
            'created_at'  # Потом по дате создания
        )
    
    def get_available_doctors(self, date: datetime = None) -> List[Doctor]:
        """
        Получить врачей, работающих в указанный день.
        
        Фильтрация по:
        - active = True
        - есть смена на дату
        - is_day_off = 0
        """
        if date is None:
            date = timezone.now().date()
        
        doctor_ids = Schedule.objects.filter(
            work_date=date,
            is_day_off=0
        ).values_list('doctor_id', flat=True)
        
        return Doctor.objects.filter(
            id__in=doctor_ids,
            is_active=True
        )
    
    def check_modality_compatibility(
        self, 
        study_modality: str, 
        doctor_modalities: List[str]
    ) -> bool:
        """
        Проверить соответствие модальности врача и исследования.
        
        Примеры модальностей:
        - XRAY (Рентген)
        - CT (Компьютерная томография)
        - MRI (Магнитно-резонансная томография)
        """
        if not doctor_modalities:
            return True  # Если у врача не указаны модальности — считаем совместимым
        
        if not study_modality:
            return True  # Если у исследования не указана модальность
        
        return study_modality.upper() in [m.upper() for m in doctor_modalities]
    
    def calculate_completion_time(
        self, 
        doctor: DoctorData, 
        study: StudyData
    ) -> datetime:
        """
        Рассчитать время завершения исследования.
        
        C_i = max(available_time, now) + duration
        """
        # Длительность исследования (условно 15 мин за 1 УП)
        duration_minutes = float(study.up_value) * 15
        
        if doctor.available_time is None:
            # ✅ ИСПРАВЛЕНО: now уже aware из __init__
            doctor.available_time = self.now
        
        completion_time = doctor.available_time + timedelta(minutes=duration_minutes)
        doctor.available_time = completion_time
        
        return completion_time
    
    def calculate_tardiness(
        self, 
        completion_time: datetime, 
        deadline: datetime
    ) -> float:
        """
        Рассчитать просрочку (T_i).
        
        Формула из отчёта (стр. 30):
        T_i = max(0, C_i - d_i)
        
        Возвращает просрочку в часах.
        """
        # ✅ ИСПРАВЛЕНО: убеждаемся что оба datetime aware
        if not timezone.is_aware(completion_time):
            completion_time = timezone.make_aware(completion_time)
        
        if not timezone.is_aware(deadline):
            deadline = timezone.make_aware(deadline)
        
        if completion_time <= deadline:
            return 0.0
        
        tardiness = (completion_time - deadline).total_seconds() / 3600
        return max(0, tardiness)
    
    def find_best_doctor(
        self, 
        study: StudyData, 
        doctors: List[DoctorData]
    ) -> Optional[DoctorData]:
        """
        Найти лучшего врача для исследования.
        
        Критерий: минимальная просрочка + минимальная загрузка
        """
        compatible_doctors = []
        
        for doctor in doctors:
            # Проверка модальности
            if not self.check_modality_compatibility(study.modality, doctor.modality):
                continue
            
            # Проверка загрузки (не превышать max_up_per_day)
            if doctor.current_load >= doctor.max_up_per_day:
                continue
            
            # Расчёт просрочки
            completion_time = self.calculate_completion_time(doctor, study)
            tardiness = self.calculate_tardiness(completion_time, study.deadline)
            
            compatible_doctors.append((doctor, tardiness, completion_time))
        
        if not compatible_doctors:
            return None
        
        # Сортировка: сначала по просрочке, потом по загрузке
        compatible_doctors.sort(key=lambda x: (x[1], x[0].current_load))
        
        return compatible_doctors[0][0]
    
    def distribute(self) -> Dict:
        """
        Выполнить распределение исследований.
        
        Возвращает:
        - assigned: количество назначенных
        - unassigned: количество неназначенных
        - total_tardiness: суммарная просрочка (часы)
        - assignments: список назначений
        """
        studies = self.get_pending_studies()
        doctors = self.get_available_doctors()
        
        if not studies or not doctors:
            return {
                'assigned': 0,
                'unassigned': 0,
                'total_tardiness': 0,
                'assignments': [],
                'message': 'Нет исследований или врачей для распределения'
            }
        
        # Подготовка данных врачей
        doctor_data_list = []
        for doctor in doctors:
            doctor_data_list.append(DoctorData(
                id=doctor.id,
                fio_alias=doctor.fio_alias,
                modality=doctor.modality or [],
                max_up_per_day=doctor.max_up_per_day or 120,
                current_load=0.0,
                available_time=None
            ))
        
        assignments = []
        total_tardiness = 0.0
        assigned_count = 0
        unassigned_count = 0
        
        for study in studies:
            # ✅ ИСПРАВЛЕНО: делаем created_at aware перед созданием StudyData
            created_at = self.make_aware(study.created_at)
            if created_at is None:
                created_at = self.now
            
            # Подготовка данных исследования
            study_type = study.study_type
            study_data = StudyData(
                id=study.id,
                research_number=study.research_number,
                priority=study.priority or 'normal',
                created_at=created_at,
                study_type_id=study_type.id if study_type else None,
                modality=study_type.modality if study_type else '',
                up_value=float(study_type.up_value) if study_type and study_type.up_value else 1.0,
                deadline=self.get_deadline(study)
            )
            
            # Поиск лучшего врача
            best_doctor = self.find_best_doctor(study_data, doctor_data_list)
            
            if best_doctor:
                # Назначение врача
                study.diagnostician_id = best_doctor.id
                study.status = 'confirmed'
                study.save()
                
                # Обновление загрузки врача
                best_doctor.current_load += study_data.up_value
                
                # Расчёт просрочки
                completion_time = self.calculate_completion_time(best_doctor, study_data)
                tardiness = self.calculate_tardiness(completion_time, study_data.deadline)
                total_tardiness += tardiness
                
                assignments.append({
                    'study_id': study.id,
                    'study_number': study.research_number,
                    'doctor_id': best_doctor.id,
                    'doctor_name': best_doctor.fio_alias,
                    'priority': study_data.priority,
                    'deadline': study_data.deadline.isoformat(),
                    'tardiness_hours': round(tardiness, 2),
                    'up_value': study_data.up_value,
                })
                
                assigned_count += 1
            else:
                unassigned_count += 1
        
        return {
            'assigned': assigned_count,
            'unassigned': unassigned_count,
            'total_tardiness': round(total_tardiness, 2),
            'avg_tardiness': round(total_tardiness / assigned_count, 2) if assigned_count > 0 else 0,
            'assignments': assignments,
            'message': f'Распределено {assigned_count} из {assigned_count + unassigned_count} исследований'
        }


# === УДОБНАЯ ФУНКЦИЯ ДЛЯ ВЫЗОВА ===
def distribute_studies() -> Dict:
    """
    Быстрый вызов распределения.
    
    Пример использования:
        from api.services.distribution import distribute_studies
        result = distribute_studies()
        print(result['message'])
    """
    service = DistributionService()
    return service.distribute()