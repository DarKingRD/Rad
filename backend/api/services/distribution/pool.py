"""
Формирование candidate pool для текущего запуска распределения.

Модуль содержит вспомогательные функции, которые:
- отбирают исследования, потенциально совместимые с врачами;
- оценивают грубую вместимость дня;
- строят shortlist для обычного режима;
- строят shortlist для multi-pass режима.

Логика вынесена отдельно, чтобы сервис не был перегружен правилами отбора.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .config import (
    CANDIDATE_POOL_FACTOR,
    CANDIDATE_POOL_MAX_SIZE,
    CANDIDATE_POOL_MIN_SIZE,
)
from .entities import DoctorData, StudyData


def candidate_priority_key(study: StudyData, now, target_date) -> Tuple:
    """
    Построить ключ сортировки исследования для shortlist.

    Ключ учитывает:
    - просроченность;
    - уровень приоритета;
    - дедлайн;
    - время создания.

    Используется для упорядочивания backlog перед выбором candidate pool.
    """
    overdue = study.deadline < now
    pr = {"cito": 0, "asap": 1, "normal": 2}.get(study.priority, 2)

    if overdue and study.priority == "cito":
        bucket = 0
    elif overdue and study.priority == "asap":
        bucket = 1
    elif overdue and study.priority == "normal":
        bucket = 2
    elif study.deadline.date() <= target_date:
        bucket = 3
    else:
        bucket = 4

    return (bucket, pr, study.deadline, study.created_at)


def filter_feasible_studies(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> List[StudyData]:
    """
    Построить ключ сортировки исследования для shortlist.

    Ключ учитывает:
    - просроченность;
    - уровень приоритета;
    - дедлайн;
    - время создания.

    Используется для упорядочивания backlog перед выбором candidate pool.
    """
    feasible: List[StudyData] = []
    prebooked = doc_prebooked_minutes or {}

    for study in studies:
        fits_somewhere = False
        for doctor in doctors:
            if not modality_ok(study.modality, doctor.modality):
                continue
            if study.up_value > doctor.max_up + 1e-9:
                continue
            if study.duration_minutes > remaining_work_minutes(
                doctor, prebooked.get(doctor.id, 0.0)) + 1e-9:
                continue
            fits_somewhere = True
            break

        if fits_somewhere:
            feasible.append(study)

    return feasible


def rough_daily_capacity_count(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> int:
    """
    Грубо оценить, сколько исследований система способна обработать за день.

    Оценка строится по каждому врачу отдельно и использует средние значения
    длительности и УП по совместимым исследованиям. Итог нужен не для точного
    решения, а для определения разумного размера candidate pool.
    """
    total_capacity = 0.0
    prebooked = doc_prebooked_minutes or {}

    for doctor in doctors:
        compatible = [s for s in studies if modality_ok(s.modality, doctor.modality)]
        if not compatible:
            continue

        available_minutes = remaining_work_minutes(doctor, prebooked.get(doctor.id, 0.0))
        if available_minutes <= 1e-9 or doctor.max_up <= 1e-9:
            continue

        avg_duration = sum(s.duration_minutes for s in compatible) / len(compatible)
        avg_up = sum(s.up_value for s in compatible) / len(compatible)

        by_minutes = available_minutes / max(avg_duration, 1e-9)
        by_up = doctor.max_up / max(avg_up, 1e-9)
        total_capacity += max(0.0, min(by_minutes, by_up))

    return max(1, int(round(total_capacity))) if studies and doctors else 0


def build_candidate_pool(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    now,
    target_date,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> List[StudyData]:
    """
    Построить shortlist исследований для обычного режима распределения.

    Алгоритм:
    1. отфильтровать feasible-исследования;
    2. отсортировать их по приоритетному ключу;
    3. оценить грубую вместимость дня;
    4. ограничить размер shortlist по конфигурационным параметрам.

    Возвращается список исследований, которые передаются в solver.
    """
    feasible = filter_feasible_studies(
        studies,
        doctors,
        modality_ok=modality_ok,
        remaining_work_minutes=remaining_work_minutes,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )

    ordered = sorted(feasible, key=lambda s: candidate_priority_key(s, now, target_date))
    rough_capacity = rough_daily_capacity_count(
        ordered,
        doctors,
        modality_ok=modality_ok,
        remaining_work_minutes=remaining_work_minutes,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )

    target_size = int(round(rough_capacity * CANDIDATE_POOL_FACTOR))
    target_size = max(target_size, CANDIDATE_POOL_MIN_SIZE if ordered else 0)
    target_size = min(target_size, CANDIDATE_POOL_MAX_SIZE if ordered else 0)
    target_size = min(target_size, len(ordered))

    selected = ordered[:target_size]

    n_cito = sum(1 for s in selected if s.priority == "cito")
    n_asap = sum(1 for s in selected if s.priority == "asap")
    n_normal = sum(1 for s in selected if s.priority == "normal")

    log(
        f"Candidate pool: feasible={len(feasible)} из {len(studies)}, "
        f"rough_capacity≈{rough_capacity}, target={target_size}, "
        f"CITO={n_cito}, ASAP={n_asap}, NORMAL={n_normal}"
    )
    return selected


def build_multipass_candidate_pool(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    priority: str,
    now,
    target_date,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> List[StudyData]:
    """
    Построить shortlist для очередного прохода multi-pass распределения.

    Для CITO и ASAP берётся весь feasible-набор текущей группы, чтобы не
    обрезать критически важные исследования. Для остальных приоритетов
    используется обычная логика candidate pool.
    """
    if priority not in {"cito", "asap"}:
        return build_candidate_pool(
            studies,
            doctors,
            now=now,
            target_date=target_date,
            modality_ok=modality_ok,
            remaining_work_minutes=remaining_work_minutes,
            log=log,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

    feasible = filter_feasible_studies(
        studies,
        doctors,
        modality_ok=modality_ok,
        remaining_work_minutes=remaining_work_minutes,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )
    feasible = sorted(feasible, key=lambda s: candidate_priority_key(s, now, target_date))

    log(
        f"Multi-pass pool [{priority.upper()}]: feasible={len(feasible)} "
        f"из {len(studies)} — берём весь feasible-набор"
    )
    return feasible
