"""
Вспомогательные функции для нормализации и разбора модальностей.

Модуль позволяет привести строковые обозначения модальностей к единому
внутреннему формату, а также получить множество модальностей из поля,
пришедшего из БД или внешнего источника.
"""
from typing import Set

from .config import MODALITY_ALIASES


def normalize_modality(m: str) -> str:
    """
    Нормализовать строковое обозначение модальности.

    Если значение найдено в словаре алиасов, возвращается каноническое
    обозначение. Если значение пустое, возвращается "OTHER".
    """
    if not m:
        return "OTHER"
    return MODALITY_ALIASES.get(m.strip().upper(), m.strip().upper())


def parse_modalities(data) -> Set[str]:
    """
    Преобразовать исходное поле модальностей в множество нормализованных значений.

    Поддерживаются:
    - уже готовый список;
    - строка с разделителем "/";
    - пустое значение.

    На выходе всегда возвращается множество нормализованных модальностей.
    """
    if not data:
        return set()
    items = data if isinstance(data, list) else str(data).split("/")
    return {normalize_modality(str(m)) for m in items if m and str(m).strip()}
