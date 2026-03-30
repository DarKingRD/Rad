"""
Сервис оффлайн-распределения исследований по врачам.

Назначение модуля
-----------------
Этот файл реализует прикладной сервис, который берёт:
1. список нераспределённых исследований;
2. список врачей с расписанием на целевую дату;
3. правила приоритетов, дедлайнов, длительностей и ограничений по УП;
и возвращает результат распределения исследований между врачами.

Ключевая идея текущей версии
----------------------------
Текущая реализация использует ОДНОЭТАПНУЮ exact-постановку на candidate pool:

1) Из всего backlog формируется расширенный candidate pool.
   Это не окончательный план дня, а более широкий набор кандидатов, из
   которого exact-модель выбирает лучший вариант распределения.

2) Для candidate pool решается точная задача с явным выбором:
   - назначить исследование в один из допустимых стартов;
   - либо оставить его неназначенным в текущей смене.

   При этом минимизируется единая objective-функция, зависящая от выбранной
   стратегии. Для взвешенной просрочки она имеет вид:

       MIN Z = Σ(assign_cost(i,o) * x(i,o)) + Σ(unassigned_cost(i) * y(i))

   где:
   - x(i,o) = 1, если исследование i назначено в допустимый старт o;
   - y(i) = 1, если исследование i не вошло в план текущей смены;
   - assign_cost(i,o) — штраф назначения (например, w_i * T_i);
   - unassigned_cost(i) — штраф переноса исследования за пределы текущей смены.

Важно понимать ограничения модели
---------------------------------
- Целевая функция применяется ко всему candidate pool текущего дня.
- Неназначение исследования тоже участвует в objective через отдельный штраф,
  поэтому objective действительно влияет на СОСТАВ выбранных исследований,
  а не только на их внутренний порядок.
- Для exact-модели используется time-indexed MILP: время дискретизируется
  слотами по 5 минут.
- Смена врача и перерыв учитываются явно: нельзя ставить исследование в слот,
  который пересекается с перерывом или выходит за пределы рабочей смены.

Fallback-логика
---------------
Если exact-режим по какой-то причине недоступен (например, не установлен PuLP,
нет допустимых стартов или solver завершился нештатно), сервис переходит на
жадный fallback. Жадная версия не гарантирует глобальный оптимум, но позволяет
получить практический результат и не сорвать распределение полностью.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from django.utils import timezone

from api.models import Schedule, Study

logger = logging.getLogger(__name__)


# ==============================================================================
# МАППИНГ МОДАЛЬНОСТЕЙ
# ==============================================================================
#
# В исходных данных модальность может быть записана по-разному:
# - русскими и латинскими сокращениями;
# - в разных регистрах;
# - в виде альтернативных кодов.
#
# Чтобы логика совместимости "врач ↔ исследование" работала корректно,
# мы приводим все варианты к единому внутреннему виду.
#

MODALITY_ALIASES: Dict[str, str] = {
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
}


def normalize_modality(m: str) -> str:
    """
    Нормализовать обозначение модальности к единому внутреннему коду.

    Примеры:
    - "КТ" -> "CT"
    - "рентген" -> "XRAY"
    - "MRI" -> "MRI"

    Если значение пустое, возвращается "OTHER".
    Если значение неизвестно, возвращается его upper-case представление.
    """
    if not m:
        return "OTHER"
    return MODALITY_ALIASES.get(m.strip().upper(), m.strip().upper())



def parse_modalities(data) -> Set[str]:
    """
    Преобразовать поле модальности в множество нормализованных кодов.

    На вход может прийти:
    - список строк;
    - одна строка, где модальности разделены '/';
    - пустое значение.

    Возвращается множество, потому что:
    - дубли нам не нужны;
    - операции пересечения множеств удобны для проверки совместимости
      исследования и врача.
    """
    if not data:
        return set()
    items = data if isinstance(data, list) else str(data).split("/")
    return {normalize_modality(str(m)) for m in items if m and str(m).strip()}


# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================
#
# Здесь сосредоточены базовые параметры модели:
# - веса приоритетов для objective;
# - SLA/дедлайны по приоритетам;
# - типовые длительности исследований по модальностям;
# - параметры exact MILP.
#
# Замечание: веса и дедлайны жёстко зашиты в коде. Если бизнес-правила
# изменятся, править нужно именно этот блок.
#

# Веса w_i в целевой функции Σ w_i T_i.
PRIORITY_WEIGHTS = {"cito": 36.0, "asap": 3.0, "normal": 1.0}

# Веса для этапа выбора исследований в exact MILP.
SELECTION_PRIORITY_SCORES = {"cito": 100000.0, "asap": 1000.0, "normal": 1.0}

# Дедлайны d_i в часах от created_at.
DEADLINE_HOURS = {"cito": 2, "asap": 3, "normal": 72}

# Грубая длительность исследования в минутах по модальности.
# Используется как рабочая оценка для планирования времени врача.
MODALITY_DURATION_MINUTES = {
    "XRAY": 5,
    "CT": 15,
    "CT_CON": 25,
    "MRI": 20,
    "MRI_CON": 30,
    "MAMMO": 6,
    "FLUORO": 4,
    "ECG": 4,
    "HOLTER": 25,
    "EEG": 20,
    "US": 10,
}

# Размер временного слота exact-модели.
TIME_SLOT_MINUTES = 5

# Ограничения solver'а CBC.
MIP_TIME_LIMIT = 300
MIP_GAP_REL = 0.01

# Параметры формирования candidate pool.
# Идея: exact-модель не должна получать весь backlog, но и не должна работать
# на слишком узком shortlist, который почти полностью предрешает результат.
CANDIDATE_POOL_FACTOR = 3.0
CANDIDATE_POOL_MIN_SIZE = 120
CANDIDATE_POOL_MAX_SIZE = 600

# Виртуальный сдвиг окончания для штрафа неназначения.
# Интерпретация: если исследование не вошло в текущую смену, считаем, что оно
# будет завершено не раньше чем через сутки после конца планируемого горизонта.
UNASSIGNED_EXTRA_HOURS = 24.0

# Базовый штраф неназначения в "часах критерия".
# Нужен, чтобы модель не была безразлична между:
# - ранним назначением с нулевой просрочкой;
# - переносом исследования, которое ещё не просрочено.
UNASSIGNED_BASE_HOURS = 4.0


# ==============================================================================
# СТРУКТУРЫ ДАННЫХ
# ==============================================================================
#
# Вместо постоянной работы прямо с Django-моделями сервис сначала переводит
# данные в компактные dataclass-структуры. Это упрощает расчёты и делает код
# более предсказуемым.
#


@dataclass
class StudyData:
    """
    Внутреннее представление исследования для алгоритма распределения.

    Поля:
    - research_number: внешний идентификатор исследования;
    - priority: приоритет (`cito`, `asap`, `normal`);
    - created_at: время создания исследования;
    - modality: множество допустимых модальностей исследования;
    - up_value: УП исследования;
    - duration_minutes: оценка длительности исследования в минутах;
    - deadline: крайний допустимый срок завершения;
    - weight: вес исследования в objective.
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
        """Длительность исследования в часах."""
        return self.duration_minutes / 60.0


@dataclass
class DoctorData:
    """
    Внутреннее представление врача для алгоритма распределения.

    Поля:
    - modality: множество модальностей, по которым врач может работать;
    - max_up: суточный лимит УП;
    - shift_start / shift_end: границы смены;
    - break_start / break_end: границы перерыва, если он задан;
    - assigned_ids: список исследований, назначенных в рамках текущего запуска;
    - used_up: накопленный УП после распределения;
    - used_minutes: накопленное занятое время после распределения.
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
        """Длительность перерыва в минутах."""
        if self.break_start and self.break_end and self.break_end > self.break_start:
            return (self.break_end - self.break_start).total_seconds() / 60.0
        return 0.0

    @property
    def shift_hours(self) -> float:
        """
        Эффективная длительность смены в часах.

        Это не просто (shift_end - shift_start), а смена за вычетом перерыва.
        """
        gross = (self.shift_end - self.shift_start).total_seconds() / 3600.0
        return max(0.0, gross - self.break_minutes / 60.0)

    @property
    def free_up(self) -> float:
        """Оставшийся лимит УП после уже назначенных исследований."""
        return max(0.0, self.max_up - self.used_up)


@dataclass
class ScheduleOption:
    """
    Один допустимый вариант старта исследования в exact-модели.

    Помимо базовых полей хранит metrics и objective_value, чтобы конкретную
    objective-функцию можно было менять независимо от solver-а.
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


