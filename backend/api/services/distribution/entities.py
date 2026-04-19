"""
Доменные сущности сервиса распределения.

Здесь описаны минимальные структуры данных, которые используются решателями,
формирователем candidate pool и builder-ом ответа.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


@dataclass
class StudyData:
    """Нормализованное представление исследования для алгоритма распределения."""

    research_number: str
    priority: str
    created_at: datetime
    modality: Set[str]
    up_value: float
    duration_minutes: float
    deadline: datetime
    weight: float

    @property
    def duration_hours(self) -> float:
        """Вернуть длительность исследования в часах."""
        return self.duration_minutes / 60.0


@dataclass
class DoctorData:
    """Нормализованное представление врача и его рабочей смены."""

    id: int
    name: str
    modality: Set[str]
    max_up: float
    shift_start: datetime
    shift_end: datetime
    break_start: Optional[datetime] = None
    break_end: Optional[datetime] = None
    assigned_ids: List[str] = field(default_factory=list)
    used_up: float = 0.0
    used_minutes: float = 0.0

    @property
    def break_minutes(self) -> float:
        """Вернуть длительность перерыва в минутах."""
        if self.break_start and self.break_end and self.break_end > self.break_start:
            return (self.break_end - self.break_start).total_seconds() / 60.0
        return 0.0

    @property
    def shift_minutes(self) -> float:
        """Вернуть эффективную продолжительность смены в минутах."""
        gross = (self.shift_end - self.shift_start).total_seconds() / 60.0
        return max(0.0, gross - self.break_minutes)

    @property
    def shift_hours(self) -> float:
        """Вернуть эффективную продолжительность смены в часах."""
        return self.shift_minutes / 60.0

    @property
    def free_up(self) -> float:
        """Вернуть остаток доступного дневного лимита УП."""
        return max(0.0, self.max_up - self.used_up)

    def reset_runtime_stats(self) -> None:
        """Очистить накопленные во время расчёта назначения и загрузку."""
        self.assigned_ids.clear()
        self.used_up = 0.0
        self.used_minutes = 0.0

    def clone_with_remaining_up(self, remaining_up: float) -> "DoctorData":
        """Создать копию врача для очередного прохода multi-pass."""
        return DoctorData(
            id=self.id,
            name=self.name,
            modality=set(self.modality),
            max_up=max(0.0, float(remaining_up)),
            shift_start=self.shift_start,
            shift_end=self.shift_end,
            break_start=self.break_start,
            break_end=self.break_end,
        )


@dataclass
class ScheduleOption:
    """Один допустимый вариант назначения исследования на конкретного врача."""

    option_id: int
    study_idx: int
    doctor_idx: int
    start_dt: datetime
    finish_dt: datetime
    tardiness_hours: float
    weighted_tardiness: float
    occupied_slots: List[int]
    metrics: Dict[str, float] = field(default_factory=dict)
    objective_value: float = 0.0
