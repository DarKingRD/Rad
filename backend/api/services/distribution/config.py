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
from typing import Dict

# список модальностей
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

# веса исследований
PRIORITY_WEIGHTS = {"cito": 36.0, "asap": 3.0, "normal": 1.0}
# веса для обязательного назначения исследований (критерий-штраф)
SELECTION_PRIORITY_SCORES = {"cito": 100000.0, "asap": 1000.0, "normal": 1.0}
# дедлайны у исследований
DEADLINE_HOURS = {"cito": 2, "asap": 3, "normal": 72}

# затраты на исследование в минутах
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

# по каким слотам расскидывать исследования (по 5 минут слоты)
# т.е. если у нас исследование завершилось в 14:53,
# то следующее назначится в 14:55. Необходимо для быстрого решения.
TIME_SLOT_MINUTES = 5

MIP_TIME_LIMIT = 300
MIP_GAP_REL = 0.01

#
CANDIDATE_POOL_FACTOR = 3.0
CANDIDATE_POOL_MIN_SIZE = 120
CANDIDATE_POOL_MAX_SIZE = 600

UNASSIGNED_EXTRA_HOURS = 24.0
UNASSIGNED_BASE_HOURS = 4.0
