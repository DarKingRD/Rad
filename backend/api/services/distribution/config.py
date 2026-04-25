"""
Конфигурация сервиса оффлайн-распределения исследований.
"""
from typing import Dict

from ..modality_catalog import (
    MODALITY_DURATION_MINUTES as CATALOG_DURATION_MINUTES,
    MODALITY_UP_VALUES as CATALOG_UP_VALUES,
)

PRIORITY_ORDER = ("cito", "asap", "normal")
PRIORITY_WEIGHTS: Dict[str, float] = {"cito": 64.0, "asap": 8.0, "normal": 1.0}
DEADLINE_HOURS: Dict[str, int] = {"cito": 2, "asap": 24, "normal": 72}

MODALITY_DURATION_MINUTES: Dict[str, float] = {
    key: float(value) for key, value in CATALOG_DURATION_MINUTES.items()
}
MODALITY_UP_VALUES: Dict[str, float] = {
    key: float(value) for key, value in CATALOG_UP_VALUES.items()
}

DEFAULT_DOCTOR_MAX_UP_PER_DAY = 8.0
DEFAULT_SHIFT_START_HOUR = 9
DEFAULT_SHIFT_END_HOUR = 17
DEFAULT_STUDY_DURATION_MINUTES = 15.0
DEFAULT_STUDY_UP_VALUE = 0.25

TIME_SLOT_MINUTES = 5

MIP_TIME_LIMIT = 10000
MIP_GAP_REL = 0.01

CBC_THREADS = 1

# 0 означает auto: использовать до os.cpu_count(), но не больше числа врачей.
# Для Windows/Django безопаснее держать значение умеренным, например 4.
EXACT_OPTIONS_WORKERS = 6
EXACT_PARALLEL_MIN_DOCTORS = 2

# Удалять только те варианты, которые хуже, чем оставить исследование неназначенным
# до конца планового горизонта. Варианты с равной стоимостью остаются, чтобы
# не снижать долю назначений в отчёте при одинаковом objective.
EXACT_PRUNE_WORSE_THAN_UNASSIGNED = True

# Ограничения размера модели отключены: CBC получает полный набор вариантов.
EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR = None
EXACT_MAX_OPTIONS = None
