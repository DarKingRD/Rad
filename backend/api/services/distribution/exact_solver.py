"""
Exact-решатель задачи распределения на основе MILP.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

from .entities import DoctorData, ScheduleOption, StudyData


def build_exact_options(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    priority_weights: Dict[str, float],
    modality_ok: Callable,
    slot_boundaries_fn: Callable,
    add_work_minutes_fn: Callable,
    execution_segments_fn: Callable,
    occupied_slot_indices_fn: Callable,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> Tuple[
    List[ScheduleOption],
    Dict[int, List[int]],
    Dict[int, List[int]],
    Dict[Tuple[int, int], List[int]],
]:
    """Построить все допустимые варианты назначения для exact MILP."""
    options: List[ScheduleOption] = []
    options_by_study: Dict[int, List[int]] = {index: [] for index in range(len(studies))}
    options_by_doctor: Dict[int, List[int]] = {index: [] for index in range(len(doctors))}
    options_by_doctor_slot: Dict[Tuple[int, int], List[int]] = defaultdict(list)

    option_id = 0
    for doctor_idx, doctor in enumerate(doctors):
        prebooked = (doc_prebooked_minutes or {}).get(doctor.id, 0.0)
        boundaries = slot_boundaries_fn(doctor, prebooked)
        if not boundaries:
            continue

        studies_by_duration: Dict[float, List[Tuple[int, StudyData]]] = defaultdict(list)
        for study_idx, study in enumerate(studies):
            if not modality_ok(study.modality, doctor.modality):
                continue
            if study.up_value > doctor.max_up + 1e-9:
                continue
            studies_by_duration[float(study.duration_minutes)].append((study_idx, study))

        if not studies_by_duration:
            continue

        geometry_by_duration: Dict[float, List[Tuple[datetime, datetime, List[int]]]] = {}
        for duration_minutes in studies_by_duration:
            variants: List[Tuple[datetime, datetime, List[int]]] = []
            for start_dt in boundaries:
                finish_dt = add_work_minutes_fn(doctor, start_dt, duration_minutes)
                if finish_dt > doctor.shift_end:
                    break

                segments = execution_segments_fn(doctor, start_dt, duration_minutes)
                occupied_slots = occupied_slot_indices_fn(doctor, segments, boundaries)
                if not occupied_slots:
                    continue
                variants.append((start_dt, finish_dt, occupied_slots))
            geometry_by_duration[duration_minutes] = variants

        for duration_minutes, indexed_studies in studies_by_duration.items():
            variants = geometry_by_duration.get(duration_minutes, [])
            if not variants:
                continue

            for study_idx, study in indexed_studies:
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
                    option_id += 1

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
    studies,
    doctors,
    objective,
    objective_code,
    priority_weights,
    mip_time_limit,
    mip_gap_rel,
    solve_greedy_fn,
    planning_horizon_end_fn,
    modality_ok,
    slot_boundaries_fn,
    add_work_minutes_fn,
    execution_segments_fn,
    occupied_slot_indices_fn,
    log,
    doc_prebooked_minutes=None,
):
    """Решить задачу точным MILP или откатиться на fallback."""
    try:
        import pulp
    except ImportError:
        log("PuLP не установлен → используем жадный fallback по candidate pool")
        return build_fallback_result(
            studies=studies,
            doctors=doctors,
            solve_greedy_fn=solve_greedy_fn,
            planning_horizon_end_fn=planning_horizon_end_fn,
            objective=objective,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

    log(
        f"Exact MILP: candidate_pool={len(studies)}, "
        f"doctors={len(doctors)}, objective={objective_code}"
    )

    options, options_by_study, options_by_doctor, options_by_doctor_slot = build_exact_options(
        studies=studies,
        doctors=doctors,
        objective=objective,
        priority_weights=priority_weights,
        modality_ok=modality_ok,
        slot_boundaries_fn=slot_boundaries_fn,
        add_work_minutes_fn=add_work_minutes_fn,
        execution_segments_fn=execution_segments_fn,
        occupied_slot_indices_fn=occupied_slot_indices_fn,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )

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
        problem = pulp.LpProblem(f"Exact_{objective_code}", pulp.LpMinimize)
        x = {
            option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary")
            for option in options
        }

        for study_idx, option_ids in options_by_study.items():
            if not option_ids:
                continue
            problem += (
                pulp.lpSum(x[option_id] for option_id in option_ids) <= 1,
                f"StudyChoice_{study_idx}",
            )

        for (doctor_idx, slot_idx), option_ids in options_by_doctor_slot.items():
            problem += (
                pulp.lpSum(x[option_id] for option_id in option_ids) <= 1,
                f"Cap_d{doctor_idx}_s{slot_idx}",
            )

        for doctor_idx, doctor in enumerate(doctors):
            doctor_option_ids = options_by_doctor.get(doctor_idx, [])
            if not doctor_option_ids:
                continue
            problem += (
                pulp.lpSum(up_by_option[option_id] * x[option_id] for option_id in doctor_option_ids)
                <= doctor.max_up,
                f"UP_{doctor_idx}",
            )

        problem += (
            base_constant + pulp.lpSum(reduced_cost_by_option[option_id] * x[option_id] for option_id in x),
            "Obj",
        )

        solver = pulp.PULP_CBC_CMD(timeLimit=mip_time_limit, msg=0, gapRel=mip_gap_rel)
        problem.solve(solver)

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

        chosen = [option for option in options if (pulp.value(x[option.option_id]) or 0.0) > 0.5]
        assignment = {}
        details = {}
        chosen_study_indices = set()

        for option in chosen:
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
