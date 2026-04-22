"""
Конфигурация сервиса оффлайн-распределения исследований.
"""
import os
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

MIP_TIME_LIMIT = 300
MIP_GAP_REL = 0.01


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_optional_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    if value.strip().lower() in {"none", "null", "0"}:
        return None
    try:
        return int(value)
    except ValueError:
        return default


_CPU_COUNT = os.cpu_count() or 1

# CBC threads help only when branch-and-bound has a search tree. For root-only
# solves they are expected to stay idle, but the value is useful for benchmarks.
CBC_THREADS = max(1, _env_int("CBC_THREADS", min(4, _CPU_COUNT)))

# This cap has the biggest effect on model size. With 50 variants the sample log
# creates 858k MPS columns; try 10/15/20 for speed-quality experiments.
EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR = max(
    1,
    _env_int("EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR", 50),
)
EXACT_MAX_OPTIONS = _env_optional_int("EXACT_MAX_OPTIONS", None)

# Candidate generation is independent per doctor, so it can be parallelized even
# when CBC itself solves the MILP at the root node.
EXACT_OPTION_BUILD_WORKERS = max(
    1,
    _env_int("EXACT_OPTION_BUILD_WORKERS", 1),
)
EXACT_PARALLEL_MIN_DOCTORS = max(2, _env_int("EXACT_PARALLEL_MIN_DOCTORS", 2))
