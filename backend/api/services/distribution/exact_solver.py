"""
Exact-решатель задачи распределения на основе MILP.

Модуль отвечает за:
- построение допустимых вариантов назначения;
- формирование fallback-результата при недоступности exact-решателя;
- решение MILP-задачи с ограничениями по слотам и УП.

Сервисный слой использует этот модуль как вычислительный backend,
не вникая в детали построения модели.
"""
from __future__ import annotations

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
    Dict[int, List[datetime]],
]:
    """
    Построить все допустимые варианты назначения исследований на врачей.

    Для каждого исследования и врача перебираются допустимые стартовые слоты.
    Для каждого варианта рассчитываются:
    - время начала и окончания;
    - занятые слоты;
    - tardiness;
    - weighted tardiness;
    - objective value.

    Возвращаются:
    - список опций;
    - индексы опций по исследованию;
    - индексы опций по врачу;
    - список временных слотов по каждому врачу.
    """
    options: List[ScheduleOption] = []
    options_by_study: Dict[int, List[int]] = {i: [] for i in range(len(studies))}
    options_by_doctor: Dict[int, List[int]] = {j: [] for j in range(len(doctors))}
    slot_boundaries_by_doctor: Dict[int, List[datetime]] = {}

    option_id = 0

    for j, doctor in enumerate(doctors):
        prebooked = (doc_prebooked_minutes or {}).get(doctor.id, 0.0)
        slot_boundaries = slot_boundaries_fn(doctor, prebooked)
        slot_boundaries_by_doctor[j] = slot_boundaries

        if not slot_boundaries:
            continue

        for i, study in enumerate(studies):
            if not modality_ok(study.modality, doctor.modality):
                continue
            if study.up_value > doctor.max_up + 1e-9:
                continue

            for start_dt in slot_boundaries:
                finish_dt = add_work_minutes_fn(doctor, start_dt, study.duration_minutes)
                if finish_dt > doctor.shift_end:
                    continue

                segments = execution_segments_fn(doctor, start_dt, study.duration_minutes)
                occupied_slots = occupied_slot_indices_fn(doctor, segments, slot_boundaries)
                if not occupied_slots:
                    continue

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
                    study_idx=i,
                    doctor_idx=j,
                    start_dt=start_dt,
                    finish_dt=finish_dt,
                    tardiness_hours=tardiness_hours,
                    weighted_tardiness=weighted_tardiness,
                    occupied_slots=occupied_slots,
                    metrics=metrics,
                    objective_value=objective_value,
                )
                options.append(option)
                options_by_study[i].append(option_id)
                options_by_doctor[j].append(option_id)
                option_id += 1

    return options, options_by_study, options_by_doctor, slot_boundaries_by_doctor


