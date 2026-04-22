"""
Стратегии целевых функций для сервиса распределения.

Модуль реализует набор objective-стратегий, которые определяют:
- как считать метрики варианта назначения;
- как считать вклад неназначенных исследований;
- какую функцию минимизировать в жадном и exact-режиме.

Все стратегии наследуются от абстрактного класса ObjectiveStrategy.
Через OBJECTIVE_REGISTRY можно выбрать нужную стратегию по строковому коду.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Type

from .config import PRIORITY_WEIGHTS


class ObjectiveStrategy(ABC):
    """
    Базовый класс стратегий целевой функции.

    Важно:
    - для назначенных исследований objective считается по реальному времени finish_dt;
    - для неназначенных исследований objective считается на конец планового горизонта
      planning_horizon_end;
    - отдельного искусственного штрафа за неназначение здесь больше нет.
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
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.params = params

    @abstractmethod
    def option_metrics(
        self,
        study,
        doctor,
        start_dt: datetime,
        finish_dt: datetime,
    ) -> Dict[str, float]:
        """
        Рассчитать метрики варианта назначения исследования.

        Должны вернуться как минимум:
        - tardiness_hours;
        - weighted_tardiness;
        - completion_hours_from_created;
        - objective_value.
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
        Рассчитать вклад неназначенного исследования в objective.

        В новой постановке это не отдельный штраф, а та же самая просрочка,
        посчитанная на planning_horizon_end.
        """
        raise NotImplementedError

    def unassigned_metrics(
        self,
        study,
        planning_horizon_end: datetime,
    ) -> Dict[str, float | datetime]:
        """
        Рассчитать метрики неназначенного исследования.

        Неназначенное исследование считается оставшимся в очереди до конца
        текущего планового горизонта. Никакого дополнительного penalty
        поверх tardiness не добавляется.
        """
        weight = self.priority_weights.get(study.priority, 1.0)
        virtual_finish_dt = planning_horizon_end

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
            base_hours=0.0,
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
    Минимизация взвешенной просрочки всей очереди на горизонте планирования.

    Для назначенных:
        objective = w_i * T_i(finish_dt)

    Для неназначенных:
        objective = w_i * T_i(planning_horizon_end)
    """

    code = "weighted_tardiness_lexicographic"
    description = "MIN Σ_i w_i*T_i по всей очереди на текущем горизонте планирования"

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
        return weighted_tardiness


class TardinessLexicographicObjective(ObjectiveStrategy):
    """
    Минимизация обычной просрочки всей очереди на горизонте планирования.

    Для назначенных:
        objective = T_i(finish_dt)

    Для неназначенных:
        objective = T_i(planning_horizon_end)
    """

    code = "tardiness_lexicographic"
    description = "MIN Σ_i T_i по всей очереди на текущем горизонте планирования"

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
        return tardiness_hours


class MaxAssignmentsObjective(ObjectiveStrategy):
    """
    Экспериментальная стратегия максимизации числа назначений.

    Эту стратегию я не трогаю по смыслу: она не про очередь как tardiness-объект,
    а именно про максимум назначений.
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
        return float(self.params.get("unassigned_penalty", 1e6))


class PriorityTierTardinessMultiPassObjective(ObjectiveStrategy):
    """
    Multi-pass: сначала CITO, затем ASAP, затем NORMAL.

    Внутри каждого прохода минимизируется обычная просрочка всей очереди
    текущего слоя на горизонте планирования.
    """

    code = "priority_tier_tardiness_multipass"
    description = (
        "Multi-pass: отдельно решаются CITO, затем ASAP, затем NORMAL; "
        "внутри каждой категории минимизируется просрочка всей очереди "
        "на текущем горизонте планирования"
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
        return tardiness_hours


OBJECTIVE_REGISTRY: Dict[str, Type[ObjectiveStrategy]] = {
    WeightedTardinessLexicographicObjective.code: WeightedTardinessLexicographicObjective,
    TardinessLexicographicObjective.code: TardinessLexicographicObjective,
    MaxAssignmentsObjective.code: MaxAssignmentsObjective,
    PriorityTierTardinessMultiPassObjective.code: PriorityTierTardinessMultiPassObjective,
}
