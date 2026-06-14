"""
Exact-решатель задачи распределения на основе MILP.
"""
from __future__ import annotations

import os
import time
from datetime import timedelta
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional

from .config import (
    EXACT_MAX_OPTIONS,
    EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR,
    EXACT_OPTIONS_WORKERS,
    EXACT_PARALLEL_MIN_DOCTORS,
    EXACT_PRUNE_WORSE_THAN_UNASSIGNED,
    TIME_SLOT_MINUTES,
)
from .entities import DoctorData, ScheduleOption, StudyData
from .time_utils import add_work_minutes, execution_segments, occupied_slot_indices, slot_boundaries

_WORKER_CONTEXT = {}


def _solver_available(solver) -> bool:
    try:
        return bool(solver.available())
    except Exception:
        return True


def make_solver(
    *,
    pulp,
    time_limit: float,
    gap_rel: float,
    threads: int,
    msg: int,
):
    """Создать обычный CBC-решатель без дополнительных режимов."""
    threads = max(1, int(threads or 1))
    solver = pulp.PULP_CBC_CMD(
        timeLimit=time_limit,
        gapRel=gap_rel,
        threads=threads,
        msg=msg,
    )
    if not _solver_available(solver):
        raise RuntimeError(f"CBC executable не найден: {getattr(solver, 'path', None)}")
    return solver, "CBC", threads


def _build_solution_payload(
    *,
    chosen_option_ids: set[int],
    options: List[ScheduleOption],
    studies: List[StudyData],
    doctors: List[DoctorData],
    unassigned_meta_by_study: Dict[int, Dict],
    solver_obj: float,
    log: Callable[[str], None],
):
    chosen_study_indices = set()
    assignment: Dict[str, int] = {}
    details: Dict[str, Dict] = {}

    for option in options:
        if option.option_id not in chosen_option_ids:
            continue
        study = studies[option.study_idx]
        doctor = doctors[option.doctor_idx]
        chosen_study_indices.add(option.study_idx)
        assignment[study.research_number] = doctor.id
        details[study.research_number] = {
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "start_dt": option.start_dt,
            "finish_dt": option.finish_dt,
            **{key: float(value) for key, value in option.metrics.items()},
        }

    unassigned_meta = {
        studies[index].research_number: dict(unassigned_meta_by_study[index])
        for index in range(len(studies))
        if index not in chosen_study_indices
    }
    log(
        f"Exact solver: назначено {len(assignment)} / {len(studies)}, "
        f"неназначено {len(unassigned_meta)} / {len(studies)}"
    )
    return assignment, details, float(solver_obj), unassigned_meta


def _solve_with_pulp_mip(
    *,
    options: List[ScheduleOption],
    options_by_study: Dict[int, List[int]],
    options_by_doctor: Dict[int, List[int]],
    options_by_doctor_slot: Dict[tuple, List[int]],
    studies: List[StudyData],
    doctors: List[DoctorData],
    unassigned_meta_by_study: Dict[int, Dict],
    base_constant: float,
    reduced_cost_by_option: Dict[int, float],
    up_by_option: Dict[int, float],
    mip_time_limit: float,
    mip_gap_rel: float,
    mip_threads: int,
    objective_code: str,
    log: Callable[[str], None],
):
    import pulp

    t_build_model = time.perf_counter()
    problem = pulp.LpProblem(f"Exact_{objective_code}", pulp.LpMinimize)
    x = {option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary") for option in options}

    added_study_constraints = 0
    skipped_study_constraints = 0
    for study_idx, option_ids in options_by_study.items():
        if len(option_ids) > 1:
            problem += (pulp.lpSum(x[option_id] for option_id in option_ids) <= 1, f"StudyChoice_{study_idx}")
            added_study_constraints += 1
        else:
            skipped_study_constraints += 1

    added_slot_constraints = 0
    skipped_slot_constraints = 0
    for (doctor_idx, slot_idx), option_ids in options_by_doctor_slot.items():
        if len(option_ids) > 1:
            problem += (pulp.lpSum(x[option_id] for option_id in option_ids) <= 1, f"Cap_d{doctor_idx}_s{slot_idx}")
            added_slot_constraints += 1
        else:
            skipped_slot_constraints += 1

    added_up_constraints = 0
    skipped_up_constraints = 0
    for doctor_idx, doctor in enumerate(doctors):
        doctor_option_ids = options_by_doctor.get(doctor_idx, [])
        if not doctor_option_ids:
            skipped_up_constraints += 1
            continue

        # Если даже выбор всех опций врача не превышает его дневной лимит УП,
        # ограничение не сужает feasible set: бинарность переменных уже достаточна.
        max_possible_up = sum(up_by_option[option_id] for option_id in doctor_option_ids)
        if max_possible_up <= doctor.max_up + 1e-9:
            skipped_up_constraints += 1
        else:
            problem += (
                pulp.lpSum(up_by_option[option_id] * x[option_id] for option_id in doctor_option_ids)
                <= doctor.max_up,
                f"UP_{doctor_idx}",
            )
            added_up_constraints += 1

    problem += (
        base_constant + pulp.lpSum(reduced_cost_by_option[option_id] * x[option_id] for option_id in x),
        "Obj",
    )
    log(
        "CBC constraints: "
        f"study added={added_study_constraints}, skipped_redundant={skipped_study_constraints}; "
        f"slot added={added_slot_constraints}, skipped_redundant={skipped_slot_constraints}; "
        f"up added={added_up_constraints}, skipped_redundant={skipped_up_constraints}"
    )
    log(f"TIMING build_model_cbc: {time.perf_counter() - t_build_model:.2f}s")

    solver, executable_label, effective_threads = make_solver(
        pulp=pulp,
        time_limit=mip_time_limit,
        gap_rel=mip_gap_rel,
        threads=mip_threads,
        msg=1,
    )
    log(
        f"{executable_label} параметры: timeLimit={mip_time_limit}, "
        f"gapRel={mip_gap_rel}, threads={effective_threads}"
    )

    t_solve = time.perf_counter()
    problem.solve(solver)
    log(f"TIMING cbc_solve: {time.perf_counter() - t_solve:.2f}s")

    status = pulp.LpStatus[problem.status]
    solver_obj = float(pulp.value(problem.objective) or 0.0)
    log(f"{executable_label}: статус={status}, obj={solver_obj:.6f}")

    if status not in {"Optimal", "Integer Feasible"}:
        raise RuntimeError(f"{executable_label} не дал корректного решения: {status}")

    chosen_option_ids = {
        option_id
        for option_id, variable in x.items()
        if (pulp.value(variable) or 0.0) > 0.5
    }
    return _build_solution_payload(
        chosen_option_ids=chosen_option_ids,
        options=options,
        studies=studies,
        doctors=doctors,
        unassigned_meta_by_study=unassigned_meta_by_study,
        solver_obj=solver_obj,
        log=log,
    )


def _modality_ok(study_mods, doctor_mods) -> bool:
    if not doctor_mods:
        return False
    if not study_mods:
        return True
    return bool(study_mods & doctor_mods)


def _build_rows_for_doctor(
    *,
    doctor_idx: int,
    doctor: DoctorData,
    studies: List[StudyData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    prebooked_minutes: float,
) -> List[tuple]:
    """Построить все допустимые варианты стартов для одного врача."""
    boundaries = slot_boundaries(doctor, planning_now, prebooked_minutes)
    if not boundaries:
        return []

    slot_delta = timedelta(minutes=TIME_SLOT_MINUTES)
    slot_ends = [slot_start + slot_delta for slot_start in boundaries]

    studies_by_duration = defaultdict(list)
    for study_idx, study in enumerate(studies):
        if not _modality_ok(study.modality, doctor.modality):
            continue
        if study.up_value > doctor.max_up + 1e-9:
            continue
        studies_by_duration[float(study.duration_minutes)].append((study_idx, study))

    if not studies_by_duration:
        return []

    geometry_by_duration: Dict[float, list] = {}
    for duration_minutes in studies_by_duration:
        variants = []
        for start_dt in boundaries:
            finish_dt = add_work_minutes(doctor, start_dt, duration_minutes)
            if finish_dt > doctor.shift_end:
                break

            segments = execution_segments(doctor, start_dt, duration_minutes)
            occupied_slots = occupied_slot_indices(segments, boundaries, slot_ends)
            if occupied_slots:
                variants.append((start_dt, finish_dt, occupied_slots))
        geometry_by_duration[duration_minutes] = variants

    rows: List[tuple] = []
    for duration_minutes, indexed_studies in studies_by_duration.items():
        variants = geometry_by_duration.get(duration_minutes, [])
        if not variants:
            continue

        for study_idx, study in indexed_studies:
            ranked: List[tuple] = []
            for start_dt, finish_dt, occupied_slots in variants:
                metrics = objective.option_metrics(study, doctor, start_dt, finish_dt)
                tardiness_hours = float(
                    metrics.get(
                        "tardiness_hours",
                        max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0),
                    )
                )
                weighted_tardiness = float(
                    metrics.get(
                        "weighted_tardiness",
                        tardiness_hours * priority_weights.get(study.priority, 1.0),
                    )
                )
                objective_value = float(metrics.get("objective_value", weighted_tardiness))

                ranked.append(
                    (
                        objective_value,
                        finish_dt,
                        start_dt,
                        study_idx,
                        doctor_idx,
                        tardiness_hours,
                        weighted_tardiness,
                        occupied_slots,
                        metrics,
                    )
                )

            if EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR is None:
                rows.extend(ranked)
            else:
                ranked.sort(key=lambda item: (item[0], item[1], item[2]))
                rows.extend(ranked[:EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR])

    return rows


def _auto_options_workers(doctors_count: int) -> int:
    """Определить число процессов для генерации options."""
    if doctors_count < EXACT_PARALLEL_MIN_DOCTORS:
        return 1

    configured = int(EXACT_OPTIONS_WORKERS or 0)
    if configured > 0:
        return max(1, min(configured, doctors_count))

    cpu_count = os.cpu_count() or 1
    return max(1, min(cpu_count, doctors_count))


def _init_option_worker(studies, objective, priority_weights, planning_now):
    """Инициализировать общий контекст процесса для генерации options."""
    _WORKER_CONTEXT.clear()
    _WORKER_CONTEXT.update(
        {
            "studies": studies,
            "objective": objective,
            "priority_weights": priority_weights,
            "planning_now": planning_now,
        }
    )


def _build_rows_for_doctor_worker(payload):
    """Worker для ProcessPoolExecutor: генерирует options одного врача."""
    doctor_idx, doctor, prebooked_minutes = payload

    rows = _build_rows_for_doctor(
        doctor_idx=doctor_idx,
        doctor=doctor,
        studies=_WORKER_CONTEXT["studies"],
        objective=_WORKER_CONTEXT["objective"],
        priority_weights=_WORKER_CONTEXT["priority_weights"],
        planning_now=_WORKER_CONTEXT["planning_now"],
        prebooked_minutes=prebooked_minutes,
    )
    return doctor_idx, doctor.id, rows


def _collect_raw_option_rows(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    prebooked_map: Dict[int, float],
    log: Callable[[str], None],
) -> List[tuple]:
    """Собрать сырые rows для options: последовательно или параллельно по врачам."""
    workers = _auto_options_workers(len(doctors))

    def collect_sequential(reason: Optional[str] = None) -> List[tuple]:
        raw_rows: List[tuple] = []
        if reason:
            log(f"Параллельная генерация options недоступна: {reason}; fallback=sequential")
        log(f"Последовательная генерация options: doctors={len(doctors)}")
        for doctor_idx, doctor in enumerate(doctors):
            rows = _build_rows_for_doctor(
                doctor_idx=doctor_idx,
                doctor=doctor,
                studies=studies,
                objective=objective,
                priority_weights=priority_weights,
                planning_now=planning_now,
                prebooked_minutes=prebooked_map.get(doctor.id, 0.0),
            )
            raw_rows.extend(rows)
            log(f"  options doctor_idx={doctor_idx}, doctor_id={doctor.id}: {len(rows)}")
        return raw_rows

    if workers <= 1:
        return collect_sequential()

    payloads = [
        (doctor_idx, doctor, prebooked_map.get(doctor.id, 0.0))
        for doctor_idx, doctor in enumerate(doctors)
    ]

    log(f"Параллельная генерация options: workers={workers}, doctors={len(doctors)}")
    raw_rows_by_doctor: Dict[int, List[tuple]] = {}

    try:
        with ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_option_worker,
            initargs=(studies, objective, priority_weights, planning_now),
        ) as executor:
            future_map = {
                executor.submit(_build_rows_for_doctor_worker, payload): payload[0]
                for payload in payloads
            }
            for future in as_completed(future_map):
                doctor_idx, doctor_id, rows = future.result()
                raw_rows_by_doctor[doctor_idx] = rows
                log(f"  options doctor_idx={doctor_idx}, doctor_id={doctor_id}: {len(rows)}")
    except Exception as exc:
        return collect_sequential(str(exc))

    raw_rows: List[tuple] = []
    for doctor_idx in sorted(raw_rows_by_doctor):
        raw_rows.extend(raw_rows_by_doctor[doctor_idx])

    return raw_rows

