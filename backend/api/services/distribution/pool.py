"""
Формирование candidate pool для текущего запуска распределения.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .config import (
    CANDIDATE_POOL_FACTOR,
    CANDIDATE_POOL_MAX_SIZE,
    CANDIDATE_POOL_MIN_SIZE,
    PRIORITY_ORDER,
)
from .entities import DoctorData, StudyData

_PRIORITY_RANK = {priority: rank for rank, priority in enumerate(PRIORITY_ORDER)}


def candidate_priority_key(study: StudyData, now, target_date) -> Tuple[int, int, object, object]:
    """Построить ключ сортировки исследования для shortlist."""
    overdue = study.deadline < now
    priority_rank = _PRIORITY_RANK.get(study.priority, len(_PRIORITY_RANK))

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

    return (bucket, priority_rank, study.deadline, study.created_at)


def filter_feasible_studies(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> List[StudyData]:
    """Оставить только исследования, которые помещаются хотя бы к одному врачу."""
    feasible: List[StudyData] = []
    prebooked = doc_prebooked_minutes or {}

    for study in studies:
        for doctor in doctors:
            if not modality_ok(study.modality, doctor.modality):
                continue
            if study.up_value > doctor.max_up + 1e-9:
                continue
            remaining_minutes = remaining_work_minutes(doctor, prebooked.get(doctor.id, 0.0))
            if study.duration_minutes > remaining_minutes + 1e-9:
                continue
            feasible.append(study)
            break

    return feasible


def rough_daily_capacity_count(
    studies: List[StudyData],
    doctors: List[DoctorData],
    *,
    modality_ok: Callable,
    remaining_work_minutes: Callable,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> int:
    """Грубо оценить, сколько исследований система способна обработать за день."""
    total_capacity = 0.0
    prebooked = doc_prebooked_minutes or {}

    for doctor in doctors:
        compatible = [study for study in studies if modality_ok(study.modality, doctor.modality)]
        if not compatible:
            continue

        available_minutes = remaining_work_minutes(doctor, prebooked.get(doctor.id, 0.0))
        if available_minutes <= 1e-9 or doctor.max_up <= 1e-9:
            continue

        avg_duration = sum(study.duration_minutes for study in compatible) / len(compatible)
        avg_up = sum(study.up_value for study in compatible) / len(compatible)
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
    """Построить shortlist исследований для обычного режима распределения."""
    feasible = filter_feasible_studies(
        studies,
        doctors,
        modality_ok=modality_ok,
        remaining_work_minutes=remaining_work_minutes,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )

    ordered = sorted(feasible, key=lambda study: candidate_priority_key(study, now, target_date))
    rough_capacity = rough_daily_capacity_count(
        ordered,
        doctors,
        modality_ok=modality_ok,
        remaining_work_minutes=remaining_work_minutes,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )

    target_size = int(round(rough_capacity * CANDIDATE_POOL_FACTOR))
    if ordered:
        target_size = max(target_size, CANDIDATE_POOL_MIN_SIZE)
        target_size = min(target_size, CANDIDATE_POOL_MAX_SIZE, len(ordered))
    else:
        target_size = 0

    selected = ordered[:target_size]

    counts = {priority: sum(1 for study in selected if study.priority == priority) for priority in PRIORITY_ORDER}
    log(
        f"Candidate pool: feasible={len(feasible)} из {len(studies)}, "
        f"rough_capacity≈{rough_capacity}, target={target_size}, "
        f"CITO={counts['cito']}, ASAP={counts['asap']}, NORMAL={counts['normal']}"
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
    """Построить shortlist для очередного прохода multi-pass."""
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
    feasible = sorted(feasible, key=lambda study: candidate_priority_key(study, now, target_date))

    log(
        f"Multi-pass pool [{priority.upper()}]: feasible={len(feasible)} "
        f"из {len(studies)} — берём весь feasible-набор"
    )
    return feasible
