"""
Централизованный конфигурационный модуль сервиса оффлайн-распределения.

Здесь собраны:
- словари нормализации модальностей;
- базовые веса приоритетов и selection scores;
- нормативы дедлайнов по приоритетам;
- типовые длительности исследований по модальностям;
- параметры exact MILP;
- параметры формирования candidate pool;
- параметры виртуального штрафа для неназначенных исследований.

Модуль не содержит бизнес-логики и используется как единый источник
настроек для остальных компонентов системы.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


@dataclass
class StudyData:
    """
    Нормализованное представление исследования для алгоритма распределения.

    Поля класса содержат минимально необходимую информацию для принятия
    решения о назначении:
    - идентификатор исследования;
    - приоритет;
    - время создания;
    - множество допустимых модальностей;
    - условные пункты;
    - предполагаемую длительность;
    - дедлайн;
    - вес приоритета.

    Объект формируется на этапе загрузки данных из БД и дальше используется
    всеми решателями и вспомогательными модулями.
    """
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
        """
        Нормализованное представление исследования для алгоритма распределения.

        Поля класса содержат минимально необходимую информацию для принятия
        решения о назначении:
        - идентификатор исследования;
        - приоритет;
        - время создания;
        - множество допустимых модальностей;
        - условные пункты;
        - предполагаемую длительность;
        - дедлайн;
        - вес приоритета.

        Объект формируется на этапе загрузки данных из БД и дальше используется
        всеми решателями и вспомогательными модулями.
        """
        return self.duration_minutes / 60.0


@dataclass
class DoctorData:
    """
    Нормализованное представление врача для алгоритма распределения.

    Содержит:
    - идентификатор и имя врача;
    - множество доступных модальностей;
    - дневной лимит по УП;
    - рабочее окно смены;
    - перерыв;
    - накопленные назначения и фактическую загрузку.

    В ходе расчёта объект может использоваться как источник ограничений
    и как контейнер для накопления итоговой статистики по врачу.
    """
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
        """
        Вернуть длительность перерыва в минутах.

        Если перерыв не задан или задан некорректно, возвращается 0.
        """
        if self.break_start and self.break_end and self.break_end > self.break_start:
            return (self.break_end - self.break_start).total_seconds() / 60.0
        return 0.0

    @property
    def shift_hours(self) -> float:
        """
        Вернуть эффективную продолжительность смены в часах.

        Значение рассчитывается как разница между началом и концом смены
        за вычетом перерыва.
        """
        gross = (self.shift_end - self.shift_start).total_seconds() / 3600.0
        return max(0.0, gross - self.break_minutes / 60.0)

    @property
    def free_up(self) -> float:
        """
        Вернуть эффективную продолжительность смены в часах.

        Значение рассчитывается как разница между началом и концом смены
        за вычетом перерыва.
        """
        return max(0.0, self.max_up - self.used_up)


@dataclass
class ScheduleOption:
    """
    Допустимый вариант назначения исследования на врача.

    Каждый объект описывает один конкретный сценарий:
    - какое исследование;
    - какому врачу;
    - в какое время стартует и заканчивается;
    - какие слоты рабочего окна занимает;
    - какие значения tardiness и objective получаются.

    Эти объекты используются при построении exact MILP.
    """
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
