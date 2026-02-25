"""
Сервис автоматизированного распределения исследований по врачам.
Реализует алгоритм ATC для минимизации:
MIN Z = Σᵢ w_i × T_i
где T_i = max(0, C_i - d_i)
"""

from datetime import timedelta, datetime, time
from django.utils import timezone
from api.models import Study, Doctor, Schedule, StudyType
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
import math
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# МАППИНГ МОДАЛЬНОСТЕЙ
# ==============================================================================

MODALITY_ALIASES = {
    "KT": "CT",
    "КТ": "CT",
    "COMPUTED_TOMOGRAPHY": "CT",
    "MRT": "MRI",
    "МРТ": "MRI",
    "MAGNETIC_RESONANCE": "MRI",
    "RENTGEN": "XRAY",
    "РЕНТГЕН": "XRAY",
    "X_RAY": "XRAY",
    "US": "US",
    "УЗИ": "US",
    "ULTRASOUND": "US",
    "OTHER": "OTHER",
    "ПРОЧЕЕ": "OTHER",
    "": "OTHER",
}


def normalize_modality(modality: str) -> str:
    if not modality:
        return "OTHER"
    normalized = modality.strip().upper()
    return MODALITY_ALIASES.get(normalized, normalized)


def parse_modalities(modality_data) -> Set[str]:
    if modality_data is None:
        return set()
    if isinstance(modality_data, list):
        modalities = modality_data
    elif isinstance(modality_data, str):
        modalities = modality_data.split("/")
    else:
        return set()

    result = set()
    for m in modalities:
        if m and str(m).strip():
            normalized = normalize_modality(str(m))
            result.add(normalized)
    return result


# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================


@dataclass
class Config:
    PRIORITY_WEIGHTS = {
        "cito": 100.0,
        "asap": 10.0,
        "normal": 1.0,
    }

    DEADLINES = {
        "cito": 2,
        "asap": 24,
        "normal": 72,
    }

    MINUTES_PER_UP = 15
    ATC_K_PARAM = 2.0


# ==============================================================================
# СТРУКТУРЫ ДАННЫХ
# ==============================================================================


@dataclass
class StudyData:
    id: int
    research_number: str
    priority: str
    created_at: datetime
    modality: Set[str]
    up_value: float
    deadline: datetime
    weight: float
    duration_minutes: float

    def get_processing_time_hours(self) -> float:
        return self.duration_minutes / 60

    def get_slack_time(self, current_time: datetime) -> float:
        time_to_deadline = (self.deadline - current_time).total_seconds() / 3600
        return time_to_deadline - self.get_processing_time_hours()


@dataclass
class DoctorData:
    id: int
    fio_alias: str
    modality: Set[str]
    max_up_per_day: int
    max_minutes: float
    time_start: Optional[time] = None
    time_end: Optional[time] = None

    current_load: float = 0.0
    current_minutes: float = 0.0
    available_time: Optional[datetime] = None
    assigned_study_ids: List[int] = field(default_factory=list)

    @property
    def remaining_up(self) -> float:
        return max(0, self.max_up_per_day - self.current_load)

    @property
    def remaining_minutes(self) -> float:
        return max(0, self.max_minutes - self.current_minutes)


# ==============================================================================
# СЕРВИС РАСПРЕДЕЛЕНИЯ
# ==============================================================================


