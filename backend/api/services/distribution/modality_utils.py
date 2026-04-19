"""
Вспомогательные функции для нормализации и разбора модальностей.
"""
from __future__ import annotations

import re
from typing import Iterable, Set

from .config import CONTRAST_KEYWORDS, MODALITY_ALIASES

_SPLIT_RE = re.compile(r"[/,;|]+")


def normalize_modality(value: str) -> str:
    """Нормализовать строковое обозначение модальности."""
    if not value:
        return "OTHER"
    normalized = str(value).strip().upper()
    return MODALITY_ALIASES.get(normalized, normalized)


def parse_modalities(data) -> Set[str]:
    """Преобразовать исходное поле модальностей в множество канонических кодов."""
    if not data:
        return set()

    if isinstance(data, (list, tuple, set, frozenset)):
        raw_items: Iterable[object] = data
    else:
        raw_items = [item for item in _SPLIT_RE.split(str(data)) if item]

    return {
        normalize_modality(str(item))
        for item in raw_items
        if item is not None and str(item).strip()
    }


def is_contrast_study(*parts: object) -> bool:
    """Проверить, содержит ли текст исследования признак контрастирования."""
    haystack = " ".join(str(part or "") for part in parts).lower()
    return any(keyword in haystack for keyword in CONTRAST_KEYWORDS)


def workload_modality(modality: str, *text_parts: object) -> str:
    """Вернуть код модальности для расчёта длительности и УП.

    Для совместимости врача и исследования по-прежнему используется базовая
    модальность, а для workload-метрик CT/MRI с контрастом разводятся отдельно.
    """
    base = normalize_modality(modality)
    if base == "CT" and is_contrast_study(modality, *text_parts):
        return "CT_CON"
    if base == "MRI" and is_contrast_study(modality, *text_parts):
        return "MRI_CON"
    return base
