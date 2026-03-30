"""
Стратегии целевых функций для сервиса распределения.

Модуль реализует набор objective-стратегий, которые определяют:
- как считать метрики варианта назначения;
- как штрафовать неназначенные исследования;
- какую функцию минимизировать в жадном и exact-режиме.

Все стратегии наследуются от абстрактного класса ObjectiveStrategy.
Через OBJECTIVE_REGISTRY можно выбрать нужную стратегию по строковому коду.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Type

from .config import (
    PRIORITY_WEIGHTS,
    SELECTION_PRIORITY_SCORES,
    UNASSIGNED_BASE_HOURS,
    UNASSIGNED_EXTRA_HOURS,
)


class ObjectiveStrategy(ABC):
    """
    Стратегии целевых функций для сервиса распределения.

    Модуль реализует набор objective-стратегий, которые определяют:
    - как считать метрики варианта назначения;
    - как штрафовать неназначенные исследования;
    - какую функцию минимизировать в жадном и exact-режиме.

    Все стратегии наследуются от абстрактного класса ObjectiveStrategy.
    Через OBJECTIVE_REGISTRY можно выбрать нужную стратегию по строковому коду.
    """
    code: str = "base"
    description: str = "Base objective"

    def __init__(
        self,
        *,
        priority_weights: Optional[Dict[str, float]] = None,
        selection_scores: Optional[Dict[str, float]] = None,
        **params: Any,
    ) -> None:
        """
        Инициализировать стратегию целевой функции.

        Параметры позволяют:
        - переопределить веса приоритетов;
        - переопределить selection scores;
        - передать дополнительные параметры конкретной objective-стратегии.
        """
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.selection_scores = {**SELECTION_PRIORITY_SCORES, **(selection_scores or {})}
        self.params = params

    def selection_priority_score(self, study) -> float:
        """
        Вернуть score исследования для этапа выбора и отображения.

        Значение не влияет напрямую на все objective-формулы, но используется
        как вспомогательная характеристика приоритета исследования.
        """
        return float(self.selection_scores.get(study.priority, 1.0))

    @abstractmethod
    def option_metrics(self,
                       study,
                       doctor,
                       start_dt: datetime,
                       finish_dt: datetime
                    ) -> Dict[str, float]:
        """
        Рассчитать метрики варианта назначения исследования.

        Реализация должна вернуть словарь, содержащий как минимум:
        - tardiness_hours;
        - weighted_tardiness;
        - completion_hours_from_created;
        - objective_value.

        Конкретный смысл objective_value задаётся реализацией стратегии.
        """
        raise NotImplementedError

    @abstractmethod
    def unassigned_objective_value(
        self,
        study,
        *,
        tardiness_hours: float,
        weighted_tardiness: float,
        completion_hours: float,
        base_hours: float,
        weight: float,
    ) -> float:
        """
        Рассчитать штраф objective за неназначенное исследование.

        Метод получает уже посчитанные производные показатели и должен вернуть
        итоговое значение штрафа в рамках выбранной стратегии.
        """
        raise NotImplementedError

    def unassigned_metrics(
        self,
        study,
        planning_horizon_end: datetime
    ) -> Dict[str, float | datetime]:
        """
        Рассчитать метрики для исследования, оставшегося неназначенным.

        Для этого вводится виртуальное время завершения после конца текущего
        планового горизонта. На его основе считаются:
        - просрочка;
        - взвешенная просрочка;
        - время выполнения от момента создания;
        - итоговый objective-штраф.
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
    """
    Стратегия минимизации взвешенной просрочки.

    Для назначенных исследований objective равна weighted tardiness.
    Для неназначенных добавляется дополнительный штраф, зависящий от веса
    приоритета и базового penalty-параметра.
    """
    code = "weighted_tardiness_lexicographic"
    description = "MIN Σ_i w_i*T_i по назначенным + штрафы за неназначение в текущей смене"

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

    def unassigned_objective_value(self,
                                   study,
                                   *,
                                   tardiness_hours,
                                   weighted_tardiness,
                                   completion_hours,
                                   base_hours,
                                   weight
                                ) -> float:
        return weighted_tardiness + weight * base_hours