def build_exact_options(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    unassigned_cost_by_study: Optional[Dict[int, float]] = None,
):
    """Построить бинарные опции MILP и индексы для ограничений."""
    options: List[ScheduleOption] = []
    options_by_study = {index: [] for index in range(len(studies))}
    options_by_doctor = {index: [] for index in range(len(doctors))}
    options_by_doctor_slot = defaultdict(list)

    prebooked_map = doc_prebooked_minutes or {}
    raw_rows = _collect_raw_option_rows(
        studies=studies,
        doctors=doctors,
        objective=objective,
        priority_weights=priority_weights,
        planning_now=planning_now,
        prebooked_map=prebooked_map,
        log=log,
    )

    if EXACT_PRUNE_WORSE_THAN_UNASSIGNED and unassigned_cost_by_study:
        before_prune = len(raw_rows)
        raw_rows = [
            row
            for row in raw_rows
            if float(row[0]) <= float(unassigned_cost_by_study.get(row[3], 0.0)) + 1e-9
        ]
        log(
            "Prune worse-than-unassigned options: "
            f"removed={before_prune - len(raw_rows)}, remained={len(raw_rows)}"
        )

    if EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR is None:
        log("Лимит вариантов на исследование/врача отключён")
    else:
        log(
            "Лимит вариантов на исследование/врача: "
            f"{EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR}"
        )

    if EXACT_MAX_OPTIONS is not None and len(raw_rows) > EXACT_MAX_OPTIONS:
        raw_rows.sort(key=lambda item: (item[0], item[1], item[3], item[4]))
        raw_rows = raw_rows[:EXACT_MAX_OPTIONS]
        log(f"Ограничение model size: оставлено {len(raw_rows)} лучших options")
    else:
        log(f"Глобальный лимит options не применялся: raw_rows={len(raw_rows)}")

    raw_rows.sort(key=lambda item: (item[4], item[3], item[2]))

    for option_id, row in enumerate(raw_rows):
        (
            objective_value,
            finish_dt,
            start_dt,
            study_idx,
            doctor_idx,
            tardiness_hours,
            weighted_tardiness,
            occupied_slots,
            metrics,
        ) = row

        option = ScheduleOption(
            option_id=option_id,
            study_idx=study_idx,
            doctor_idx=doctor_idx,
            start_dt=start_dt,
            finish_dt=finish_dt,
            tardiness_hours=tardiness_hours,
            weighted_tardiness=weighted_tardiness,
            occupied_slots=occupied_slots,
            metrics=metrics,
            objective_value=objective_value,
        )
        options.append(option)
        options_by_study[study_idx].append(option_id)
        options_by_doctor[doctor_idx].append(option_id)
        for slot_idx in occupied_slots:
            options_by_doctor_slot[(doctor_idx, slot_idx)].append(option_id)

    return options, options_by_study, options_by_doctor, dict(options_by_doctor_slot)