def build_fallback_result(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    solve_greedy_fn: Callable,
    planning_horizon_end_fn: Callable,
    objective,
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """
    Построить результат fallback-режима через жадное распределение.

    Используется, если exact MILP недоступен или не смог вернуть
    корректное решение. Помимо назначений, функция рассчитывает
    штрафы для неназначенных исследований и итоговое значение objective.
    """
    assignment, details = solve_greedy_fn(
        studies,
        doctors,
        doc_prebooked_minutes=doc_prebooked_minutes,
    )
    planning_horizon_end = planning_horizon_end_fn(doctors)
    unassigned_meta = {
        s.research_number: objective.unassigned_metrics(s, planning_horizon_end)
        for s in studies
        if s.research_number not in assignment
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
    mip_time_limit: int,
    mip_gap_rel: float,
    solve_greedy_fn: Callable,
    planning_horizon_end_fn: Callable,
    modality_ok: Callable,
    slot_boundaries_fn: Callable,
    add_work_minutes_fn: Callable,
    execution_segments_fn: Callable,
    occupied_slot_indices_fn: Callable,
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
):
    """
    Решить задачу распределения в exact-постановке с помощью MILP.

    Модель выбирает для каждого исследования ровно одно из двух:
    - один допустимый вариант назначения;
    - статус неназначенного исследования.

    В модели учитываются:
    - несовместимость слотов у одного врача;
    - ограничение по УП врача;
    - objective-штрафы для назначенных и неназначенных исследований.

    При невозможности корректного решения возвращается fallback-результат.
    """
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
        f"Exact MILP: candidate_pool={
            len(studies)}, doctors={len(doctors)}, objective={objective_code}"
    )

    options, options_by_study, _, slot_boundaries_by_doctor = build_exact_options(
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

    options_by_id = {option.option_id: option for option in options}
    planning_horizon_end = planning_horizon_end_fn(doctors)
    unassigned_meta_by_study = {
        i: objective.unassigned_metrics(study, planning_horizon_end)
        for i, study in enumerate(studies)
    }

    def _add_common_constraints(prob, x_vars, y_vars):
        for study_idx, option_ids in options_by_study.items():
            if option_ids:
                prob += (
                    pulp.lpSum(x_vars[oid] for oid in option_ids) + y_vars[study_idx] == 1,
                    f"StudyChoice_{study_idx}",
                )
            else:
                prob += y_vars[study_idx] == 1, f"StudyForcedUnassigned_{study_idx}"

        for doctor_idx, slot_boundaries in slot_boundaries_by_doctor.items():
            for slot_idx, _ in enumerate(slot_boundaries):
                occupying = [
                    x_vars[option.option_id]
                    for option in options
                    if option.doctor_idx == doctor_idx and slot_idx in option.occupied_slots
                ]
                if occupying:
                    prob += (
                        pulp.lpSum(occupying) <= 1,
                        f"Cap_d{doctor_idx}_s{slot_idx}",
                    )

        for doctor_idx, doctor in enumerate(doctors):
            up_terms = [
                studies[options_by_id[oid].study_idx].up_value * x_vars[oid]
                for oid in x_vars
                if options_by_id[oid].doctor_idx == doctor_idx
            ]
            if up_terms:
                prob += pulp.lpSum(up_terms) <= doctor.max_up, f"UP_{doctor_idx}"

    try:
        prob = pulp.LpProblem(f"Exact_{objective_code}", pulp.LpMinimize)

        x = {
            option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary")
            for option in options
        }
        y = {
            study_idx: pulp.LpVariable(f"y_{study_idx}", cat="Binary")
            for study_idx in range(len(studies))
        }

        _add_common_constraints(prob, x, y)

        prob += (
            pulp.lpSum(option.objective_value * x[option.option_id] for option in options)
            + pulp.lpSum(
                float(unassigned_meta_by_study[i]["objective_value"]) * y[i]
                for i in y
            ),
            "Obj",
        )

        solver = pulp.PULP_CBC_CMD(
            timeLimit=mip_time_limit,
            msg=0,
            gapRel=mip_gap_rel,
        )
        prob.solve(solver)

        status = pulp.LpStatus[prob.status]
        solver_obj = float(pulp.value(prob.objective) or 0.0)
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

        chosen = [
            option for option in options if (pulp.value(x[option.option_id]) or 0) > 0.5
        ]
        unassigned_indices = [i for i in y if (pulp.value(y[i]) or 0) > 0.5]

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}

        for option in chosen:
            study = studies[option.study_idx]
            doctor = doctors[option.doctor_idx]
            assignment[study.research_number] = doctor.id
            details[study.research_number] = {
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "start_dt": option.start_dt,
                "finish_dt": option.finish_dt,
                **{k: float(v) for k, v in option.metrics.items()},
            }

        unassigned_meta = {
            studies[i].research_number: dict(unassigned_meta_by_study[i])
            for i in unassigned_indices
        }

        log(
            f"Exact MILP: назначено {len(assignment)} / {len(studies)}, "
            f"неназначено {len(unassigned_meta)} / {len(studies)}"
        )
        return assignment, details, float(solver_obj), unassigned_meta

    except Exception as e:
        log(f"CBC ошибка: {e} → жадный fallback")
        return build_fallback_result(
            studies=studies,
            doctors=doctors,
            solve_greedy_fn=solve_greedy_fn,
            planning_horizon_end_fn=planning_horizon_end_fn,
            objective=objective,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )
