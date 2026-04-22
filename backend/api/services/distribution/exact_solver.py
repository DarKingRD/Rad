"""
Exact-решатель задачи распределения на основе MILP.
"""
from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Dict, List, Optional

from .config import (
    EXACT_MAX_OPTIONS,
    EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR,
    EXACT_OPTION_BUILD_WORKERS,
    EXACT_PARALLEL_MIN_DOCTORS,
)
from .entities import DoctorData, ScheduleOption, StudyData
from .time_utils import add_work_minutes, execution_segments, occupied_slot_indices, slot_boundaries


def make_solver(*, pulp, time_limit: float, gap_rel: float, threads: int, msg: int):
    """Создать CBC-решатель без привязки к локальному пути."""
    return pulp.PULP_CBC_CMD(
        timeLimit=time_limit,
        gapRel=gap_rel,
        threads=max(1, int(threads or 1)),
        msg=msg,
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
            occupied_slots = occupied_slot_indices(segments, boundaries)
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

            ranked.sort(key=lambda item: (item[0], item[1], item[2]))
            rows.extend(ranked[:EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR])

    return rows


def build_exact_options(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """Построить бинарные опции MILP и индексы для ограничений."""
    options: List[ScheduleOption] = []
    options_by_study = {index: [] for index in range(len(studies))}
    options_by_doctor = {index: [] for index in range(len(doctors))}
    options_by_doctor_slot = defaultdict(list)

    prebooked_map = doc_prebooked_minutes or {}
    raw_rows: List[tuple] = []

    worker_count = min(EXACT_OPTION_BUILD_WORKERS, len(doctors))
    use_parallel = worker_count > 1 and len(doctors) >= EXACT_PARALLEL_MIN_DOCTORS

    if use_parallel:
        try:
            log(f"Параллельная генерация options: workers={worker_count}, doctors={len(doctors)}")
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                futures = [
                    executor.submit(
                        _build_rows_for_doctor,
                        doctor_idx=doctor_idx,
                        doctor=doctor,
                        studies=studies,
                        objective=objective,
                        priority_weights=priority_weights,
                        planning_now=planning_now,
                        prebooked_minutes=prebooked_map.get(doctor.id, 0.0),
                    )
                    for doctor_idx, doctor in enumerate(doctors)
                ]
                for future in futures:
                    raw_rows.extend(future.result())
        except Exception as exc:
            log(f"Параллельная генерация options недоступна ({exc}) → последовательный режим")
            raw_rows = []
            use_parallel = False

    if not use_parallel:
        log(f"Последовательная генерация options: doctors={len(doctors)}")
        for doctor_idx, doctor in enumerate(doctors):
            raw_rows.extend(
                _build_rows_for_doctor(
                    doctor_idx=doctor_idx,
                    doctor=doctor,
                    studies=studies,
                    objective=objective,
                    priority_weights=priority_weights,
                    planning_now=planning_now,
                    prebooked_minutes=prebooked_map.get(doctor.id, 0.0),
                )
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
    mip_threads: int = 4,
    planning_now=None,
    solve_greedy_fn: Callable,
    planning_horizon_end_fn: Callable,
    log: Optional[Callable[[str], None]] = None,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """Решить задачу точным MILP или откатиться на жадный fallback."""
    log = log or (lambda _msg: None)

    try:
        import pulp
    except ImportError:
        log("PuLP не установлен → используем жадный fallback")
        return build_fallback_result(
            studies=studies,
            doctors=doctors,
            solve_greedy_fn=solve_greedy_fn,
            planning_horizon_end_fn=planning_horizon_end_fn,
            objective=objective,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

    log(f"Exact MILP: studies={len(studies)}, doctors={len(doctors)}, objective={objective_code}")

    t_build_options = time.perf_counter()
    options, options_by_study, options_by_doctor, options_by_doctor_slot = build_exact_options(
        studies=studies,
        doctors=doctors,
        objective=objective,
        priority_weights=priority_weights,
        planning_now=planning_now,
        log=log,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )
    log(f"TIMING build_exact_options: {time.perf_counter() - t_build_options:.2f}s")
    log(f"  Кандидатных стартов: {len(options)}")
    if not options and studies:
        log("  Нет допустимых стартов → все исследования переходят в неназначенные")

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
    reduced_cost_by_option = {
        option.option_id: float(option.objective_value - unassigned_cost_by_study[option.study_idx])
        for option in options
    }
    up_by_option = {
        option.option_id: float(studies[option.study_idx].up_value)
        for option in options
    }

    try:
        t_build_model = time.perf_counter()
        problem = pulp.LpProblem(f"Exact_{objective_code}", pulp.LpMinimize)
        x = {option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary") for option in options}

        for study_idx, option_ids in options_by_study.items():
            if option_ids:
                problem += (pulp.lpSum(x[option_id] for option_id in option_ids) <= 1, f"StudyChoice_{study_idx}")

        for (doctor_idx, slot_idx), option_ids in options_by_doctor_slot.items():
            problem += (pulp.lpSum(x[option_id] for option_id in option_ids) <= 1, f"Cap_d{doctor_idx}_s{slot_idx}")

        for doctor_idx, doctor in enumerate(doctors):
            doctor_option_ids = options_by_doctor.get(doctor_idx, [])
            if doctor_option_ids:
                problem += (
                    pulp.lpSum(up_by_option[option_id] * x[option_id] for option_id in doctor_option_ids)
                    <= doctor.max_up,
                    f"UP_{doctor_idx}",
                )

        problem += (
            base_constant + pulp.lpSum(reduced_cost_by_option[option_id] * x[option_id] for option_id in x),
            "Obj",
        )
        log(f"TIMING build_model: {time.perf_counter() - t_build_model:.2f}s")

        solver = make_solver(
            pulp=pulp,
            time_limit=mip_time_limit,
            gap_rel=mip_gap_rel,
            threads=mip_threads,
            msg=1,
        )
        log(f"CBC параметры: timeLimit={mip_time_limit}, gapRel={mip_gap_rel}, threads={max(1, int(mip_threads or 1))}")

        t_cbc = time.perf_counter()
        problem.solve(solver)
        log(f"TIMING cbc_solve: {time.perf_counter() - t_cbc:.2f}s")

        status = pulp.LpStatus[problem.status]
        solver_obj = float(pulp.value(problem.objective) or 0.0)
        log(f"CBC: статус={status}, obj={solver_obj:.6f}")

        if status not in {"Optimal", "Integer Feasible"}:
            log("  Exact MILP не дал корректного решения → жадный fallback")
            return build_fallback_result(
                studies=studies,
                doctors=doctors,
                solve_greedy_fn=solve_greedy_fn,
                planning_horizon_end_fn=planning_horizon_end_fn,
                objective=objective,
                doc_prebooked_minutes=doc_prebooked_minutes,
            )

        chosen_study_indices = set()
        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}

        for option in options:
            if (pulp.value(x[option.option_id]) or 0.0) <= 0.5:
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
            f"Exact MILP: назначено {len(assignment)} / {len(studies)}, "
            f"неназначено {len(unassigned_meta)} / {len(studies)}"
        )
        return assignment, details, float(solver_obj), unassigned_meta

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
