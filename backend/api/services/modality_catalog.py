"""
Единый справочник модальностей, длительностей и УП.

Модальности приведены к наименованиям из положения об оплате ОМС.
Этот модуль должен быть единственным источником правды для:
- импорта данных;
- распределения исследований;
- прогнозирования смен;
- валидации справочника врачей.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, List

OTHER_MODALITY = "OTHER"

FLUOROGRAPHY = "Флюорографическое исследование"
MAMMOGRAPHY_AI = "Маммографическое исследование совместно с искусственным интеллектом"
XRAY = "Рентгенгеновское исследование"
CT = "Компьютерная томограмма"
CT_CONTRAST = "Компьютерная томограмма с контрастом"
MRI = "Магнитно-резонансная томограмма"
MRI_CONTRAST = "Магнитно-резонансная томограмма с контрастом"
ABPM = "Суточное мониторирование артериального давления"
ECG = "Электрокардиография"
HOLTER_ECG = "Холтеровское мониторирование электрокардиографии"
EEG = "Электроэнцефалографическое исследование"

SUPPORTED_MODALITIES: List[str] = [
    FLUOROGRAPHY,
    MAMMOGRAPHY_AI,
    XRAY,
    CT,
    CT_CONTRAST,
    MRI,
    MRI_CONTRAST,
    ABPM,
    ECG,
    HOLTER_ECG,
    EEG,
]

DISPLAY_MODALITIES: List[str] = list(SUPPORTED_MODALITIES)

MODALITY_ORDER = {
    FLUOROGRAPHY: 1,
    MAMMOGRAPHY_AI: 2,
    XRAY: 3,
    CT: 4,
    CT_CONTRAST: 5,
    MRI: 6,
    MRI_CONTRAST: 7,
    ABPM: 8,
    ECG: 9,
    HOLTER_ECG: 10,
    EEG: 11,
    OTHER_MODALITY: 999,
}

MODALITY_DURATION_MINUTES = {
    FLUOROGRAPHY: 4.0,
    MAMMOGRAPHY_AI: 6.0,
    XRAY: 5.0,
    CT: 15.0,
    CT_CONTRAST: 25.0,
    MRI: 20.0,
    MRI_CONTRAST: 30.0,
    ABPM: 15.0,
    ECG: 4.0,
    HOLTER_ECG: 25.0,
    EEG: 20.0,
}

MODALITY_UP_VALUES = {
    FLUOROGRAPHY: Decimal("0.067"),
    MAMMOGRAPHY_AI: Decimal("0.100"),
    XRAY: Decimal("0.083"),
    CT: Decimal("0.250"),
    CT_CONTRAST: Decimal("0.417"),
    MRI: Decimal("0.333"),
    MRI_CONTRAST: Decimal("0.500"),
    ABPM: Decimal("0.250"),
    ECG: Decimal("0.067"),
    HOLTER_ECG: Decimal("0.417"),
    EEG: Decimal("0.333"),
}

DOCTOR_DAILY_UP_DEFAULT = 8
DOCTOR_MONTHLY_UP_DEFAULT = 50

CONTRAST_KEYWORDS = (
    "контраст",
    "контрастом",
    "контрастирование",
    "contrast",
    "bolus",
    "болюс",
)

_DIRECT_ALIASES = {
    FLUOROGRAPHY.casefold(): FLUOROGRAPHY,
    "флюорографическое исследование".casefold(): FLUOROGRAPHY,
    "флюорография".casefold(): FLUOROGRAPHY,
    "флг".casefold(): FLUOROGRAPHY,
    "flg": FLUOROGRAPHY,
    "fluoro": FLUOROGRAPHY,
    "fluorography": FLUOROGRAPHY,

    MAMMOGRAPHY_AI.casefold(): MAMMOGRAPHY_AI,
    "маммографическое исследование совместно с искусственным интеллектом".casefold(): MAMMOGRAPHY_AI,
    "маммография".casefold(): MAMMOGRAPHY_AI,
    "маммо".casefold(): MAMMOGRAPHY_AI,
    "mmg": MAMMOGRAPHY_AI,
    "mammo": MAMMOGRAPHY_AI,
    "mammo": MAMMOGRAPHY_AI,

    XRAY.casefold(): XRAY,
    "рентгеновское исследование".casefold(): XRAY,
    "рентгенгеновское исследование".casefold(): XRAY,
    "рентгенография".casefold(): XRAY,
    "рентген".casefold(): XRAY,
    "рентгенологическое исследование".casefold(): XRAY,
    "xray": XRAY,
    "x-ray": XRAY,
    "xr": XRAY,
    "rentgen": XRAY,

    CT.casefold(): CT,
    "компьютерная томограмма".casefold(): CT,
    "компьютерная томография".casefold(): CT,
    "кт".casefold(): CT,
    "kt": CT,
    "ct": CT,

    CT_CONTRAST.casefold(): CT_CONTRAST,
    "компьютерная томограмма с контрастом".casefold(): CT_CONTRAST,
    "компьютерная томография с контрастом".casefold(): CT_CONTRAST,
    "кт с контрастом".casefold(): CT_CONTRAST,
    "ct_con": CT_CONTRAST,
    "ct contrast": CT_CONTRAST,

    MRI.casefold(): MRI,
    "магнитно-резонансная томограмма".casefold(): MRI,
    "магнитно-резонансная томография".casefold(): MRI,
    "мрт".casefold(): MRI,
    "mrt": MRI,
    "mri": MRI,

    MRI_CONTRAST.casefold(): MRI_CONTRAST,
    "магнитно-резонансная томограмма с контрастом".casefold(): MRI_CONTRAST,
    "магнитно-резонансная томография с контрастом".casefold(): MRI_CONTRAST,
    "мрт с контрастом".casefold(): MRI_CONTRAST,
    "mri_con": MRI_CONTRAST,
    "mri contrast": MRI_CONTRAST,

    ABPM.casefold(): ABPM,
    "суточное мониторирование артериального давления".casefold(): ABPM,
    "смад".casefold(): ABPM,
    "abpm": ABPM,

    ECG.casefold(): ECG,
    "электрокардиография".casefold(): ECG,
    "экг".casefold(): ECG,
    "ecg": ECG,

    HOLTER_ECG.casefold(): HOLTER_ECG,
    "холтеровское мониторирование электрокардиографии".casefold(): HOLTER_ECG,
    "холтеровское мониторирование".casefold(): HOLTER_ECG,
    "холтер".casefold(): HOLTER_ECG,
    "holter": HOLTER_ECG,

    EEG.casefold(): EEG,
    "электроэнцефалографическое исследование".casefold(): EEG,
    "электроэнцефалография".casefold(): EEG,
    "ээг".casefold(): EEG,
    "eeg": EEG,

    OTHER_MODALITY.casefold(): OTHER_MODALITY,
    "other": OTHER_MODALITY,
    "прочее".casefold(): OTHER_MODALITY,
}

def _normalize_key(value: object) -> str:
    return str(value or "").strip().replace("Ё", "Е").replace("ё", "е").casefold()

def has_contrast(*parts: object) -> bool:
    haystack = " ".join(str(part or "") for part in parts).casefold()
    return any(keyword in haystack for keyword in CONTRAST_KEYWORDS)

def infer_modality_from_text(*parts: object) -> str:
    text = " ".join(str(part or "") for part in parts).replace("Ё", "Е").replace("ё", "е").casefold()
    if not text:
        return OTHER_MODALITY

    if "флюор" in text or "флг" in text:
        return FLUOROGRAPHY
    if "маммо" in text:
        return MAMMOGRAPHY_AI
    if "рентген" in text:
        return XRAY
    if "компьютерн" in text and "томограф" in text:
        return CT_CONTRAST if has_contrast(text) else CT
    if ("магнитно-резонанс" in text and "томограф" in text) or "мрт" in text:
        return MRI_CONTRAST if has_contrast(text) else MRI
    if ("суточ" in text and "давлен" in text) or "смад" in text or "abpm" in text:
        return ABPM
    if "холтер" in text:
        return HOLTER_ECG
    if "электрокардиограф" in text or " экг" in f" {text}" or text == "экг":
        return ECG
    if "электроэнцефал" in text or "ээг" in text:
        return EEG
    return OTHER_MODALITY

def normalize_modality_name(value: object, *context: object) -> str:
    key = _normalize_key(value)
    if key in _DIRECT_ALIASES:
        canonical = _DIRECT_ALIASES[key]
        # даже если пришёл базовый CT/MRI, по контексту можно развести исследования с контрастом
        if canonical == CT and has_contrast(value, *context):
            return CT_CONTRAST
        if canonical == MRI and has_contrast(value, *context):
            return MRI_CONTRAST
        return canonical

    inferred = infer_modality_from_text(value, *context)
    if inferred != OTHER_MODALITY:
        return inferred

    for item in context:
        inferred = infer_modality_from_text(item)
        if inferred != OTHER_MODALITY:
            return inferred

    return OTHER_MODALITY

def normalize_modalities(values: Iterable[object]) -> List[str]:
    normalized = []
    seen = set()
    for value in values:
        modality = normalize_modality_name(value)
        if modality == OTHER_MODALITY:
            continue
        if modality not in seen:
            seen.add(modality)
            normalized.append(modality)
    return sort_modalities(normalized)

def sort_modalities(values: Iterable[str]) -> List[str]:
    unique = []
    seen = set()
    for value in values:
        normalized = normalize_modality_name(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return sorted(unique, key=lambda item: (MODALITY_ORDER.get(item, 1000), item))

def is_supported_modality(value: object) -> bool:
    return normalize_modality_name(value) in SUPPORTED_MODALITIES

def get_modality_up_value(value: object, *context: object) -> Decimal:
    modality = normalize_modality_name(value, *context)
    return MODALITY_UP_VALUES.get(modality, Decimal("0.000"))

def get_modality_duration_minutes(value: object, *context: object) -> float:
    modality = normalize_modality_name(value, *context)
    return float(MODALITY_DURATION_MINUTES.get(modality, 15.0))