class ObjectiveStrategy(ABC):
    code: str = "base"
    description: str = "Base objective"

    def __init__(
        self,
        *,
        priority_weights: Optional[Dict[str, float]] = None,
        selection_scores: Optional[Dict[str, float]] = None,
        **params: Any,
    ) -> None:
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.selection_scores = {**SELECTION_PRIORITY_SCORES, **(selection_scores or {})}
        self.params = params

    def selection_priority_score(self, study: "StudyData") -> float:
        return float(self.selection_scores.get(study.priority, 1.0))

    @abstractmethod
    def option_metrics(
        self,
        study: "StudyData",
        doctor: "DoctorData",
        start_dt: datetime,
        finish_dt: datetime,
    ) -> Dict[str, float]:
        raise NotImplementedError

    @abstractmethod
    def unassigned_objective_value(
        self,
        study: "StudyData",
        *,
        tardiness_hours: float,
        weighted_tardiness: float,
        completion_hours: float,
        base_hours: float,
        weight: float,
    ) -> float:
        raise NotImplementedError

    def unassigned_metrics(
        self,
        study: "StudyData",
        planning_horizon_end: datetime,
    ) -> Dict[str, float | datetime]:
        """
        Оценить штраф, если исследование НЕ вошло в текущую смену.

        Идея простая:
        - считаем виртуальное завершение после конца планируемого горизонта;
        - вычисляем метрики так, как будто исследование будет сделано позже;
        - добавляем небольшой базовый штраф неназначения.

        Благодаря этому objective влияет не только на порядок, но и на сам факт
        включения исследования в план текущего дня.
        """
        extra_hours = float(self.params.get("unassigned_extra_hours", UNASSIGNED_EXTRA_HOURS))
        base_hours = float(self.params.get("unassigned_base_hours", UNASSIGNED_BASE_HOURS))
        weight = self.priority_weights.get(study.priority, 1.0)

        virtual_finish_dt = planning_horizon_end + timedelta(hours=extra_hours)
        tardiness_hours = max(
            0.0,
            (virtual_finish_dt - study.deadline).total_seconds() / 3600.0,
        )
        weighted_tardiness = tardiness_hours * weight
        completion_hours = max(
            0.0,
            (virtual_finish_dt - study.created_at).total_seconds() / 3600.0,
        )
        objective_value = self.unassigned_objective_value(
            study,
            tardiness_hours=tardiness_hours,
            weighted_tardiness=weighted_tardiness,
            completion_hours=completion_hours,
            base_hours=base_hours,
            weight=weight,
        )
        return {
            "virtual_finish_dt": virtual_finish_dt,
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": float(objective_value),
        }


class WeightedTardinessLexicographicObjective(ObjectiveStrategy):
    code = "weighted_tardiness_lexicographic"
    description = (
        "MIN Σ_i w_i*T_i по назначенным + штрафы за неназначение в текущей смене"
    )

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weighted_tardiness = tardiness_hours * self.priority_weights.get(study.priority, 1.0)
        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": weighted_tardiness,
        }

    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours,
        weighted_tardiness,
        completion_hours,
        base_hours,
        weight,
    ) -> float:
        return weighted_tardiness + weight * base_hours


class TardinessLexicographicObjective(ObjectiveStrategy):
    code = "tardiness_lexicographic"
    description = (
        "MIN Σ_i T_i по назначенным + штрафы за неназначение в текущей смене"
    )

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weighted_tardiness = tardiness_hours * self.priority_weights.get(study.priority, 1.0)
        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": tardiness_hours,
        }

    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours,
        weighted_tardiness,
        completion_hours,
        base_hours,
        weight,
    ) -> float:
        return tardiness_hours + base_hours

class MaxAssignmentsObjective(ObjectiveStrategy):
    code = "max_assignments"
    description = (
        "MAX числа назначений "
        "(через большой штраф за неназначение) "
        "+ слабый tie-break по просрочке"
    )

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weight = self.priority_weights.get(study.priority, 1.0)
        weighted_tardiness = tardiness_hours * weight

        # Маленький коэффициент, чтобы:
        # 1) сначала максимизировалось число назначений;
        # 2) среди равных по числу назначений решений выбиралось
        #    решение с меньшей просрочкой.
        epsilon = float(self.params.get("epsilon", 1e-3))

        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": epsilon * tardiness_hours,
        }

    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours,
        weighted_tardiness,
        completion_hours,
        base_hours,
        weight,
    ) -> float:
        # Большой штраф за неназначение.
        # Тогда модель будет брать максимум возможных исследований.
        unassigned_penalty = float(self.params.get("unassigned_penalty", 1e6))
        return unassigned_penalty


class CitoFirstThenWeightedRestLexicographicObjective(ObjectiveStrategy):
    code = "cito_first_then_weighted_rest_lexicographic"
    description = (
        "CITO приоритизируются сильнее; "
        "для назначенных: MIN Σ T_i для CITO + Σ w_i*T_i для ASAP/NORMAL; "
        "для неназначенных CITO используется более жёсткий штраф"
    )

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weight = self.priority_weights.get(study.priority, 1.0)
        weighted_tardiness = tardiness_hours * weight

        # Для CITO — без весов.
        # Для ASAP/NORMAL — по весам.
        if study.priority == "cito":
            objective_value = tardiness_hours
        else:
            objective_value = weighted_tardiness

        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": objective_value,
        }

    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours,
        weighted_tardiness,
        completion_hours,
        base_hours,
        weight,
    ) -> float:
        # В текущей одноэтапной модели именно тут задаётся,
        # насколько "дорого" оставить исследование неназначенным.
        #
        # Делаем CITO заметно дороже, чем ASAP/NORMAL,
        # чтобы solver сначала старался включить именно их.

        cito_unassigned_multiplier = float(
            self.params.get("cito_unassigned_multiplier", 10.0)
        )

        if study.priority == "cito":
            # Без весов, но с усиленным штрафом за неназначение CITO.
            return cito_unassigned_multiplier * (tardiness_hours + base_hours)

        # Для ASAP/NORMAL — стандартная взвешенная логика.
        return weighted_tardiness + weight * base_hours

class PriorityTierTardinessMultiPassObjective(ObjectiveStrategy):
    code = "priority_tier_tardiness_multipass"
    description = (
        "Multi-pass: отдельно решаются CITO, затем ASAP, затем NORMAL; "
        "внутри каждой категории минимизируется отставание без весов"
    )

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weight = self.priority_weights.get(study.priority, 1.0)
        weighted_tardiness = tardiness_hours * weight

        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": tardiness_hours,
        }

    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours,
        weighted_tardiness,
        completion_hours,
        base_hours,
        weight,
    ) -> float:
        return tardiness_hours + base_hours


# ==============================================================================
# СЕРВИС РАСПРЕДЕЛЕНИЯ
# ==============================================================================