class DistributionService:
    """
    Сервис распределения на основе алгоритма ATC.
    Минимизирует ТОЛЬКО: Σ(w_i × T_i)
    """

    def __init__(self):
        self.now = timezone.now()
        self.config = Config()

    def make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if timezone.is_aware(dt):
            return dt
        return timezone.make_aware(dt)

    def check_modality_compatibility(
        self, study_mods: Set[str], doctor_mods: Set[str]
    ) -> bool:
        if not doctor_mods:
            return True
        if not study_mods:
            return True
        return bool(study_mods & doctor_mods)

    def get_deadline(self, study: Study) -> datetime:
        priority = study.priority or "normal"
        hours = self.config.DEADLINES.get(priority, 72)
        created_at = self.make_aware(study.created_at) or self.now
        return created_at + timedelta(hours=hours)

    def get_pending_studies(self) -> List[Study]:
        studies = list(
            Study.objects.filter(diagnostician__isnull=True).select_related(
                "study_type"
            )
        )

        # ✅ Сортировка: CITO → ASAP → Normal, внутри по времени
        studies.sort(
            key=lambda s: (
                0 if s.priority == "cito" else (1 if s.priority == "asap" else 2),
                self.make_aware(s.created_at) or self.now,
            )
        )
        return studies

    def get_available_doctors(self, date: datetime = None) -> List[Doctor]:
        if date is None:
            date = timezone.now().date()

        schedules = Schedule.objects.filter(
            work_date=date, is_day_off=0
        ).select_related("doctor")

        doctor_ids = schedules.values_list("doctor_id", flat=True)
        return Doctor.objects.filter(id__in=doctor_ids, is_active=True)

    def prepare_doctors_data(
        self, doctors: List[Doctor], today: datetime
    ) -> List[DoctorData]:
        doctor_data_list = []

        for doctor in doctors:
            schedule = Schedule.objects.filter(
                doctor=doctor, work_date=today.date(), is_day_off=0
            ).first()

            if not schedule:
                continue

            modality_set = parse_modalities(doctor.modality)

            if schedule.time_start and schedule.time_end:
                start_dt = datetime.combine(today.date(), schedule.time_start)
                end_dt = datetime.combine(today.date(), schedule.time_end)
                start_dt = timezone.make_aware(start_dt)
                end_dt = timezone.make_aware(end_dt)
                max_minutes = (end_dt - start_dt).total_seconds() / 60
                available_time = start_dt
            else:
                max_minutes = 480
                available_time = self.now

            doctor_data = DoctorData(
                id=doctor.id,
                fio_alias=doctor.fio_alias,
                modality=modality_set,
                max_up_per_day=doctor.max_up_per_day or 120,
                max_minutes=max_minutes,
                time_start=schedule.time_start,
                time_end=schedule.time_end,
                current_load=0.0,
                current_minutes=0.0,
                available_time=available_time,
            )
            doctor_data_list.append(doctor_data)

        logger.info(f"Prepared {len(doctor_data_list)} doctors")
        for d in doctor_data_list:
            logger.info(
                f"  Doctor {d.id}: modality={d.modality}, max_minutes={d.max_minutes}, max_up={d.max_up_per_day}"
            )

        return doctor_data_list

    def prepare_study_data(self, study: Study) -> StudyData:
        study_type = study.study_type
        modality_set = parse_modalities(study_type.modality if study_type else [])
        up_value = (
            float(study_type.up_value) if study_type and study_type.up_value else 1.0
        )
        priority = study.priority or "normal"
        created_at = self.make_aware(study.created_at) or self.now
        deadline = self.get_deadline(study)

        return StudyData(
            id=study.id,
            research_number=study.research_number,
            priority=priority,
            created_at=created_at,
            modality=modality_set,
            up_value=up_value,
            deadline=deadline,
            weight=self.config.PRIORITY_WEIGHTS.get(priority, 1.0),
            duration_minutes=up_value * self.config.MINUTES_PER_UP,
        )

    def calculate_atc_index(self, study: StudyData, current_time: datetime) -> float:
        """
        ATC_i(t) = (w_i / p_i) × exp(-max(0, d_i - t - p_i) / (k × p_avg))
        """
        processing_time = study.get_processing_time_hours()
        if processing_time <= 0:
            processing_time = 0.25

        # Используем реальное значение UP для расчета времени обработки
        p_avg = processing_time

        # Рассчитываем slack time с учетом времени обработки
        time_to_deadline = (study.deadline - current_time).total_seconds() / 3600
        slack = time_to_deadline - processing_time

        weight_density = study.weight / processing_time
        exp_component = math.exp(-max(0, slack) / (self.config.ATC_K_PARAM * p_avg))

        atc_index = weight_density * exp_component
        return atc_index

    def calculate_tardiness(
        self, completion_time: datetime, deadline: datetime
    ) -> float:
        """T_i = max(0, C_i - d_i)"""
        if not timezone.is_aware(completion_time):
            completion_time = timezone.make_aware(completion_time)
        if not timezone.is_aware(deadline):
            deadline = timezone.make_aware(deadline)

        if completion_time <= deadline:
            return 0.0

        tardiness = (completion_time - deadline).total_seconds() / 3600
        return max(0, tardiness)

    def find_best_study_for_doctor(
        self, studies: List[StudyData], doctor: DoctorData
    ) -> Optional[Tuple[StudyData, float]]:
        """Находит исследование с НАИБОЛЬШИМ ATC индексом для врача"""
        best_study = None
        best_atc_index = -float("inf")

        for study in studies:
            # Проверка модальности
            if not self.check_modality_compatibility(study.modality, doctor.modality):
                continue

            # ✅ Проверка загрузки по УП (было >=, стало >)
            if doctor.remaining_up < study.up_value:
                continue

            # Проверка совместимости по времени (дедлайн уже прошел)
            if study.deadline < doctor.available_time:
                continue

            # ✅ Проверка времени смены (более мягкая)
            completion_time = doctor.available_time + timedelta(
                minutes=study.duration_minutes
            )
            if doctor.time_end:
                end_dt = datetime.combine(self.now.date(), doctor.time_end)
                end_dt = timezone.make_aware(end_dt)
                # ✅ Разрешаем превышение на 30 минут (овертайм)
                if completion_time > end_dt + timedelta(minutes=30):
                    continue

            # Расчёт ATC индекса
            atc_index = self.calculate_atc_index(study, doctor.available_time)

            if atc_index > best_atc_index:
                best_atc_index = atc_index
                best_study = study

        if best_study:
            return (best_study, best_atc_index)
        return None

    def assign_study_to_doctor(self, study: StudyData, doctor: DoctorData):
        """Назначает исследование врачу"""
        doctor.current_load += study.up_value
        doctor.current_minutes += study.duration_minutes
        doctor.available_time = doctor.available_time + timedelta(
            minutes=study.duration_minutes
        )
        doctor.assigned_study_ids.append(study.id)

    def distribute_atc(
        self, studies: List[StudyData], doctors: List[DoctorData]
    ) -> Dict:
        """
        АЛГОРИТМ ATC для минимизации Σ(w_i × T_i)
        ✅ ИСПРАВЛЕНО: увеличен лимит итераций и consecutive_failures
        """
        logger.info("=" * 60)
        logger.info("Starting ATC Distribution Algorithm")
        logger.info(f"Studies: {len(studies)}, Doctors: {len(doctors)}")
        logger.info("=" * 60)

        assignments = []
        total_tardiness = 0.0
        total_weighted_tardiness = 0.0
        assigned_count = 0

        remaining_studies = studies.copy()

        # ✅ УВЕЛИЧЕНО: было len(studies)*len(doctors), стало больше
        max_iterations = len(studies) * len(doctors) * 2

        # ✅ УВЕЛИЧЕНО: было len(doctors)*2=10, стало 100
        consecutive_failures = 0
        max_consecutive_failures = 100

        iteration = 0
        while remaining_studies and iteration < max_iterations:
            iteration += 1

            best_atc_index = -float("inf")
            best_doctor = None
            best_study = None

            for doctor in doctors:
                # Пропускаем врачей, у которых НЕТ места
                if doctor.remaining_up <= 0:
                    continue
                if doctor.remaining_minutes <= 0:
                    continue

                # Сортируем исследования по ATC индексу в порядке убывания
                doctor_studies = []
                for study in remaining_studies:
                    # Проверка модальности
                    if not self.check_modality_compatibility(study.modality, doctor.modality):
                        continue

                    # Проверка загрузки по УП
                    if doctor.remaining_up < study.up_value:
                        continue

                    # Проверка совместимости по времени
                    if study.deadline < doctor.available_time:
                        continue

                    # Расчёт ATC индекса
                    atc_index = self.calculate_atc_index(study, doctor.available_time)
                    doctor_studies.append((study, atc_index))

                # Сортировка по ATC индексу в порядке убывания
                doctor_studies.sort(key=lambda x: x[1], reverse=True)

                # Выбираем лучшее исследование для врача
                if doctor_studies:
                    study, atc_index = doctor_studies[0]

                    if atc_index > best_atc_index:
                        best_atc_index = atc_index
                        best_doctor = doctor
                        best_study = study

                result = self.find_best_study_for_doctor(remaining_studies, doctor)

                if result:
                    study, atc_index = result

                    if atc_index > best_atc_index:
                        best_atc_index = atc_index
                        best_doctor = doctor
                        best_study = study

            if best_doctor and best_study:
                self.assign_study_to_doctor(best_study, best_doctor)

                completion_time = best_doctor.available_time
                tardiness = self.calculate_tardiness(
                    completion_time, best_study.deadline
                )
                weighted_tardiness = tardiness * best_study.weight

                total_tardiness += tardiness
                total_weighted_tardiness += weighted_tardiness
                assigned_count += 1
                consecutive_failures = 0  # ✅ Сброс при успешном назначении

                remaining_studies.remove(best_study)

                if assigned_count % 100 == 0:
                    logger.info(
                        f"Assigned {assigned_count} studies, ATC index: {best_atc_index:.2f}"
                    )

                assignments.append(
                    {
                        "study_id": best_study.id,
                        "study_number": best_study.research_number,
                        "doctor_id": best_doctor.id,
                        "doctor_name": best_doctor.fio_alias,
                        "priority": best_study.priority,
                        "weight": best_study.weight,
                        "deadline": best_study.deadline.isoformat(),
                        "completion_time": completion_time.isoformat(),
                        "tardiness_hours": round(tardiness, 2),
                        "weighted_tardiness": round(weighted_tardiness, 2),
                        "up_value": best_study.up_value,
                        "atc_index": round(best_atc_index, 2),
                    }
                )
            else:
                consecutive_failures += 1

                # ✅ Логирование каждые 50 неудач
                if consecutive_failures % 50 == 0:
                    logger.warning(
                        f"{consecutive_failures} consecutive failures, remaining studies: {len(remaining_studies)}"
                    )

                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(
                        f"Stopping after {max_consecutive_failures} consecutive failures"
                    )
                    break

        unassigned_count = len(studies) - assigned_count

        logger.info("=" * 60)
        logger.info(f"ATC Distribution Complete:")
        logger.info(f"  Assigned: {assigned_count}")
        logger.info(f"  Unassigned: {unassigned_count}")
        logger.info(f"  Total Tardiness: {round(total_tardiness, 2)} hours")
        logger.info(
            f"  Total Weighted Tardiness (Z): {round(total_weighted_tardiness, 2)}"
        )
        logger.info("=" * 60)

        return {
            "assignments": assignments,
            "total_tardiness": total_tardiness,
            "total_weighted_tardiness": total_weighted_tardiness,
            "assigned_count": assigned_count,
            "unassigned_count": unassigned_count,
        }

    def save_to_db(self, doctors: List[DoctorData]) -> Tuple[List[Dict], float]:
        """Сохраняет назначения в БД"""
        assignments = []
        total_tardiness = 0.0

        for doctor in doctors:
            if not doctor.assigned_study_ids:
                continue

            studies_map = {
                s.id: self.prepare_study_data(s)
                for s in Study.objects.filter(id__in=doctor.assigned_study_ids)
            }

            if doctor.time_start:
                current_time = datetime.combine(self.now.date(), doctor.time_start)
                current_time = timezone.make_aware(current_time)
            else:
                current_time = self.now

            for study_id in doctor.assigned_study_ids:
                study = studies_map.get(study_id)
                if not study:
                    continue

                completion_time = current_time + timedelta(
                    minutes=study.duration_minutes
                )

                if completion_time > study.deadline:
                    tardiness = (
                        completion_time - study.deadline
                    ).total_seconds() / 3600
                else:
                    tardiness = 0.0

                total_tardiness += tardiness

                Study.objects.filter(id=study.id).update(
                    diagnostician_id=doctor.id, status="confirmed"
                )

                assignments.append(
                    {
                        "study_id": study.id,
                        "study_number": study.research_number,
                        "doctor_id": doctor.id,
                        "doctor_name": doctor.fio_alias,
                        "priority": study.priority,
                        "deadline": study.deadline.isoformat(),
                        "completion_time": completion_time.isoformat(),
                        "tardiness_hours": round(tardiness, 2),
                        "up_value": study.up_value,
                    }
                )

                current_time = completion_time

        return assignments, total_tardiness

    def distribute(self) -> Dict:
        """Основной метод распределения (ATC алгоритм)"""
        logger.info("=" * 60)
        logger.info("ATC DISTRIBUTION SERVICE")
        logger.info(f"Time: {self.now}")
        logger.info("Objective: MIN Z = Σ(w_i × T_i)")
        logger.info("=" * 60)

        today = timezone.now()
        studies_qs = self.get_pending_studies()
        doctors_qs = self.get_available_doctors()

        logger.info(f"Pending studies: {len(studies_qs)}")
        logger.info(f"Available doctors: {len(doctors_qs)}")

        if not studies_qs or not doctors_qs:
            return {
                "assigned": 0,
                "unassigned": 0,
                "total_tardiness": 0,
                "total_weighted_tardiness": 0,
                "assignments": [],
                "doctor_stats": [],
                "message": "Нет исследований или врачей для распределения",
            }

        studies_data = [self.prepare_study_data(s) for s in studies_qs]
        doctors_data = self.prepare_doctors_data(doctors_qs, today)

        if not studies_data or not doctors_data:
            return {
                "assigned": 0,
                "unassigned": len(studies_data),
                "total_tardiness": 0,
                "total_weighted_tardiness": 0,
                "assignments": [],
                "doctor_stats": [],
                "message": "Ошибка подготовки данных",
            }

        result = self.distribute_atc(studies_data, doctors_data)

        assignments, total_tardiness = self.save_to_db(doctors_data)

        assigned_count = result["assigned_count"]
        unassigned_count = result["unassigned_count"]

        doctor_stats = [
            {
                "doctor_id": d.id,
                "doctor_name": d.fio_alias,
                "assigned_studies": len(d.assigned_study_ids),
                "total_up": round(d.current_load, 1),
                "max_up": d.max_up_per_day,
                "load_percent": round(
                    (d.current_load / d.max_up_per_day * 100)
                    if d.max_up_per_day > 0
                    else 0,
                    1,
                ),
                "remaining_up": round(d.remaining_up, 1),
            }
            for d in doctors_data
        ]

        priority_stats = {"cito": 0, "asap": 0, "normal": 0}
        for a in assignments:
            priority_stats[a["priority"]] = priority_stats.get(a["priority"], 0) + 1

        return {
            "assigned": assigned_count,
            "unassigned": unassigned_count,
            "total_tardiness": round(total_tardiness, 2),
            "total_weighted_tardiness": round(result["total_weighted_tardiness"], 2),
            "avg_tardiness": round(total_tardiness / assigned_count, 2)
            if assigned_count > 0
            else 0,
            "assignments": assignments,
            "doctor_stats": doctor_stats,
            "priority_stats": priority_stats,
            "objective_function": f"MIN Z = Σ(w_i × T_i) = {round(result['total_weighted_tardiness'], 2)}",
            "message": f"ATC: Распределено {assigned_count} из {len(studies_data)} исследований. "
            f"Целевая функция Z = {round(result['total_weighted_tardiness'], 2)}",
        }


def distribute_studies() -> Dict:
    """Точка входа"""
    service = DistributionService()
    return service.distribute()
