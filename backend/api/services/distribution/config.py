"""
Конфигурация сервиса оффлайн-распределения исследований.

Модуль выступает единым источником настроек для остальных компонентов:
- нормализация модальностей;
- веса приоритетов и SLA по дедлайнам;
- типовые длительности и УП по модальностям;
- параметры candidate pool;
- параметры exact MILP.
"""
from typing import Dict, Tuple

# Канонические обозначения модальностей.
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
    "ULTRASOUND": "US",
    "УЗИ": "US",
    "US": "US",
}

# Ключевые слова, по которым определяем исследования с контрастированием.
CONTRAST_KEYWORDS: Tuple[str, ...] = (
    "контраст",
    "контрастом",
    "contrast",
    "bolus",
    "болюс",
)

PRIORITY_ORDER = ("cito", "asap", "normal")
PRIORITY_WEIGHTS: Dict[str, float] = {"cito": 64.0, "asap": 8.0, "normal": 1.0}
DEADLINE_HOURS: Dict[str, int] = {"cito": 2, "asap": 24, "normal": 72}

# Типовые длительности исследований в минутах.
MODALITY_DURATION_MINUTES: Dict[str, float] = {
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

# Типовые УП по модальностям.
MODALITY_UP_VALUES: Dict[str, float] = {
    "FLUORO": 0.067,
    "MAMMO": 0.10,
    "XRAY": 0.083,
    "CT": 0.25,
    "CT_CON": 0.417,
    "MRI": 0.333,
    "MRI_CON": 0.50,
    "US": 0.10,
    "ECG": 0.067,
    "HOLTER": 0.417,
    "EEG": 0.333,
}

DEFAULT_DOCTOR_MAX_UP_PER_DAY = 50.0
DEFAULT_SHIFT_START_HOUR = 9
DEFAULT_SHIFT_END_HOUR = 17
DEFAULT_STUDY_DURATION_MINUTES = 15.0
DEFAULT_STUDY_UP_VALUE = 0.25

# Раскладываем исследования по слотам по 5 минут.
TIME_SLOT_MINUTES = 5

MIP_TIME_LIMIT = 300
MIP_GAP_REL = 0.01

CANDIDATE_POOL_FACTOR = 3.0
CANDIDATE_POOL_MIN_SIZE = 120
CANDIDATE_POOL_MAX_SIZE = 5000

# Оставлены как legacy-настройки на случай обратной совместимости.
UNASSIGNED_EXTRA_HOURS = 24.0
UNASSIGNED_BASE_HOURS = 4.0