class DistributionService:
    """
    Главный сервис оффлайн-распределения исследований.

    Общий сценарий работы:
    1. Загружаем врачей с расписанием на target_date.
    2. Загружаем неназначенные исследования из backlog.
    3. Формируем shortlist на текущий день.
    4. Пытаемся решить exact MILP для shortlist.
    5. Если exact-режим недоступен — используем greedy fallback.
    6. Собираем подробный ответ для UI и, при необходимости, сохраняем результат.
    """

    def __init__(
        self,
        target_date: Optional[datetime] = None,
        preview_mode: bool = False,
        objective: Optional[str] = None,
        priority_weights: Optional[Dict[str, float]] = None,
        selection_scores: Optional[Dict[str, float]] = None,
        deadline_hours: Optional[Dict[str, float]] = None,
        objective_params: Optional[Dict[str, Any]] = None,
    ):
        """
        Инициализация сервиса.

        Параметры:
        - target_date: дата, на которую строится распределение;
        - preview_mode: если True, результат не записывается в БД;
        - objective: код objective-стратегии;
        - priority_weights: пользовательские веса для objective;
        - selection_scores: пользовательские веса этапа выбора исследований;
        - deadline_hours: пользовательские SLA по приоритетам;
        - objective_params: дополнительные параметры objective.
        """
        self.now = timezone.now()
        self.target_date = target_date or self.now.date()
        self.preview_mode = preview_mode
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.selection_scores = {**SELECTION_PRIORITY_SCORES, **(selection_scores or {})}
        self.deadline_hours = {**DEADLINE_HOURS, **(deadline_hours or {})}
        self.objective_params = dict(objective_params or {})
        self._debug: List[str] = []

        self._objective_registry = self._build_objective_registry()
        self.objective: ObjectiveStrategy
        self.objective_code = ""
        self.objective_description = ""
        self.set_objective(objective or "weighted_tardiness_lexicographic")

    def set_preview_mode(self, preview: bool = True):
        """Включить или выключить режим предпросмотра."""
        self.preview_mode = preview

    def _build_objective_registry(self) -> Dict[str, Type[ObjectiveStrategy]]:
        return {
            WeightedTardinessLexicographicObjective.code: WeightedTardinessLexicographicObjective,
            TardinessLexicographicObjective.code: TardinessLexicographicObjective,
            
            MaxAssignmentsObjective.code: MaxAssignmentsObjective,
            CitoFirstThenWeightedRestLexicographicObjective.code: CitoFirstThenWeightedRestLexicographicObjective,
            PriorityTierTardinessMultiPassObjective.code: PriorityTierTardinessMultiPassObjective,
        }

    def _instantiate_objective(self, objective: str) -> ObjectiveStrategy:
        cls = self._objective_registry.get(objective, WeightedTardinessLexicographicObjective)
        return cls(
            priority_weights=self.priority_weights,
            selection_scores=self.selection_scores,
            **self.objective_params,
        )

    def _objective_meta(self) -> Dict[str, Any]:
        """Вернуть краткое описание текущей objective-функции для ответа API."""
        return {
            "code": self.objective_code,
            "description": self.objective_description,
            "priority_weights": self.priority_weights,
            "selection_scores": self.selection_scores,
            "deadline_hours": self.deadline_hours,
            "objective_params": self.objective_params,
        }

    def _log(self, msg: str):
        """
        Записать сообщение в системный лог и во внутренний debug-список.

        `_debug` затем отдаётся на фронт, чтобы можно было понимать, что именно
        происходило во время распределения.
        """
        logger.info(msg)
        self._debug.append(msg)

    def set_objective(self, objective: str) -> None:
        """Переключить objective-стратегию."""
        self.objective = self._instantiate_objective(objective)
        self.objective_code = self.objective.code
        self.objective_description = self.objective.description
        self._log(f"Objective переключена на {self.objective_code}")

    def _build_assignment_payload(
        self,
        study: StudyData,
        doctor: DoctorData,
        start_dt: datetime,
        finish_dt: datetime,
        metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "start_dt": start_dt,
            "finish_dt": finish_dt,
            "selection_priority_score": self.objective.selection_priority_score(study),
        }
        for key, value in metrics.items():
            payload[key] = float(value)
        payload.setdefault("objective_value", float(metrics.get("objective_value", 0.0)))
        payload.setdefault("tardiness_hours", 0.0)
        payload.setdefault(
            "weighted_tardiness",
            float(payload["tardiness_hours"]) * self.priority_weights.get(study.priority, 1.0),
        )
        return payload

    def _make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        Привести datetime к timezone-aware формату.

        В Django легко столкнуться со смешением aware и naive datetime.
        Для расчётов это критично, поэтому здесь приводим значения к единому виду.
        """
        if dt is None:
            return None
        return dt if timezone.is_aware(dt) else timezone.make_aware(dt)

    def _modality_ok(self, study_mods: Set[str], doc_mods: Set[str]) -> bool:
        """
        Проверить совместимость модальностей исследования и врача.

        Правило:
        - если у врача нет модальностей, он не подходит;
        - если у исследования модальность не указана, считаем его совместимым с
          любым врачом;
        - иначе нужен непустой intersection множеств модальностей.
        """
        if not doc_mods:
            return False
        if not study_mods:
            return True
        return bool(study_mods & doc_mods)

    def _align_to_work_time(self, doctor: DoctorData, dt: datetime) -> datetime:
        """
        Сдвинуть момент времени к допустимому рабочему времени врача.

        Что делает метод:
        - если время раньше начала смены, переносит его на shift_start;
        - если время попало в перерыв, переносит его на конец перерыва.

        Это базовый helper, который используется почти во всех расчётах времени.
        """
        if dt < doctor.shift_start:
            dt = doctor.shift_start
        if (
            doctor.break_start
            and doctor.break_end
            and doctor.break_start <= dt < doctor.break_end
        ):
            dt = doctor.break_end
        return dt

    def _work_minutes_between(
        self, doctor: DoctorData, start: datetime, end: datetime
    ) -> float:
        """
        Посчитать, сколько рабочих минут врача содержится в интервале [start, end].

        При этом:
        - интервалы за пределами смены отсекаются;
        - время, попадающее в перерыв, вычитается.

        Метод нужен в первую очередь для грубой оценки доступной мощности врача.
        """
        start = max(start, doctor.shift_start)
        end = min(end, doctor.shift_end)
        if end <= start:
            return 0.0

        total = (end - start).total_seconds() / 60.0
        if doctor.break_start and doctor.break_end:
            ov_start = max(start, doctor.break_start)
            ov_end = min(end, doctor.break_end)
            if ov_end > ov_start:
                total -= (ov_end - ov_start).total_seconds() / 60.0
        return max(0.0, total)

    def _remaining_work_minutes(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> float:
        """
        Оценить, сколько рабочих минут у врача осталось доступными.

        `prebooked_minutes` — это уже занятое или заранее зарезервированное время,
        которое нужно учитывать до начала нового распределения.
        """
        effective_start = self._effective_start_after_prebook(doctor, prebooked_minutes)
        available = self._work_minutes_between(doctor, effective_start, doctor.shift_end)
        return max(0.0, available)

    def _planning_horizon_end(self, doctors: List[DoctorData]) -> datetime:
        """
        Конец планируемого горизонта для оценки штрафов неназначения.

        Обычно это самый поздний конец смены среди доступных врачей.
        """
        if not doctors:
            return self.now
        return max(d.shift_end for d in doctors)

    def _add_work_minutes(
        self, doctor: DoctorData, start: datetime, minutes: float
    ) -> datetime:
        """
        Добавить к моменту `start` указанное количество РАБОЧИХ минут врача.

        Это один из самых важных методов во всём сервисе.
        Он не просто делает `start + timedelta(minutes=...)`, а двигается по
        реальному календарю врача:
        - учитывает начало смены;
        - пропускает перерыв;
        - не считает нерабочие интервалы;
        - если минут больше, чем осталось в смене, возвращает момент уже за её
          пределами.

        Именно этот helper позволяет корректно вычислять фактическое `finish_dt`
        и, следовательно, точное `C_i` в objective Σ w_i T_i.
        """
        remaining = max(0.0, float(minutes))
        current = self._align_to_work_time(doctor, start)

        while remaining > 1e-9:
            current = self._align_to_work_time(doctor, current)

            if current >= doctor.shift_end:
                return current + timedelta(minutes=remaining)

            next_stop = doctor.shift_end
            if doctor.break_start and doctor.break_end and current < doctor.break_start:
                next_stop = min(next_stop, doctor.break_start)

            available = max(0.0, (next_stop - current).total_seconds() / 60.0)

            if remaining <= available + 1e-9:
                return current + timedelta(minutes=remaining)

            remaining -= available
            current = next_stop

            if (
                doctor.break_start
                and doctor.break_end
                and current == doctor.break_start
            ):
                current = doctor.break_end

        return current

    def _effective_start_after_prebook(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> datetime:
        """
        Посчитать фактический старт врача с учётом already booked времени.

        В качестве базовой точки берётся максимум из:
        - начала смены;
        - текущего времени `self.now`.

        После этого к базовой точке добавляются заранее занятые рабочие минуты.
        """
        base = max(doctor.shift_start, self.now)
        return self._add_work_minutes(doctor, base, prebooked_minutes)

    def _round_up_to_slot(self, dt: datetime) -> datetime:
        """
        Округлить время вверх до ближайшей границы временного слота.

        Exact MILP дискретизирует время слотами по TIME_SLOT_MINUTES.
        Поэтому все допустимые старты должны лежать на этих границах.
        """
        minute = dt.minute
        remainder = minute % TIME_SLOT_MINUTES
        if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
            return dt.replace(second=0, microsecond=0)
        delta = TIME_SLOT_MINUTES - remainder if remainder else 0
        rounded = dt + timedelta(minutes=delta)
        return rounded.replace(second=0, microsecond=0)

    def _execution_segments(
        self, doctor: DoctorData, start: datetime, minutes: float
    ) -> List[Tuple[datetime, datetime]]:
        """
        Разбить выполнение исследования на рабочие сегменты.

        Зачем это нужно:
        если исследование началось до перерыва и заканчивается после перерыва,
        его исполнение состоит из двух сегментов. Exact-модель должна понимать,
        какие временные слоты действительно заняты этим исследованием.

        Результат — список интервалов `(segment_start, segment_end)`.
        """
        remaining = max(0.0, float(minutes))
        current = self._align_to_work_time(doctor, start)
        segments: List[Tuple[datetime, datetime]] = []

        while remaining > 1e-9 and current < doctor.shift_end:
            current = self._align_to_work_time(doctor, current)
            if current >= doctor.shift_end:
                break

            next_stop = doctor.shift_end
            if doctor.break_start and doctor.break_end and current < doctor.break_start:
                next_stop = min(next_stop, doctor.break_start)

            available = max(0.0, (next_stop - current).total_seconds() / 60.0)
            chunk = min(remaining, available)
            if chunk > 1e-9:
                seg_end = current + timedelta(minutes=chunk)
                segments.append((current, seg_end))
                remaining -= chunk
                current = seg_end
            else:
                current = next_stop

            if (
                doctor.break_start
                and doctor.break_end
                and current == doctor.break_start
            ):
                current = doctor.break_end

        return segments

    def _slot_boundaries(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> List[datetime]:
        """
        Сгенерировать все допустимые начала временных слотов для врача.

        Важно:
        - стартуем не раньше эффективного доступного времени врача;
        - пропускаем перерыв;
        - не выходим за пределы смены.

        Это основа для построения exact MILP: каждый слот становится кандидатом
        на старт исследования.
        """
        start = self._round_up_to_slot(
            self._effective_start_after_prebook(doctor, prebooked_minutes)
        )
        slots: List[datetime] = []
        current = start
        while current < doctor.shift_end:
            if (
                doctor.break_start
                and doctor.break_end
                and doctor.break_start <= current < doctor.break_end
            ):
                current = self._round_up_to_slot(doctor.break_end)
                continue
            slots.append(current)
            current += timedelta(minutes=TIME_SLOT_MINUTES)
        return slots

    def _occupied_slot_indices(
        self,
        doctor: DoctorData,
        segments: List[Tuple[datetime, datetime]],
        slot_boundaries: List[datetime],
    ) -> List[int]:
        """
        Найти индексы временных слотов, которые занимает исследование.

        Exact-модели нужно ограничение вида:
        "в один и тот же слот у врача не может стоять больше одного исследования".

        Поэтому для каждой опции старта мы заранее вычисляем, какие именно слоты
        она занимает.
        """
        occupied: List[int] = []
        for idx, slot_start in enumerate(slot_boundaries):
            slot_end = slot_start + timedelta(minutes=TIME_SLOT_MINUTES)
            if any(
                seg_start < slot_end and slot_start < seg_end
                for seg_start, seg_end in segments
            ):
                occupied.append(idx)
        return occupied

    # ── Загрузка данных ──────────────────────────────────────────────

    def _get_duration(self, study: Study) -> float:
        """
        Оценить длительность исследования в минутах.

        Если у исследования известна модальность study_type, длительность берётся
        из конфигурационного словаря `MODALITY_DURATION_MINUTES`.
        Иначе используется значение по умолчанию 15 минут.
        """
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return float(MODALITY_DURATION_MINUTES.get(mod, 15))
        return 15.0

    def _get_up(self, study: Study) -> float:
        """
        Получить УП исследования.

        Приоритет источников:
        1. Явное значение `study.study_type.up_value`, если оно есть.
        2. Грубая оценка по модальности.
        3. Значение по умолчанию 0.25.
        """
        if study.study_type and study.study_type.up_value:
            return float(study.study_type.up_value)
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return {"XRAY": 0.083, "CT": 0.25, "MRI": 0.333, "US": 0.10}.get(mod, 0.25)
        return 0.25

    def load_studies(
        self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
    ) -> List[StudyData]:
        """
        Загрузить все неназначенные исследования, которые можно рассматривать
        для распределения.

        Фильтрация:
        - берём только исследования без diagnostician;
        - опционально ограничиваем backlog временным окном `created_at`.

        На выходе Django-модели преобразуются в `StudyData`.
        Здесь же рассчитываются:
        - приоритет;
        - дедлайн;
        - вес исследования.
        """
        qs = Study.objects.filter(diagnostician__isnull=True).select_related("study_type")

        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lt=date_to)

        result: List[StudyData] = []
        for s in qs:
            priority = (s.priority or "normal").strip().lower()
            if priority not in PRIORITY_WEIGHTS:
                priority = "normal"

            created = self._make_aware(s.created_at) or self.now
            deadline = created + timedelta(hours=self.deadline_hours.get(priority, 72))
            weight = self.priority_weights.get(priority, 1.0)

            result.append(
                StudyData(
                    research_number=s.research_number,
                    priority=priority,
                    created_at=created,
                    modality=parse_modalities(
                        s.study_type.modality if s.study_type else ""
                    ),
                    up_value=self._get_up(s),
                    duration_minutes=self._get_duration(s),
                    deadline=deadline,
                    weight=weight,
                )
            )

        self._log(f"Исследований без назначения: {len(result)}")
        for s in result[:3]:
            self._log(
                f"  Пример: research_number={s.research_number}, priority={s.priority}, "
                f"modality={s.modality}, up={s.up_value}, dur={s.duration_minutes}мин"
            )
        return result

    def load_doctors(self) -> List[DoctorData]:
        """
        Загрузить врачей, у которых есть рабочее расписание на target_date.

        Что здесь происходит:
        - выбираются записи Schedule на целевую дату;
        - отбрасываются выходные и неактивные врачи;
        - формируются интервалы смены и перерыва;
        - модальности врача приводятся к нормализованному множеству.
        """
        target = self.target_date
        schedules = Schedule.objects.filter(
            work_date=target, is_day_off=0
        ).select_related("doctor")

        self._log(f"Расписаний на {target}: {schedules.count()}")

        result: List[DoctorData] = []
        for sch in schedules:
            doc = sch.doctor
            if not doc or not doc.is_active:
                self._log(
                    f"  Пропуск: врач {getattr(doc, 'id', '?')}, active={getattr(doc, 'is_active', '?')}"
                )
                continue

            max_up = float(doc.max_up_per_day or 50)

            if sch.time_start and sch.time_end:
                s_start = timezone.make_aware(datetime.combine(target, sch.time_start))
                s_end = timezone.make_aware(datetime.combine(target, sch.time_end))
            else:
                # Если в расписании время смены не задано, используем разумный дефолт.
                s_start = self.now.replace(hour=9, minute=0, second=0, microsecond=0)
                s_end = self.now.replace(hour=17, minute=0, second=0, microsecond=0)

            b_start = (
                timezone.make_aware(datetime.combine(target, sch.break_start))
                if sch.break_start
                else None
            )
            b_end = (
                timezone.make_aware(datetime.combine(target, sch.break_end))
                if sch.break_end
                else None
            )

            break_h = (
                (b_end - b_start).total_seconds() / 3600.0 if b_start and b_end else 0.0
            )
            shift_h = (s_end - s_start).total_seconds() / 3600.0
            mods = parse_modalities(doc.modality)

            self._log(
                f"  Врач {doc.fio_alias} (id={doc.id}): "
                f"max_up={max_up}, смена={shift_h:.1f}ч, "
                f"перерыв={break_h * 60:.0f}мин, эфф.время={shift_h - break_h:.1f}ч, мод={list(mods)}"
            )

            result.append(
                DoctorData(
                    id=doc.id,
                    name=doc.fio_alias or f"Врач {doc.id}",
                    modality=mods,
                    max_up=max_up,
                    shift_start=s_start,
                    shift_end=s_end,
                    break_start=b_start,
                    break_end=b_end,
                )
            )

        self._log(f"Врачей загружено: {len(result)}")
        return result

    # ── Candidate pool на день ──────────────────────────────────────

    def _candidate_priority_key(self, study: StudyData) -> Tuple:
        """
        Построить ключ сортировки исследования для формирования candidate pool.

        Логика bucket'ов:
        0 - просроченные CITO;
        1 - просроченные ASAP;
        2 - просроченные NORMAL;
        3 - исследования, чей дедлайн наступает не позже target_date;
        4 - остальные.

        Далее внутри bucket используется приоритет и более ранние сроки.
        """
        overdue = study.deadline < self.now
        pr = {"cito": 0, "asap": 1, "normal": 2}.get(study.priority, 2)
        if overdue and study.priority == "cito":
            bucket = 0
        elif overdue and study.priority == "asap":
            bucket = 1
        elif overdue and study.priority == "normal":
            bucket = 2
        elif study.deadline.date() <= self.target_date:
            bucket = 3
        else:
            bucket = 4
        return (bucket, pr, study.deadline, study.created_at)

    def _rough_daily_capacity_count(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> int:
        """
        Грубо оценить, сколько исследований в принципе может поместиться в день.

        Эта оценка нужна только для выбора размера candidate pool.
        Она НЕ является частью objective и НЕ определяет окончательный план.

        Для каждого врача оцениваем мощность по совместимым исследованиям:
        - по времени: available_minutes / avg_duration;
        - по УП: max_up / avg_up.

        Затем берём минимум из этих двух оценок и суммируем по врачам.
        """
        total_capacity = 0.0
        prebooked = doc_prebooked_minutes or {}

        for d in doctors:
            compatible = [s for s in studies if self._modality_ok(s.modality, d.modality)]
            if not compatible:
                continue

            available_minutes = self._remaining_work_minutes(d, prebooked.get(d.id, 0.0))
            if available_minutes <= 1e-9 or d.max_up <= 1e-9:
                continue

            avg_duration = sum(s.duration_minutes for s in compatible) / len(compatible)
            avg_up = sum(s.up_value for s in compatible) / len(compatible)

            by_minutes = available_minutes / max(avg_duration, 1e-9)
            by_up = d.max_up / max(avg_up, 1e-9)
            total_capacity += max(0.0, min(by_minutes, by_up))

        return max(1, int(round(total_capacity))) if studies and doctors else 0

    def build_candidate_pool(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> List[StudyData]:
        """
        Построить расширенный candidate pool исследований на текущий день.

        Это НЕ окончательное расписание и НЕ жёсткий shortlist по ресурсам.
        Задача метода — передать в exact-модель достаточно широкий набор
        кандидатов, чтобы именно objective-функция влияла на итоговое решение.

        Принцип работы:
        - сначала отбрасываем исследования, которые вообще несовместимы со всеми
          врачами или заведомо не помещаются ни одному врачу по УП/длительности;
        - затем сортируем кандидатов по приоритету и дедлайну;
        - после этого берём не ровно дневную мощность, а пул в 3 раза больше
          грубой оценки дневной ёмкости (с ограничением сверху и снизу).

        Важно:
        этот метод больше НЕ расходует ресурсы врачей по ходу отбора. То есть он
        не предрешает план дня, а только ограничивает размер входа для exact MILP.
        """
        feasible: List[StudyData] = []
        prebooked = doc_prebooked_minutes or {}

        for s in studies:
            fits_somewhere = False
            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if s.up_value > d.max_up + 1e-9:
                    continue
                if s.duration_minutes > self._remaining_work_minutes(d, prebooked.get(d.id, 0.0)) + 1e-9:
                    continue
                fits_somewhere = True
                break
            if fits_somewhere:
                feasible.append(s)

        ordered = sorted(feasible, key=self._candidate_priority_key)
        rough_capacity = self._rough_daily_capacity_count(
            ordered, doctors, doc_prebooked_minutes=doc_prebooked_minutes
        )

        target_size = int(round(rough_capacity * CANDIDATE_POOL_FACTOR))
        target_size = max(target_size, CANDIDATE_POOL_MIN_SIZE if ordered else 0)
        target_size = min(target_size, CANDIDATE_POOL_MAX_SIZE if ordered else 0)
        target_size = min(target_size, len(ordered))

        selected = ordered[:target_size]

        n_cito = sum(1 for s in selected if s.priority == "cito")
        n_asap = sum(1 for s in selected if s.priority == "asap")
        n_normal = sum(1 for s in selected if s.priority == "normal")

        self._log(
            f"Candidate pool: feasible={len(feasible)} из {len(studies)}, "
            f"rough_capacity≈{rough_capacity}, target={target_size}, "
            f"CITO={n_cito}, ASAP={n_asap}, NORMAL={n_normal}"
        )
        return selected


    def _make_pass_doctors(
        self,
        doctors: List[DoctorData],
        used_up_by_doctor: Optional[Dict[int, float]] = None,
    ) -> List[DoctorData]:
        """
        Построить временный список врачей для очередного прохода multi-pass.

        Важно: exact- и greedy-решатели уже умеют учитывать заранее занятое
        ВРЕМЯ через `doc_prebooked_minutes`, но не знают о ранее израсходованном
        УП. Поэтому для очередного прохода мы создаём копии врачей с уменьшенным
        `max_up`.

        Это позволяет решать задачу по приоритетам последовательно:
        - после CITO у врача остаётся меньше доступного УП;
        - этот остаток затем используется на проходе ASAP;
        - после него — на NORMAL.
        """
        used_up_by_doctor = used_up_by_doctor or {}
        result: List[DoctorData] = []

        for d in doctors:
            remaining_up = max(0.0, d.max_up - float(used_up_by_doctor.get(d.id, 0.0)))
            result.append(
                DoctorData(
                    id=d.id,
                    name=d.name,
                    modality=set(d.modality),
                    max_up=remaining_up,
                    shift_start=d.shift_start,
                    shift_end=d.shift_end,
                    break_start=d.break_start,
                    break_end=d.break_end,
                )
            )
        return result

    def _build_multipass_candidate_pool(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        priority: str,
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> List[StudyData]:
        """
        Построить входной пул для конкретного прохода multi-pass.

        Логика такая:
        - для CITO и ASAP берём ВСЕ feasible-исследования данной категории,
          чтобы проход действительно пытался распределить весь класс целиком;
        - для NORMAL оставляем обычный расширенный candidate pool, чтобы не
          раздувать MILP на всей плановой очереди.
        """
        if priority not in {"cito", "asap"}:
            return self.build_candidate_pool(
                studies,
                doctors,
                doc_prebooked_minutes=doc_prebooked_minutes,
            )

        feasible: List[StudyData] = []
        prebooked = doc_prebooked_minutes or {}
        ordered = sorted(studies, key=self._candidate_priority_key)

        for s in ordered:
            fits_somewhere = False
            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if s.up_value > d.max_up + 1e-9:
                    continue
                if s.duration_minutes > self._remaining_work_minutes(d, prebooked.get(d.id, 0.0)) + 1e-9:
                    continue
                fits_somewhere = True
                break
            if fits_somewhere:
                feasible.append(s)

        self._log(
            f"Multi-pass pool [{priority.upper()}]: feasible={len(feasible)} из {len(studies)} — берём весь feasible-набор"
        )
        return feasible

    def solve_priority_tier_multipass(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        *,
        use_mip: bool = True,
    ) -> Tuple[
        Dict[str, int],
        Dict[str, Dict],
        float,
        Dict[str, Dict[str, float | datetime]],
        List[StudyData],
    ]:
        """
        Реальный multi-pass по приоритетам: CITO → ASAP → NORMAL.

        На каждом проходе:
        1. берутся только исследования текущего приоритета;
        2. учитываются уже занятые минуты врачей;
        3. учитывается уже израсходованный УП;
        4. запускается exact MILP (или greedy fallback) только для этой группы;
        5. выбранные назначения фиксируются и уменьшают доступные ресурсы для
           следующего прохода.

        Именно этого поведения раньше и не хватало классу
        `priority_tier_tardiness_multipass`: objective была объявлена как
        multi-pass, но реально решалась одной общей MILP-задачей.
        """
        priority_order = ["cito", "asap", "normal"]
        study_map = {s.research_number: s for s in studies}

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}
        unassigned_meta: Dict[str, Dict[str, float | datetime]] = {}
        total_solver_obj = 0.0
        multipass_pool: List[StudyData] = []

        doctor_prebooked_minutes: Dict[int, float] = {d.id: 0.0 for d in doctors}
        doctor_used_up: Dict[int, float] = {d.id: 0.0 for d in doctors}

        for priority in priority_order:
            tier_studies = [s for s in studies if s.priority == priority]
            if not tier_studies:
                self._log(f"Multi-pass [{priority.upper()}]: исследований нет, проход пропущен")
                continue

            pass_doctors = self._make_pass_doctors(doctors, doctor_used_up)
            tier_pool = self._build_multipass_candidate_pool(
                tier_studies,
                pass_doctors,
                priority,
                doc_prebooked_minutes=doctor_prebooked_minutes,
            )
            multipass_pool.extend(tier_pool)

            if not tier_pool:
                self._log(
                    f"Multi-pass [{priority.upper()}]: candidate pool пуст, назначений на этом проходе не будет"
                )
                continue

            self._log(
                f"Multi-pass [{priority.upper()}]: старт прохода, pool={len(tier_pool)}, "
                f"already_booked_minutes={sum(doctor_prebooked_minutes.values()):.1f}, "
                f"already_used_up={sum(doctor_used_up.values()):.3f}"
            )

            if use_mip:
                pass_assignment, pass_details, pass_solver_obj, pass_unassigned_meta = self.solve_exact_mip(
                    tier_pool,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
            else:
                pass_assignment, pass_details = self.solve_greedy(
                    tier_pool,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
                planning_horizon_end = self._planning_horizon_end(pass_doctors)
                pass_unassigned_meta = {
                    s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                    for s in tier_pool
                    if s.research_number not in pass_assignment
                }
                pass_solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in pass_details.values())
                    + sum(float(item.get("objective_value", 0.0)) for item in pass_unassigned_meta.values())
                )

            total_solver_obj += float(pass_solver_obj)
            assignment.update(pass_assignment)
            details.update(pass_details)
            unassigned_meta.update(pass_unassigned_meta)

            for sid, did in pass_assignment.items():
                study = study_map[sid]
                doctor_prebooked_minutes[did] = doctor_prebooked_minutes.get(did, 0.0) + study.duration_minutes
                doctor_used_up[did] = doctor_used_up.get(did, 0.0) + study.up_value

            self._log(
                f"Multi-pass [{priority.upper()}]: назначено {len(pass_assignment)} / {len(tier_pool)}, "
                f"неназначено {len(pass_unassigned_meta)} / {len(tier_pool)}, obj={float(pass_solver_obj):.6f}"
            )

        self._log(
            f"Multi-pass ИТОГО: назначено {len(assignment)} / {len(studies)}, "
            f"pool={len(multipass_pool)}, obj_sum={float(total_solver_obj):.6f}"
        )
        return assignment, details, float(total_solver_obj), unassigned_meta, multipass_pool

    # ── Жадный fallback ─────────────────────────────────────────────

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict]]:
        """
        Распределить candidate pool жадным способом.

        Fallback теперь тоже учитывает текущую objective-стратегию: среди
        допустимых врачей выбирается тот вариант, у которого меньше
        objective_value, а при равенстве — более ранний finish_dt.
        """
        self._log(f"Запуск: жадный fallback по candidate pool (objective={self.objective_code})...")

        ordered = sorted(studies, key=self._candidate_priority_key)

        doctor_state: Dict[int, Dict[str, float | datetime]] = {}
        for d in doctors:
            prebooked = (doc_prebooked_minutes or {}).get(d.id, 0.0)
            doctor_state[d.id] = {
                "cursor": self._effective_start_after_prebook(d, prebooked),
                "used_up": 0.0,
            }

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}

        for s in ordered:
            best_doctor: Optional[DoctorData] = None
            best_finish: Optional[datetime] = None
            best_metrics: Optional[Dict[str, float]] = None

            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if float(doctor_state[d.id]["used_up"]) + s.up_value > d.max_up + 1e-9:
                    continue

                start_dt = self._align_to_work_time(d, doctor_state[d.id]["cursor"])
                finish_dt = self._add_work_minutes(d, start_dt, s.duration_minutes)
                if finish_dt > d.shift_end:
                    continue

                metrics = self.objective.option_metrics(s, d, start_dt, finish_dt)
                objective_value = float(metrics.get("objective_value", 0.0))

                candidate_key = (objective_value, finish_dt, start_dt, d.id)
                best_key = None
                if best_doctor is not None and best_finish is not None and best_metrics is not None:
                    best_key = (
                        float(best_metrics.get("objective_value", 0.0)),
                        best_finish,
                        self._align_to_work_time(best_doctor, doctor_state[best_doctor.id]["cursor"]),
                        best_doctor.id,
                    )

                if best_key is None or candidate_key < best_key:
                    best_doctor = d
                    best_finish = finish_dt
                    best_metrics = metrics

            if best_doctor is None or best_finish is None or best_metrics is None:
                continue

            start_dt = self._align_to_work_time(best_doctor, doctor_state[best_doctor.id]["cursor"])
            finish_dt = self._add_work_minutes(best_doctor, start_dt, s.duration_minutes)
            metrics = self.objective.option_metrics(s, best_doctor, start_dt, finish_dt)

            assignment[s.research_number] = best_doctor.id
            details[s.research_number] = self._build_assignment_payload(
                s, best_doctor, start_dt, finish_dt, metrics
            )

            doctor_state[best_doctor.id]["cursor"] = finish_dt
            doctor_state[best_doctor.id]["used_up"] = float(doctor_state[best_doctor.id]["used_up"]) + s.up_value

        self._log(f"Жадный fallback: назначено {len(assignment)} / {len(studies)}")
        return assignment, details

    # ── Exact MILP ──────────────────────────────────────────────────

    def _build_exact_options(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[List[ScheduleOption], Dict[int, List[int]], Dict[int, List[int]], Dict[int, List[datetime]]]:
        """
        Построить все допустимые опции старта для exact MILP.

        Метрики каждой опции считает текущая objective-стратегия. Поэтому exact
        solver остаётся универсальным: он минимизирует option.objective_value,
        а сама формула objective задаётся отдельно.
        """
        options: List[ScheduleOption] = []
        options_by_study: Dict[int, List[int]] = {i: [] for i in range(len(studies))}
        options_by_doctor: Dict[int, List[int]] = {j: [] for j in range(len(doctors))}
        slot_boundaries_by_doctor: Dict[int, List[datetime]] = {}

        option_id = 0
        for j, d in enumerate(doctors):
            prebooked = (doc_prebooked_minutes or {}).get(d.id, 0.0)
            slot_boundaries = self._slot_boundaries(d, prebooked)
            slot_boundaries_by_doctor[j] = slot_boundaries

            if not slot_boundaries:
                continue

            for i, s in enumerate(studies):
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if s.up_value > d.max_up + 1e-9:
                    continue

                for start_dt in slot_boundaries:
                    finish_dt = self._add_work_minutes(d, start_dt, s.duration_minutes)
                    if finish_dt > d.shift_end:
                        continue

                    segments = self._execution_segments(d, start_dt, s.duration_minutes)
                    occupied_slots = self._occupied_slot_indices(d, segments, slot_boundaries)
                    if not occupied_slots:
                        continue

                    metrics = self.objective.option_metrics(s, d, start_dt, finish_dt)
                    tardiness_hours = float(metrics.get(
                        "tardiness_hours",
                        max(0.0, (finish_dt - s.deadline).total_seconds() / 3600.0),
                    ))
                    weighted_tardiness = float(metrics.get(
                        "weighted_tardiness",
                        tardiness_hours * self.priority_weights.get(s.priority, 1.0),
                    ))
                    objective_value = float(metrics.get("objective_value", weighted_tardiness))

                    option = ScheduleOption(
                        option_id=option_id,
                        study_idx=i,
                        doctor_idx=j,
                        start_dt=start_dt,
                        finish_dt=finish_dt,
                        tardiness_hours=tardiness_hours,
                        weighted_tardiness=weighted_tardiness,
                        occupied_slots=occupied_slots,
                        metrics=metrics,
                        objective_value=objective_value,
                    )
                    options.append(option)
                    options_by_study[i].append(option_id)
                    options_by_doctor[j].append(option_id)
                    option_id += 1

        return options, options_by_study, options_by_doctor, slot_boundaries_by_doctor

    def solve_exact_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict[str, float | datetime]]]:
        """
        Одноэтапная exact-постановка.

        Для каждого исследования exact-модель должна выбрать РОВНО ОДНО из двух:
        1. один из допустимых вариантов назначения (конкретный врач + старт);
        2. оставить исследование неназначенным в текущей смене.

        Благодаря этому текущая objective-функция влияет и на состав назначенных
        исследований, и на их внутренний порядок. Это как раз убирает главную
        проблему старой двухэтапной схемы, где stage 1 фактически предопределял
        набор исследований ещё до применения основной objective.
        """
        try:
            import pulp
        except ImportError:
            self._log("PuLP не установлен → используем жадный fallback по candidate pool")
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            planning_horizon_end = self._planning_horizon_end(doctors)
            unassigned_meta = {
                s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                for s in studies
                if s.research_number not in assignment
            }
            solver_obj = (
                sum(float(item.get("objective_value", 0.0)) for item in details.values())
                + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
            )
            return assignment, details, float(solver_obj), unassigned_meta

        self._log(
            f"Exact MILP: candidate_pool={len(studies)}, doctors={len(doctors)}, objective={self.objective_code}"
        )

        options, options_by_study, _, slot_boundaries_by_doctor = self._build_exact_options(
            studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
        )

        self._log(f"  Кандидатных стартов: {len(options)}")
        if not options and studies:
            self._log("  Нет допустимых стартов → все исследования переходят в неназначенные")

        options_by_id = {option.option_id: option for option in options}
        planning_horizon_end = self._planning_horizon_end(doctors)
        unassigned_meta_by_study = {
            i: self.objective.unassigned_metrics(study, planning_horizon_end)
            for i, study in enumerate(studies)
        }

        def _add_common_constraints(prob, x_vars, y_vars):
            for study_idx, option_ids in options_by_study.items():
                if option_ids:
                    prob += (
                        pulp.lpSum(x_vars[oid] for oid in option_ids) + y_vars[study_idx] == 1,
                        f"StudyChoice_{study_idx}",
                    )
                else:
                    prob += y_vars[study_idx] == 1, f"StudyForcedUnassigned_{study_idx}"

            for doctor_idx, slot_boundaries in slot_boundaries_by_doctor.items():
                for slot_idx, _ in enumerate(slot_boundaries):
                    occupying = [
                        x_vars[option.option_id]
                        for option in options
                        if option.doctor_idx == doctor_idx and slot_idx in option.occupied_slots
                    ]
                    if occupying:
                        prob += (
                            pulp.lpSum(occupying) <= 1,
                            f"Cap_d{doctor_idx}_s{slot_idx}",
                        )

            for doctor_idx, d in enumerate(doctors):
                up_terms = [
                    studies[options_by_id[oid].study_idx].up_value * x_vars[oid]
                    for oid in x_vars
                    if options_by_id[oid].doctor_idx == doctor_idx
                ]
                if up_terms:
                    prob += pulp.lpSum(up_terms) <= d.max_up, f"UP_{doctor_idx}"

        try:
            prob = pulp.LpProblem(f"Exact_{self.objective_code}", pulp.LpMinimize)
            x = {
                option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary")
                for option in options
            }
            y = {
                study_idx: pulp.LpVariable(f"y_{study_idx}", cat="Binary")
                for study_idx in range(len(studies))
            }
            _add_common_constraints(prob, x, y)

            prob += (
                pulp.lpSum(option.objective_value * x[option.option_id] for option in options)
                + pulp.lpSum(
                    float(unassigned_meta_by_study[i]["objective_value"]) * y[i]
                    for i in y
                ),
                "Obj",
            )

            solver = pulp.PULP_CBC_CMD(
                timeLimit=MIP_TIME_LIMIT,
                msg=0,
                gapRel=MIP_GAP_REL,
            )
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            solver_obj = float(pulp.value(prob.objective) or 0.0)
            self._log(f"CBC: статус={status}, obj={solver_obj:.6f}")

            if status not in {"Optimal", "Integer Feasible"}:
                self._log("  Exact MILP не дал корректного решения → жадный fallback")
                assignment, details = self.solve_greedy(
                    studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
                )
                unassigned_meta = {
                    s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                    for s in studies
                    if s.research_number not in assignment
                }
                solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in details.values())
                    + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
                )
                return assignment, details, float(solver_obj), unassigned_meta

            chosen = [
                option for option in options if (pulp.value(x[option.option_id]) or 0) > 0.5
            ]
            unassigned_indices = [
                i for i in y if (pulp.value(y[i]) or 0) > 0.5
            ]

            assignment: Dict[str, int] = {}
            details: Dict[str, Dict] = {}
            for option in chosen:
                study = studies[option.study_idx]
                doctor = doctors[option.doctor_idx]
                assignment[study.research_number] = doctor.id
                details[study.research_number] = self._build_assignment_payload(
                    study, doctor, option.start_dt, option.finish_dt, option.metrics
                )

            unassigned_meta = {
                studies[i].research_number: dict(unassigned_meta_by_study[i])
                for i in unassigned_indices
            }

            self._log(
                f"Exact MILP: назначено {len(assignment)} / {len(studies)}, "
                f"неназначено {len(unassigned_meta)} / {len(studies)}"
            )
            return assignment, details, float(solver_obj), unassigned_meta

        except Exception as e:
            self._log(f"CBC ошибка: {e} → жадный fallback")
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            unassigned_meta = {
                s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                for s in studies
                if s.research_number not in assignment
            }
            solver_obj = (
                sum(float(item.get("objective_value", 0.0)) for item in details.values())
                + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
            )
            return assignment, details, float(solver_obj), unassigned_meta

    # ── Сохранение ───────────────────────────────────────────────────

    def save_to_db(self, assignment: Dict[str, int]) -> None:
        """
        Сохранить результат распределения в БД.

        Если сервис запущен в preview-режиме, изменения не сохраняются.
        Иначе для каждого исследования выставляются:
        - diagnostician_id;
        - статус `confirmed`;
        - planned_at = self.now.
        """
        if self.preview_mode:
            self._log("Режим предпросмотра - сохранение пропущено")
            return

        for study_id, doc_id in assignment.items():
            Study.objects.filter(research_number=study_id).update(
                diagnostician_id=doc_id,
                status="confirmed",
                planned_at=self.now,
            )

    # ── Главный метод ────────────────────────────────────────────────

    def distribute(
        self,
        use_mip: bool = True,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict:
        """
        Выполнить полный цикл распределения и вернуть подробный результат.

        Основные этапы метода:
        1. Логирование параметров запуска.
        2. Загрузка врачей и исследований.
        3. Формирование candidate pool текущего дня.
        4. Решение exact MILP или greedy fallback.
        5. Построение агрегированных метрик и структуры ответа для UI.
        6. Сохранение результата в БД, если это не preview.

        Параметры:
        - use_mip: если False, exact MILP принудительно не используется,
          даже если доступен PuLP.
        - date_from / date_to: окно отбора исследований по created_at.
        """
        self._log("=" * 60)
        self._log("OFFLINE DISTRIBUTION SERVICE")
        self._log(f"Время: {self.now}")
        self._log(f"Целевая дата: {self.target_date}")
        self._log(f"Режим предпросмотра: {self.preview_mode}")
        self._log(
            f"Целевая функция: {self.objective_code} | {self.objective_description}"
        )
        self._log("=" * 60)

        doctors = self.load_doctors()

        # Если сервис запущен позже начала смены, в симуляции "сегодняшнего" дня
        # текущее время сдвигается к min_start. Это позволяет избежать ситуации,
        # когда весь утренний интервал автоматически считается потерянным просто
        # из-за времени запуска сервиса.
        if doctors:
            min_start = min(d.shift_start for d in doctors)
            if self.now > min_start:
                self._log(
                    f"Текущее время {self.now} после начала смены {min_start}, используем min_start как единое now для симуляции"
                )
                self.now = min_start

        studies = self.load_studies(date_from, date_to)

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        if self.objective_code == PriorityTierTardinessMultiPassObjective.code:
            assignment, details, solver_obj, unassigned_meta, candidate_pool = self.solve_priority_tier_multipass(
                studies,
                doctors,
                use_mip=use_mip,
            )
            if not candidate_pool:
                return self._empty("Не удалось сформировать candidate pool ни на одном проходе multi-pass", studies)
        else:
            candidate_pool = self.build_candidate_pool(studies, doctors)
            if not candidate_pool:
                return self._empty("Не удалось сформировать candidate pool на текущий день", studies)

            if use_mip:
                assignment, details, solver_obj, unassigned_meta = self.solve_exact_mip(candidate_pool, doctors)
            else:
                assignment, details = self.solve_greedy(candidate_pool, doctors)
                planning_horizon_end = self._planning_horizon_end(doctors)
                unassigned_meta = {
                    s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                    for s in candidate_pool
                    if s.research_number not in assignment
                }
                solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in details.values())
                    + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
                )

        study_map = {s.research_number: s for s in studies}
        doctor_map = {d.id: d for d in doctors}

        # Переносим итог назначения в агрегаты врача, чтобы потом отдать doctor_stats.
        for sid, did in assignment.items():
            if sid not in study_map or did not in doctor_map:
                continue
            d = doctor_map[did]
            d.assigned_ids.append(sid)
            d.used_up += study_map[sid].up_value
            d.used_minutes += study_map[sid].duration_minutes

        all_assignments = []
        total_tardiness = 0.0
        total_weighted_tardiness = 0.0
        total_objective_value = 0.0
        total_unassigned_objective = 0.0
        pstats = {"cito": 0, "asap": 0, "normal": 0}

        # Сначала добавляем в итоговый список назначенные исследования.
        for sid, meta in details.items():
            s = study_map[sid]
            d = doctor_map[meta["doctor_id"]]
            tardiness = float(meta["tardiness_hours"])
            weighted_tardiness = float(meta["weighted_tardiness"])
            objective_value = float(meta.get("objective_value", weighted_tardiness))

            total_tardiness += tardiness
            total_weighted_tardiness += weighted_tardiness
            total_objective_value += objective_value
            pstats[s.priority] = pstats.get(s.priority, 0) + 1

            all_assignments.append(
                {
                    "study_number": s.research_number,
                    "study_modality": list(s.modality),
                    "doctor_id": d.id,
                    "doctor_name": d.name,
                    "doctor_modality": list(d.modality),
                    "priority": s.priority,
                    "deadline": s.deadline.isoformat(),
                    "start_time": meta["start_dt"].isoformat(),
                    "completion_time": meta["finish_dt"].isoformat(),
                    "tardiness_hours": round(tardiness, 2),
                    "weighted_tardiness": round(weighted_tardiness, 3),
                    "objective_value": round(objective_value, 3),
                    "up_value": s.up_value,
                    "is_overdue": s.deadline < self.now,
                }
            )

        # Затем добавляем исследования, которые остались неназначенными.
        # Это нужно фронту для вкладки "Не назначено" и общей аналитики.
        assigned_ids = set(assignment.keys())

        for s in studies:
            if s.research_number in assigned_ids:
                continue

            unassigned_item = unassigned_meta.get(s.research_number)
            if unassigned_item:
                total_unassigned_objective += float(unassigned_item.get("objective_value", 0.0))

            all_assignments.append(
                {
                    "study_number": s.research_number,
                    "study_modality": list(s.modality),
                    "doctor_id": None,
                    "doctor_name": None,
                    "doctor_modality": [],
                    "priority": s.priority,
                    "deadline": s.deadline.isoformat(),
                    "start_time": None,
                    "completion_time": None,
                    "tardiness_hours": None,
                    "weighted_tardiness": None,
                    "objective_value": round(float(unassigned_item.get("objective_value", 0.0)), 3)
                    if unassigned_item
                    else None,
                    "up_value": s.up_value,
                    "is_overdue": s.deadline < self.now,
                    "virtual_completion_time": unassigned_item.get("virtual_finish_dt").isoformat()
                    if unassigned_item and unassigned_item.get("virtual_finish_dt")
                    else None,
                }
            )

        # Сортировка нужна прежде всего для удобства UI:
        # - сначала назначенные;
        # - потом неназначенные;
        # - внутри — по врачу, времени старта и номеру исследования.
        all_assignments.sort(
            key=lambda item: (
                item["doctor_id"] is None,
                item["doctor_name"] or "",
                item["start_time"] or "",
                item["study_number"] or "",
            )
        )
        self.save_to_db(assignment)

        n_asgn = len(assignment)
        total_studies = len(studies)
        pool_size = len(candidate_pool)
        backlog_outside_pool = max(0, total_studies - pool_size)
        z = round(total_weighted_tardiness, 3)
        reported_objective_value = round(total_objective_value + total_unassigned_objective, 3)

        def _pct(value: float, total: float) -> float:
            """Безопасно посчитать процент `value / total * 100`."""
            if total <= 0:
                return 0.0
            return round(value / total * 100, 2)

        def _percentile(values: List[float], q: float) -> float:
            """
            Посчитать q-перцентиль линейной интерполяцией.

            Используется для p50/p95/p99 по tardiness.
            """
            if not values:
                return 0.0
            if len(values) == 1:
                return round(values[0], 2)
            ordered = sorted(values)
            idx = (len(ordered) - 1) * q
            lo = int(idx)
            hi = min(lo + 1, len(ordered) - 1)
            frac = idx - lo
            return round(ordered[lo] + (ordered[hi] - ordered[lo]) * frac, 2)

        # Словарь вида research_number -> tardiness для уже назначенных исследований.
        # Нужен для priority_breakdown и percentile-метрик.
        assigned_tardiness_by_study = {
            item["study_number"]: float(item["tardiness_hours"])
            for item in all_assignments
            if item["tardiness_hours"] is not None
        }

        priority_labels = {
            "normal": "plan",
            "asap": "asap",
            "cito": "cito",
        }
        priority_breakdown: Dict[str, Dict[str, float | int | str]] = {}

        overdue_total = 0
        overdue_assigned = 0

        # Формируем подробную статистику по каждому уровню приоритета.
        for priority_code, output_key in priority_labels.items():
            priority_studies = [s for s in studies if s.priority == priority_code]
            priority_total = len(priority_studies)
            priority_assigned = sum(
                1 for s in priority_studies if s.research_number in assignment
            )
            priority_overdue_total = sum(
                1 for s in priority_studies if s.deadline < self.now
            )
            priority_overdue_assigned = sum(
                1
                for s in priority_studies
                if s.deadline < self.now and s.research_number in assignment
            )
            priority_overdue_hours_total = round(
                sum(
                    max(0.0, (self.now - s.deadline).total_seconds() / 3600.0)
                    for s in priority_studies
                ),
                2,
            )
            priority_tardiness_values = [
                assigned_tardiness_by_study.get(s.research_number, 0.0)
                for s in priority_studies
            ]

            priority_breakdown[output_key] = {
                "priority": priority_code,
                "total": priority_total,
                "assigned": priority_assigned,
                "unassigned": priority_total - priority_assigned,
                "share_percent": _pct(priority_total, total_studies),
                "assigned_rate_percent": _pct(priority_assigned, priority_total),
                "overdue_total": priority_overdue_total,
                "overdue_assigned": priority_overdue_assigned,
                "overdue_unassigned": priority_overdue_total - priority_overdue_assigned,
                "overdue_rate_percent": _pct(priority_overdue_total, priority_total),
                "overdue_hours_total": priority_overdue_hours_total,
                "overdue_hours_avg": round(
                    priority_overdue_hours_total / priority_overdue_total, 2
                )
                if priority_overdue_total
                else 0.0,
                "tardiness_p50": _percentile(priority_tardiness_values, 0.5),
                "tardiness_p95": _percentile(priority_tardiness_values, 0.95),
                "tardiness_p99": _percentile(priority_tardiness_values, 0.99),
            }

            overdue_total += priority_overdue_total
            overdue_assigned += priority_overdue_assigned

        n_cito_total = int(priority_breakdown["cito"]["total"])
        n_asap_total = int(priority_breakdown["asap"]["total"])
        n_normal_total = int(priority_breakdown["plan"]["total"])

        n_cito_assigned = int(priority_breakdown["cito"]["assigned"])
        n_asap_assigned = int(priority_breakdown["asap"]["assigned"])
        n_normal_assigned = int(priority_breakdown["plan"]["assigned"])

        tardiness_values = [
            item["tardiness_hours"]
            for item in all_assignments
            if item["tardiness_hours"] is not None
        ]
        tardiness_p50 = _percentile(tardiness_values, 0.5)
        tardiness_p95 = _percentile(tardiness_values, 0.95)
        tardiness_p99 = _percentile(tardiness_values, 0.99)

        self._log(
            f"Итого: candidate_pool={pool_size}/{total_studies}, назначено={n_asgn}/{total_studies} "
            f"({_pct(n_asgn, total_studies):.2f}%) | "
            f"CITO: {n_cito_assigned}/{n_cito_total} | "
            f"ASAP: {n_asap_assigned}/{n_asap_total} | "
            f"NORMAL: {n_normal_assigned}/{n_normal_total} | "
            f"Backlog вне candidate_pool: {backlog_outside_pool} | Obj={reported_objective_value}"
        )

        if not self.preview_mode:
            self._log("Данные сохранены в БД")
        else:
            self._log("Данные НЕ сохранены в БД (режим предпросмотра)")

        return {
            "assigned": n_asgn,
            "unassigned": total_studies - n_asgn,
            "assigment_rate_percent": _pct(n_asgn, total_studies),
            "scheduled_pool_size": pool_size,
            "candidate_pool_size": pool_size,
            "backlog_outside_pool": backlog_outside_pool,
            "cito_assigned": n_cito_assigned,
            "cito_total": n_cito_total,
            "total_tardiness": round(total_tardiness, 2),
            "total_weighted_tardiness": z,
            "avg_tardiness": round(total_tardiness / n_asgn, 2) if n_asgn else 0,
            "tardiness_p50": tardiness_p50,
            "tardiness_p95": tardiness_p95,
            "tardiness_p99": tardiness_p99,
            "overdue_total": overdue_total,
            "overdue_assigned": overdue_assigned,
            "overdue_unassigned": overdue_total - overdue_assigned,
            "overdue_rate_percent": _pct(overdue_total, total_studies),
            "priority_breakdown": priority_breakdown,
            "assignments": all_assignments,
            "doctor_stats": [
                {
                    "doctor_id": d.id,
                    "doctor_name": d.name,
                    "assigned_studies": len(d.assigned_ids),
                    "total_up": round(d.used_up, 3),
                    "max_up": round(d.max_up, 3),
                    "load_percent": round(d.used_up / d.max_up * 100, 1)
                    if d.max_up
                    else 0,
                    "remaining_up": round(d.free_up, 3),
                }
                for d in doctors
            ],
            "priority_stats": pstats,
            "objective_function": self._objective_meta(),
            "solver_objective_value": round(float(solver_obj), 3),
            "reported_weighted_tardiness": z,
            "total_unassigned_objective": round(total_unassigned_objective, 3),
            "reported_objective_value": reported_objective_value,
            "message": (
                f"Оффлайн: candidate_pool {pool_size} из {total_studies}, назначено {n_asgn} "
                f"({_pct(n_asgn, total_studies):.2f}%). "
                f"CITO: {n_cito_assigned}/{n_cito_total}. objective={self.objective_code}, Obj={reported_objective_value}"
            ),
            "_debug": self._debug,
            "preview_mode": self.preview_mode,
            "target_date": self.target_date.isoformat(),
        }

    def _empty(self, message: str, studies: List = None) -> Dict:
        """
        Сформировать пустой ответ сервиса.

        Используется в ситуациях, когда распределение невозможно начать или
        продолжить: нет врачей, нет исследований, не сформировался candidate pool и т.п.
        """
        self._log(f"ПУСТО: {message}")
        return {
            "assigned": 0,
            "unassigned": len(studies or []),
            "assignment_rate_percent": 0.0,
            "scheduled_pool_size": 0,
            "backlog_outside_pool": len(studies or []),
            "total_tardiness": 0.0,
            "total_weighted_tardiness": 0.0,
            "avg_tardiness": 0,
            "tardiness_p50": 0.0,
            "tardiness_p95": 0.0,
            "tardiness_p99": 0.0,
            "overdue_total": 0,
            "overdue_assigned": 0,
            "overdue_unassigned": 0,
            "overdue_rate_percent": 0.0,
            "priority_breakdown": {
                "plan": {
                    "priority": "normal",
                    "total": 0,
                    "assigned": 0,
                    "unassigned": 0,
                    "share_percent": 0.0,
                    "assigned_rate_percent": 0.0,
                    "overdue_total": 0,
                    "overdue_assigned": 0,
                    "overdue_unassigned": 0,
                    "overdue_rate_percent": 0.0,
                    "overdue_hours_total": 0.0,
                    "overdue_hours_avg": 0.0,
                    "tardiness_p50": 0.0,
                    "tardiness_p95": 0.0,
                    "tardiness_p99": 0.0,
                },
                "asap": {
                    "priority": "asap",
                    "total": 0,
                    "assigned": 0,
                    "unassigned": 0,
                    "share_percent": 0.0,
                    "assigned_rate_percent": 0.0,
                    "overdue_total": 0,
                    "overdue_assigned": 0,
                    "overdue_unassigned": 0,
                    "overdue_rate_percent": 0.0,
                    "overdue_hours_total": 0.0,
                    "overdue_hours_avg": 0.0,
                    "tardiness_p50": 0.0,
                    "tardiness_p95": 0.0,
                    "tardiness_p99": 0.0,
                },
                "cito": {
                    "priority": "cito",
                    "total": 0,
                    "assigned": 0,
                    "unassigned": 0,
                    "share_percent": 0.0,
                    "assigned_rate_percent": 0.0,
                    "overdue_total": 0,
                    "overdue_assigned": 0,
                    "overdue_unassigned": 0,
                    "overdue_rate_percent": 0.0,
                    "overdue_hours_total": 0.0,
                    "overdue_hours_avg": 0.0,
                    "tardiness_p50": 0.0,
                    "tardiness_p95": 0.0,
                    "tardiness_p99": 0.0,
                },
            },
            "assignments": [],
            "doctor_stats": [],
            "priority_stats": {"cito": 0, "asap": 0, "normal": 0},
            "objective_function": self._objective_meta(),
            "solver_objective_value": 0.0,
            "reported_weighted_tardiness": 0.0,
            "message": message,
            "_debug": self._debug,
        }