class TardinessLexicographicObjective(ObjectiveStrategy):
    """
    Стратегия минимизации взвешенной просрочки.

    Для назначенных исследований objective равна weighted tardiness.
    Для неназначенных добавляется дополнительный штраф, зависящий от веса
    приоритета и базового penalty-параметра.
    """
    code = "tardiness_lexicographic"
    description = "MIN Σ_i T_i по назначенным + штрафы за неназначение в текущей смене"

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

    def unassigned_objective_value(self,
                                   study,
                                   *, tardiness_hours,
                                   weighted_tardiness,
                                   completion_hours,
                                   base_hours,
                                   weight
                                ) -> float:
        return tardiness_hours + base_hours


class MaxAssignmentsObjective(ObjectiveStrategy):
    """
    Стратегия минимизации обычной просрочки без весов внутри назначений.

    Используется в сценариях, где важнее минимизировать само отставание,
    а не его взвешенный вариант.
    """
    code = "max_assignments"
    description = "MAX числа назначений + слабый tie-break по просрочке"

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hours = max(0.0, (finish_dt - study.created_at).total_seconds() / 3600.0)
        weight = self.priority_weights.get(study.priority, 1.0)
        weighted_tardiness = tardiness_hours * weight
        epsilon = float(self.params.get("epsilon", 1e-3))

        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": epsilon * tardiness_hours,
        }

    def unassigned_objective_value(self,
                                   study,
                                   *,
                                   tardiness_hours,
                                   weighted_tardiness,
                                   completion_hours,
                                   base_hours,
                                   weight) -> float:
        return float(self.params.get("unassigned_penalty", 1e6))


class CitoFirstThenWeightedRestLexicographicObjective(ObjectiveStrategy):
    """
    Смешанная стратегия с усиленным приоритетом CITO.

    Для исследований CITO минимизируется обычная просрочка, а для ASAP и
    NORMAL — взвешенная просрочка. Для неназначенных CITO применяется
    более жёсткий штраф.
    """
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

        objective_value = tardiness_hours if study.priority == "cito" else weighted_tardiness

        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hours,
            "objective_value": objective_value,
        }

    def unassigned_objective_value(self, study, *, tardiness_hours, weighted_tardiness, completion_hours, base_hours, weight) -> float:
        cito_unassigned_multiplier = float(self.params.get("cito_unassigned_multiplier", 10.0))
        if study.priority == "cito":
            return cito_unassigned_multiplier * (tardiness_hours + base_hours)
        return weighted_tardiness + weight * base_hours


class PriorityTierTardinessMultiPassObjective(ObjectiveStrategy):
    """
    Стратегия для многоэтапного распределения по приоритетным слоям.

    Предполагается, что исследования обрабатываются отдельными проходами:
    сначала CITO, затем ASAP, затем NORMAL. Внутри каждого прохода
    минимизируется обычная просрочка без весов.
    """
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

    def unassigned_objective_value(self,
                                   study,
                                   *,
                                   tardiness_hours,
                                   weighted_tardiness,
                                   completion_hours,
                                   base_hours,
                                   weight
                                ) -> float:
        return tardiness_hours + base_hours


OBJECTIVE_REGISTRY: Dict[str, Type[ObjectiveStrategy]] = {
    WeightedTardinessLexicographicObjective.code:
        WeightedTardinessLexicographicObjective,
    TardinessLexicographicObjective.code:
        TardinessLexicographicObjective,
    MaxAssignmentsObjective.code:
        MaxAssignmentsObjective,
    CitoFirstThenWeightedRestLexicographicObjective.code:
        CitoFirstThenWeightedRestLexicographicObjective,
    PriorityTierTardinessMultiPassObjective.code:
        PriorityTierTardinessMultiPassObjective,
}
"""
Реестр доступных objective-стратегий.

Позволяет получить нужный класс стратегии по её строковому коду.
Используется сервисом при инициализации и переключении objective.
"""