def build_fallback_result(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    solve_greedy_fn: Callable,
    planning_horizon_end_fn: Callable,
    objective,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """Построить fallback-результат через жадное распределение."""
    assignment, details = solve_greedy_fn(
        studies,
        doctors,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )
    horizon_end = planning_horizon_end_fn(doctors)
    unassigned_meta = {
        study.research_number: objective.unassigned_metrics(study, horizon_end)
        for study in studies
        if study.research_number not in assignment
    }
    solver_obj = (
        sum(float(item.get("objective_value", 0.0)) for item in details.values())
        + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
    )
    return assignment, details, float(solver_obj), unassigned_meta


def solve_exact_mip(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    objective_code: str,
    priority_weights: Dict[str, float],
    mip_time_limit: float,
    mip_gap_rel: float,
    mip_threads: int = 1,
    planning_now=None,
    solve_greedy_fn: Callable,
    planning_horizon_end_fn: Callable,
    log: Optional[Callable[[str], None]] = None,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """Решить задачу точным MILP через обычный CBC или откатиться на жадный fallback."""
    log = log or (lambda _msg: None)

    log(
        f"Exact solver: backend=cbc, studies={len(studies)}, "
        f"doctors={len(doctors)}, objective={objective_code}"
    )

    horizon_end = planning_horizon_end_fn(doctors)
    unassigned_meta_by_study = {
        index: objective.unassigned_metrics(study, horizon_end)
        for index, study in enumerate(studies)
    }
    unassigned_cost_by_study = {
        index: float(meta["objective_value"])
        for index, meta in unassigned_meta_by_study.items()
    }
    base_constant = float(sum(unassigned_cost_by_study.values()))

    t_build_options = time.perf_counter()
    options, options_by_study, options_by_doctor, options_by_doctor_slot = build_exact_options(
        studies=studies,
        doctors=doctors,
        objective=objective,
        priority_weights=priority_weights,
        planning_now=planning_now,
        log=log,
        doc_prebooked_minutes=doc_prebooked_minutes,
        unassigned_cost_by_study=unassigned_cost_by_study,
    )
    log(f"TIMING build_exact_options: {time.perf_counter() - t_build_options:.2f}s")
    log(f"  Кандидатных стартов: {len(options)}")
    if not options and studies:
        log("  Нет допустимых стартов → все исследования переходят в неназначенные")

    reduced_cost_by_option = {
        option.option_id: float(option.objective_value - unassigned_cost_by_study[option.study_idx])
        for option in options
    }
    up_by_option = {
        option.option_id: float(studies[option.study_idx].up_value)
        for option in options
    }

    try:
        return _solve_with_pulp_mip(
            options=options,
            options_by_study=options_by_study,
            options_by_doctor=options_by_doctor,
            options_by_doctor_slot=options_by_doctor_slot,
            studies=studies,
            doctors=doctors,
            unassigned_meta_by_study=unassigned_meta_by_study,
            base_constant=base_constant,
            reduced_cost_by_option=reduced_cost_by_option,
            up_by_option=up_by_option,
            mip_time_limit=mip_time_limit,
            mip_gap_rel=mip_gap_rel,
            mip_threads=mip_threads,
            objective_code=objective_code,
            log=log,
        )

    except Exception as exc:
        log(f"CBC ошибка: {exc} → жадный fallback")
        return build_fallback_result(
            studies=studies,
            doctors=doctors,
            solve_greedy_fn=solve_greedy_fn,
            planning_horizon_end_fn=planning_horizon_end_fn,
            objective=objective,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )
