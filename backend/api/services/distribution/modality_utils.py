"""
Вспомогательные функции для нормализации и разбора модальностей.
"""
from __future__ import annotations

import re
from typing import Iterable, Set

from ..modality_catalog import OTHER_MODALITY, normalize_modality_name, normalize_modalities

_SPLIT_RE = re.compile(r"[/,;|]+")


def normalize_modality(value: str, *context: object) -> str:
    """Нормализовать строковое обозначение модальности."""
    if not value:
        return OTHER_MODALITY
    return normalize_modality_name(value, *context)


def parse_modalities(data) -> Set[str]:
    """Преобразовать исходное поле модальностей в множество канонических значений."""
    if not data:
        return set()

    if isinstance(data, (list, tuple, set, frozenset)):
        raw_items: Iterable[object] = data
    else:
        raw_items = [item for item in _SPLIT_RE.split(str(data)) if item]

    return set(normalize_modalities(raw_items))


def is_contrast_study(*parts: object) -> bool:
    """Проверить, содержит ли текст исследования признак контрастирования."""
    normalized = normalize_modality_name("", *parts)
    return "с контрастом" in normalized.casefold()


def workload_modality(modality: str, *text_parts: object) -> str:
    """
    Вернуть каноническую модальность для расчёта длительности и УП.

    В отличие от старой реализации здесь не используются внутренние коды
    вроде CT_CON или MRI_CON — возвращается строка из справочника ОМС.
    """
    return normalize_modality_name(modality, *text_parts)
