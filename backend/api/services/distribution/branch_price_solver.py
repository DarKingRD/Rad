"""
Exact branch-and-price solver for the offline distribution task.

The mathematical model stays equivalent to the compact CBC formulation:
- each study can be assigned at most once;
- each doctor's occupied slots cannot overlap;
- each doctor's total UP cannot exceed max_up;
- the objective is unchanged.

Instead of materializing every study-doctor-start variable in one giant MILP,
this module works with full-doctor schedule patterns:
- columns are feasible schedules for one doctor class;
- the master problem picks up to `count(class)` patterns per class;
- pricing searches for new improving patterns in parallel across classes;
- branching is done on generated pattern variables.
"""
from __future__ import annotations

import heapq
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from .config import EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR
from .entities import DoctorData, ScheduleOption, StudyData
from .time_utils import add_work_minutes, execution_segments, occupied_slot_indices, slot_boundaries

EPS = 1e-7


@dataclass(frozen=True)
class DoctorClass:
    class_id: int
    doctors: Tuple[DoctorData, ...]
    prebooked_minutes: float
    signature: tuple

    @property
    def representative(self) -> DoctorData:
        return self.doctors[0]

    @property
    def count(self) -> int:
        return len(self.doctors)


@dataclass
class ClassOptionPool:
    doctor_class: DoctorClass
    options: List[ScheduleOption]
    option_ids_by_study: Dict[int, List[int]]
    option_ids_by_slot: Dict[int, List[int]]
    reduced_cost_by_option: Dict[int, float]
    up_by_option: Dict[int, float]
    best_option_id_by_study: Dict[int, int]


@dataclass(frozen=True)
class PatternColumn:
    column_id: int
    class_id: int
    option_ids: Tuple[int, ...]
    study_indices: Tuple[int, ...]
    cost: float


@dataclass
class MasterSolveResult:
    status: str
    objective_value: float
    variable_values: Dict[int, float]
    study_duals: Dict[int, float]
    class_duals: Dict[int, float]


@dataclass
class PricingResult:
    class_id: int
    profitable_option_count: int
    selected_option_ids: Tuple[int, ...]
    profit_value: float
    reduced_cost: float


@dataclass(order=True)
class BranchPriceNode:
    priority: float
    node_id: int
    depth: int = field(compare=False)
    fixed_zero: frozenset[int] = field(compare=False, default_factory=frozenset)
    fixed_one: frozenset[int] = field(compare=False, default_factory=frozenset)


class PatternRepository:
    def __init__(self) -> None:
        self.columns: Dict[int, PatternColumn] = {}
        self.columns_by_study: Dict[int, List[int]] = defaultdict(list)
        self.columns_by_class: Dict[int, List[int]] = defaultdict(list)
        self.signature_to_column_id: Dict[tuple, int] = {}
        self._next_id = 0

    def add_column(
        self,
        *,
        class_id: int,
        option_ids: Iterable[int],
        option_pool: ClassOptionPool,
    ) -> Optional[PatternColumn]:
        normalized_ids = tuple(sorted(int(option_id) for option_id in option_ids))
        if not normalized_ids:
            return None

        signature = (class_id, normalized_ids)
        existing_id = self.signature_to_column_id.get(signature)
        if existing_id is not None:
            return None

        study_indices = tuple(
            sorted({option_pool.options[option_id].study_idx for option_id in normalized_ids})
        )
        cost = float(sum(option_pool.reduced_cost_by_option[option_id] for option_id in normalized_ids))

        column = PatternColumn(
            column_id=self._next_id,
            class_id=class_id,
            option_ids=normalized_ids,
            study_indices=study_indices,
            cost=cost,
        )
        self._next_id += 1

        self.columns[column.column_id] = column
        self.signature_to_column_id[signature] = column.column_id
        self.columns_by_class[class_id].append(column.column_id)
        for study_idx in study_indices:
            self.columns_by_study[study_idx].append(column.column_id)
        return column


def _round_float(value: float) -> float:
    return round(float(value), 6)


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
            if EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR is None:
                rows.extend(ranked)
            else:
                rows.extend(ranked[:EXACT_MAX_VARIANTS_PER_STUDY_DOCTOR])

    return rows


def _doctor_class_signature(
    doctor: DoctorData,
    *,
    prebooked_minutes: float,
) -> tuple:
    return (
        tuple(sorted(doctor.modality)),
        _round_float(doctor.max_up),
        doctor.shift_start,
        doctor.shift_end,
        doctor.break_start,
        doctor.break_end,
        _round_float(prebooked_minutes),
    )


def build_doctor_classes(
    *,
    doctors: List[DoctorData],
    doc_prebooked_minutes: Optional[Dict[int, float]],
    log: Callable[[str], None],
) -> List[DoctorClass]:
    grouped: Dict[tuple, List[DoctorData]] = defaultdict(list)
    prebooked_map = doc_prebooked_minutes or {}

    for doctor in doctors:
        prebooked = float(prebooked_map.get(doctor.id, 0.0))
        signature = _doctor_class_signature(doctor, prebooked_minutes=prebooked)
        grouped[signature].append(doctor)

    doctor_classes: List[DoctorClass] = []
    for class_id, (signature, grouped_doctors) in enumerate(grouped.items()):
        prebooked_minutes = float(signature[-1])
        doctor_class = DoctorClass(
            class_id=class_id,
            doctors=tuple(grouped_doctors),
            prebooked_minutes=prebooked_minutes,
            signature=signature,
        )
        doctor_classes.append(doctor_class)
        doctor_ids = [doctor.id for doctor in grouped_doctors]
        log(
            "BranchPrice class "
            f"{class_id}: doctors={len(grouped_doctors)}, ids={doctor_ids}, "
            f"rep={doctor_class.representative.id}, prebooked={prebooked_minutes}"
        )

    log(
        f"BranchPrice: grouped {len(doctors)} doctors into "
        f"{len(doctor_classes)} equivalence classes"
    )
    return doctor_classes


def build_class_option_pool(
    *,
    doctor_class: DoctorClass,
    studies: List[StudyData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    unassigned_cost_by_study: Dict[int, float],
    log: Callable[[str], None],
) -> ClassOptionPool:
    raw_rows = _build_rows_for_doctor(
        doctor_idx=doctor_class.class_id,
        doctor=doctor_class.representative,
        studies=studies,
        objective=objective,
        priority_weights=priority_weights,
        planning_now=planning_now,
        prebooked_minutes=doctor_class.prebooked_minutes,
    )
    raw_rows.sort(key=lambda item: (item[3], item[2], item[1]))

    options: List[ScheduleOption] = []
    option_ids_by_study: Dict[int, List[int]] = defaultdict(list)
    option_ids_by_slot: Dict[int, List[int]] = defaultdict(list)
    reduced_cost_by_option: Dict[int, float] = {}
    up_by_option: Dict[int, float] = {}
    best_option_id_by_study: Dict[int, int] = {}
    filtered_out_non_improving = 0

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

        reduced_cost = float(objective_value - unassigned_cost_by_study[study_idx])
        if reduced_cost >= -EPS:
            filtered_out_non_improving += 1
            continue

        option = ScheduleOption(
            option_id=len(options),
            study_idx=study_idx,
            doctor_idx=doctor_idx,
            start_dt=start_dt,
            finish_dt=finish_dt,
            tardiness_hours=tardiness_hours,
            weighted_tardiness=weighted_tardiness,
            occupied_slots=occupied_slots,
            metrics=metrics,
            objective_value=float(objective_value),
        )
        options.append(option)
        actual_option_id = option.option_id
        option_ids_by_study[study_idx].append(actual_option_id)
        for slot_idx in occupied_slots:
            option_ids_by_slot[slot_idx].append(actual_option_id)
        reduced_cost_by_option[actual_option_id] = reduced_cost
        up_by_option[actual_option_id] = float(studies[study_idx].up_value)
        current_best_id = best_option_id_by_study.get(study_idx)
        if current_best_id is None or reduced_cost < reduced_cost_by_option[current_best_id]:
            best_option_id_by_study[study_idx] = actual_option_id

    log(
        f"BranchPrice class {doctor_class.class_id}: representative options={len(options)} "
        f"(filtered={filtered_out_non_improving}) for {doctor_class.count} doctors"
    )
    return ClassOptionPool(
        doctor_class=doctor_class,
        options=options,
        option_ids_by_study=dict(option_ids_by_study),
        option_ids_by_slot=dict(option_ids_by_slot),
        reduced_cost_by_option=reduced_cost_by_option,
        up_by_option=up_by_option,
        best_option_id_by_study=best_option_id_by_study,
    )


def _build_master_problem(
    *,
    pattern_repo: PatternRepository,
    doctor_classes: List[DoctorClass],
    study_count: int,
    base_constant: float,
    fixed_zero: frozenset[int],
    fixed_one: frozenset[int],
    as_integer: bool,
):
    import pulp

    problem = pulp.LpProblem(
        "BranchPriceMaster",
        pulp.LpMinimize,
    )
    y = {}

    for column_id, column in pattern_repo.columns.items():
        if column_id in fixed_zero and column_id in fixed_one:
            continue

        if column_id in fixed_one:
            low_bound = 1.0
            up_bound = 1.0
        elif column_id in fixed_zero:
            low_bound = 0.0
            up_bound = 0.0
        else:
            low_bound = 0.0
            up_bound = 1.0

        y[column_id] = pulp.LpVariable(
            f"col_{column_id}",
            lowBound=low_bound,
            upBound=up_bound,
            cat="Binary" if as_integer else "Continuous",
        )

    dummy = pulp.LpVariable("dummy_zero", lowBound=0.0, upBound=0.0)
    problem += (
        base_constant
        + pulp.lpSum(pattern_repo.columns[column_id].cost * variable for column_id, variable in y.items())
        + 0.0 * dummy,
        "Obj",
    )

    for study_idx in range(study_count):
        problem += (
            pulp.lpSum(
                y[column_id]
                for column_id in pattern_repo.columns_by_study.get(study_idx, [])
                if column_id in y
            )
            <= 1,
            f"Study_{study_idx}",
        )

    for doctor_class in doctor_classes:
        problem += (
            pulp.lpSum(
                y[column_id]
                for column_id in pattern_repo.columns_by_class.get(doctor_class.class_id, [])
                if column_id in y
            )
            <= doctor_class.count,
            f"Class_{doctor_class.class_id}",
        )

    return problem, y


def solve_master_problem(
    *,
    pattern_repo: PatternRepository,
    doctor_classes: List[DoctorClass],
    study_count: int,
    base_constant: float,
    fixed_zero: frozenset[int],
    fixed_one: frozenset[int],
    as_integer: bool,
) -> MasterSolveResult:
    import pulp

    problem, y = _build_master_problem(
        pattern_repo=pattern_repo,
        doctor_classes=doctor_classes,
        study_count=study_count,
        base_constant=base_constant,
        fixed_zero=fixed_zero,
        fixed_one=fixed_one,
        as_integer=as_integer,
    )
    solver = pulp.PULP_CBC_CMD(
        mip=as_integer,
        msg=False,
        threads=1,
    )
    problem.solve(solver)

    status = pulp.LpStatus[problem.status]
    variable_values = {
        column_id: float(pulp.value(variable) or 0.0)
        for column_id, variable in y.items()
    }
    objective_value = float(pulp.value(problem.objective) or base_constant)

    study_duals: Dict[int, float] = {}
    class_duals: Dict[int, float] = {}
    if not as_integer:
        for study_idx in range(study_count):
            dual = problem.constraints[f"Study_{study_idx}"].pi
            study_duals[study_idx] = float(dual or 0.0)
        for doctor_class in doctor_classes:
            dual = problem.constraints[f"Class_{doctor_class.class_id}"].pi
            class_duals[doctor_class.class_id] = float(dual or 0.0)

    return MasterSolveResult(
        status=status,
        objective_value=objective_value,
        variable_values=variable_values,
        study_duals=study_duals,
        class_duals=class_duals,
    )


def _pattern_reduced_cost(
    *,
    option_pool: ClassOptionPool,
    option_ids: Iterable[int],
    study_duals: Optional[Dict[int, float]] = None,
    class_dual: float = 0.0,
) -> float:
    study_duals = study_duals or {}
    total_cost = 0.0
    total_dual = 0.0
    for option_id in option_ids:
        option = option_pool.options[option_id]
        total_cost += option_pool.reduced_cost_by_option[option_id]
        total_dual += float(study_duals.get(option.study_idx, 0.0))
    return float(total_cost - total_dual - class_dual)


def _greedy_pattern_from_order(
    *,
    option_pool: ClassOptionPool,
    ordered_option_ids: Iterable[int],
    forced_study_indices: frozenset[int],
    forbidden_signatures: frozenset[Tuple[int, ...]],
    study_duals: Optional[Dict[int, float]] = None,
    class_dual: float = 0.0,
) -> Optional[Tuple[int, ...]]:
    used_studies = set(forced_study_indices)
    used_slots: set[int] = set()
    used_up = 0.0
    selected_option_ids: List[int] = []
    max_up = option_pool.doctor_class.representative.max_up

    for option_id in ordered_option_ids:
        option = option_pool.options[option_id]
        if option.study_idx in used_studies:
            continue
        if used_up + option_pool.up_by_option[option_id] > max_up + 1e-9:
            continue
        if any(slot_idx in used_slots for slot_idx in option.occupied_slots):
            continue

        selected_option_ids.append(option_id)
        used_studies.add(option.study_idx)
        used_up += option_pool.up_by_option[option_id]
        used_slots.update(option.occupied_slots)

    signature = tuple(sorted(selected_option_ids))
    if not signature or signature in forbidden_signatures:
        return None

    reduced_cost = _pattern_reduced_cost(
        option_pool=option_pool,
        option_ids=signature,
        study_duals=study_duals,
        class_dual=class_dual,
    )
    if reduced_cost >= -1e-6:
        return None
    return signature


def _heuristic_pattern_signatures(
    *,
    option_pool: ClassOptionPool,
    study_duals: Optional[Dict[int, float]] = None,
    class_dual: float = 0.0,
    forced_study_indices: frozenset[int] = frozenset(),
    forbidden_signatures: frozenset[Tuple[int, ...]] = frozenset(),
) -> List[Tuple[int, ...]]:
    study_duals = study_duals or {}
    candidate_ids: List[int] = []
    for option in option_pool.options:
        if option.study_idx in forced_study_indices:
            continue
        marginal_profit = float(study_duals.get(option.study_idx, 0.0) - option_pool.reduced_cost_by_option[option.option_id])
        if study_duals and marginal_profit <= EPS:
            continue
        candidate_ids.append(option.option_id)

    if not candidate_ids:
        return []

    def profit_value(option_id: int) -> float:
        option = option_pool.options[option_id]
        return float(study_duals.get(option.study_idx, 0.0) - option_pool.reduced_cost_by_option[option_id])

    orderings = [
        sorted(candidate_ids, key=lambda option_id: option_pool.reduced_cost_by_option[option_id]),
        sorted(
            candidate_ids,
            key=lambda option_id: (
                -profit_value(option_id),
                option_pool.options[option_id].finish_dt,
                option_pool.options[option_id].start_dt,
            ),
        ),
        sorted(
            candidate_ids,
            key=lambda option_id: (
                -(profit_value(option_id) / max(1, len(option_pool.options[option_id].occupied_slots))),
                option_pool.options[option_id].finish_dt,
            ),
        ),
        sorted(
            candidate_ids,
            key=lambda option_id: (
                option_pool.options[option_id].finish_dt,
                option_pool.reduced_cost_by_option[option_id],
            ),
        ),
    ]

    signatures: List[Tuple[int, ...]] = []
    seen = set(forbidden_signatures)
    for ordered_option_ids in orderings:
        signature = _greedy_pattern_from_order(
            option_pool=option_pool,
            ordered_option_ids=ordered_option_ids,
            forced_study_indices=forced_study_indices,
            forbidden_signatures=frozenset(seen),
            study_duals=study_duals,
            class_dual=class_dual,
        )
        if signature is None or signature in seen:
            continue
        seen.add(signature)
        signatures.append(signature)

    return signatures


def seed_initial_columns(
    *,
    pattern_repo: PatternRepository,
    option_pools: Dict[int, ClassOptionPool],
    study_count: int,
    log: Callable[[str], None],
) -> None:
    best_singleton_by_study: Dict[int, Tuple[int, int, float]] = {}
    for class_id, option_pool in option_pools.items():
        for study_idx, option_id in option_pool.best_option_id_by_study.items():
            reduced_cost = option_pool.reduced_cost_by_option[option_id]
            current = best_singleton_by_study.get(study_idx)
            if current is None or reduced_cost < current[2]:
                best_singleton_by_study[study_idx] = (class_id, option_id, reduced_cost)

    singleton_count = 0
    for study_idx in range(study_count):
        if study_idx not in best_singleton_by_study:
            continue
        class_id, option_id, _ = best_singleton_by_study[study_idx]
        column = pattern_repo.add_column(
            class_id=class_id,
            option_ids=(option_id,),
            option_pool=option_pools[class_id],
        )
        if column is not None:
            singleton_count += 1

    heuristic_count = 0
    for class_id, option_pool in option_pools.items():
        for signature in _heuristic_pattern_signatures(option_pool=option_pool):
            column = pattern_repo.add_column(
                class_id=class_id,
                option_ids=signature,
                option_pool=option_pools[class_id],
            )
            if column is not None:
                heuristic_count += 1

    log(
        f"BranchPrice: seeded columns singleton={singleton_count}, heuristic={heuristic_count}, "
        f"total={len(pattern_repo.columns)}"
    )


def _solve_pricing_problem(
    *,
    option_pool: ClassOptionPool,
    study_duals: Dict[int, float],
    class_dual: float,
    forced_study_indices: frozenset[int],
    forbidden_signatures: frozenset[Tuple[int, ...]],
) -> PricingResult:
    import pulp

    profitable_option_ids: List[int] = []
    options_by_study: Dict[int, List[int]] = defaultdict(list)
    options_by_slot: Dict[int, List[int]] = defaultdict(list)

    for option in option_pool.options:
        if option.study_idx in forced_study_indices:
            continue

        profit = float(study_duals.get(option.study_idx, 0.0) - option_pool.reduced_cost_by_option[option.option_id])
        if profit <= EPS:
            continue

        profitable_option_ids.append(option.option_id)
        options_by_study[option.study_idx].append(option.option_id)
        for slot_idx in option.occupied_slots:
            options_by_slot[slot_idx].append(option.option_id)

    if not profitable_option_ids:
        return PricingResult(
            class_id=option_pool.doctor_class.class_id,
            profitable_option_count=0,
            selected_option_ids=tuple(),
            profit_value=0.0,
            reduced_cost=0.0,
        )

    problem = pulp.LpProblem(
        f"Pricing_class_{option_pool.doctor_class.class_id}",
        pulp.LpMaximize,
    )
    z = {
        option_id: pulp.LpVariable(f"z_{option_id}", cat="Binary")
        for option_id in profitable_option_ids
    }

    for study_idx, option_ids in options_by_study.items():
        if option_ids:
            problem += (
                pulp.lpSum(z[option_id] for option_id in option_ids) <= 1,
                f"Study_{study_idx}",
            )

    for slot_idx, option_ids in options_by_slot.items():
        if option_ids:
            problem += (
                pulp.lpSum(z[option_id] for option_id in option_ids) <= 1,
                f"Slot_{slot_idx}",
            )

    problem += (
        pulp.lpSum(
            option_pool.up_by_option[option_id] * z[option_id]
            for option_id in profitable_option_ids
        )
        <= option_pool.doctor_class.representative.max_up,
        "UP",
    )

    problem += pulp.lpSum(
        (
            study_duals.get(option_pool.options[option_id].study_idx, 0.0)
            - option_pool.reduced_cost_by_option[option_id]
        )
        * z[option_id]
        for option_id in profitable_option_ids
    )

    solver = pulp.PULP_CBC_CMD(msg=False, threads=1)
    no_good_index = 0
    while True:
        problem.solve(solver)

        status = pulp.LpStatus[problem.status]
        if status not in {"Optimal", "Integer Feasible"}:
            return PricingResult(
                class_id=option_pool.doctor_class.class_id,
                profitable_option_count=len(profitable_option_ids),
                selected_option_ids=tuple(),
                profit_value=0.0,
                reduced_cost=0.0,
            )

        selected_option_ids = tuple(
            sorted(
                option_id
                for option_id, variable in z.items()
                if (pulp.value(variable) or 0.0) > 0.5
            )
        )
        profit_value = float(pulp.value(problem.objective) or 0.0)
        reduced_cost = float(-profit_value - class_dual)

        if reduced_cost >= -1e-6 or not selected_option_ids:
            return PricingResult(
                class_id=option_pool.doctor_class.class_id,
                profitable_option_count=len(profitable_option_ids),
                selected_option_ids=selected_option_ids,
                profit_value=profit_value,
                reduced_cost=reduced_cost,
            )

        if selected_option_ids not in forbidden_signatures:
            return PricingResult(
                class_id=option_pool.doctor_class.class_id,
                profitable_option_count=len(profitable_option_ids),
                selected_option_ids=selected_option_ids,
                profit_value=profit_value,
                reduced_cost=reduced_cost,
            )

        problem += (
            pulp.lpSum(z[option_id] for option_id in selected_option_ids)
            <= len(selected_option_ids) - 1,
            f"NoGood_{no_good_index}",
        )
        no_good_index += 1


def _is_integral_solution(variable_values: Dict[int, float]) -> bool:
    return all(abs(value - round(value)) <= 1e-6 for value in variable_values.values())


def _choose_branch_column(variable_values: Dict[int, float]) -> Optional[int]:
    fractional = [
        (abs(value - 0.5), column_id)
        for column_id, value in variable_values.items()
        if EPS < value < 1.0 - EPS
    ]
    if not fractional:
        return None
    fractional.sort(key=lambda item: item[0])
    return fractional[0][1]


def _selected_columns_from_values(variable_values: Dict[int, float]) -> set[int]:
    return {column_id for column_id, value in variable_values.items() if value > 0.5}


def _forced_studies_from_node(
    *,
    node: BranchPriceNode,
    pattern_repo: PatternRepository,
) -> frozenset[int]:
    forced_studies = set()
    for column_id in node.fixed_one:
        column = pattern_repo.columns.get(column_id)
        if column is None:
            continue
        forced_studies.update(column.study_indices)
    return frozenset(forced_studies)


def _fixed_class_usage_from_node(
    *,
    node: BranchPriceNode,
    pattern_repo: PatternRepository,
) -> Dict[int, int]:
    usage: Dict[int, int] = defaultdict(int)
    for column_id in node.fixed_one:
        column = pattern_repo.columns.get(column_id)
        if column is None:
            continue
        usage[column.class_id] += 1
    return dict(usage)


def run_column_generation(
    *,
    node: BranchPriceNode,
    doctor_classes: List[DoctorClass],
    option_pools: Dict[int, ClassOptionPool],
    pattern_repo: PatternRepository,
    study_count: int,
    base_constant: float,
    log: Callable[[str], None],
) -> Optional[MasterSolveResult]:
    iteration = 0
    forced_studies = _forced_studies_from_node(node=node, pattern_repo=pattern_repo)
    fixed_class_usage = _fixed_class_usage_from_node(node=node, pattern_repo=pattern_repo)

    while True:
        iteration += 1
        lp_result = solve_master_problem(
            pattern_repo=pattern_repo,
            doctor_classes=doctor_classes,
            study_count=study_count,
            base_constant=base_constant,
            fixed_zero=node.fixed_zero,
            fixed_one=node.fixed_one,
            as_integer=False,
        )

        if lp_result.status not in {"Optimal"}:
            log(
                f"BranchPrice node {node.node_id}: LP status={lp_result.status}, "
                "node pruned as infeasible"
            )
            return None

        log(
            f"BranchPrice node {node.node_id} iter {iteration}: "
            f"LP obj={lp_result.objective_value:.6f}, columns={len(pattern_repo.columns)}"
        )

        pricing_inputs = []
        for doctor_class in doctor_classes:
            class_id = doctor_class.class_id
            if fixed_class_usage.get(class_id, 0) >= doctor_class.count:
                continue
            pricing_inputs.append(
                (
                    option_pools[class_id],
                    lp_result.study_duals,
                    lp_result.class_duals.get(class_id, 0.0),
                    forced_studies,
                )
            )

        if not pricing_inputs:
            return lp_result

        heuristic_added_columns = 0
        for option_pool, study_duals, class_dual, forced_study_indices in pricing_inputs:
            forbidden_signatures = frozenset(
                pattern_repo.columns[column_id].option_ids
                for column_id in pattern_repo.columns_by_class.get(option_pool.doctor_class.class_id, [])
            )
            heuristic_signatures = _heuristic_pattern_signatures(
                option_pool=option_pool,
                study_duals=study_duals,
                class_dual=class_dual,
                forced_study_indices=forced_study_indices,
                forbidden_signatures=forbidden_signatures,
            )
            for signature in heuristic_signatures:
                column = pattern_repo.add_column(
                    class_id=option_pool.doctor_class.class_id,
                    option_ids=signature,
                    option_pool=option_pool,
                )
                if column is not None:
                    heuristic_added_columns += 1

        if heuristic_added_columns:
            log(
                f"BranchPrice node {node.node_id}: heuristic pricing added "
                f"{heuristic_added_columns} columns"
            )
            continue

        max_workers = min(len(pricing_inputs), os.cpu_count() or 1)
        if max_workers <= 1:
            pricing_results = [
                _solve_pricing_problem(
                    option_pool=option_pool,
                    study_duals=study_duals,
                    class_dual=class_dual,
                    forced_study_indices=forced_study_indices,
                    forbidden_signatures=frozenset(
                        pattern_repo.columns[column_id].option_ids
                        for column_id in pattern_repo.columns_by_class.get(option_pool.doctor_class.class_id, [])
                    ),
                )
                for option_pool, study_duals, class_dual, forced_study_indices in pricing_inputs
            ]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(
                        _solve_pricing_problem,
                        option_pool=option_pool,
                        study_duals=study_duals,
                        class_dual=class_dual,
                        forced_study_indices=forced_study_indices,
                        forbidden_signatures=frozenset(
                            pattern_repo.columns[column_id].option_ids
                            for column_id in pattern_repo.columns_by_class.get(option_pool.doctor_class.class_id, [])
                        ),
                    )
                    for option_pool, study_duals, class_dual, forced_study_indices in pricing_inputs
                ]
                pricing_results = [future.result() for future in futures]

        added_columns = 0
        for pricing_result in pricing_results:
            log(
                f"  pricing class={pricing_result.class_id}: "
                f"profitable={pricing_result.profitable_option_count}, "
                f"profit={pricing_result.profit_value:.6f}, "
                f"reduced_cost={pricing_result.reduced_cost:.6f}"
            )
            if pricing_result.reduced_cost >= -1e-6:
                continue

            column = pattern_repo.add_column(
                class_id=pricing_result.class_id,
                option_ids=pricing_result.selected_option_ids,
                option_pool=option_pools[pricing_result.class_id],
            )
            if column is None:
                continue
            added_columns += 1

        if added_columns == 0:
            return lp_result

        log(
            f"BranchPrice node {node.node_id}: added {added_columns} columns, "
            "continuing column generation"
        )


def _build_solution_payload(
    *,
    selected_column_ids: Iterable[int],
    pattern_repo: PatternRepository,
    option_pools: Dict[int, ClassOptionPool],
    doctor_classes: List[DoctorClass],
    studies: List[StudyData],
    unassigned_meta_by_study: Dict[int, Dict],
) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict]]:
    selected_by_class: Dict[int, List[PatternColumn]] = defaultdict(list)
    for column_id in selected_column_ids:
        column = pattern_repo.columns[column_id]
        selected_by_class[column.class_id].append(column)

    assignment: Dict[str, int] = {}
    details: Dict[str, Dict] = {}
    solver_obj = 0.0

    doctor_classes_by_id = {doctor_class.class_id: doctor_class for doctor_class in doctor_classes}

    for class_id, columns in selected_by_class.items():
        doctor_class = doctor_classes_by_id[class_id]
        option_pool = option_pools[class_id]
        ordered_columns = sorted(
            columns,
            key=lambda column: min(option_pool.options[option_id].start_dt for option_id in column.option_ids),
        )
        for doctor, column in zip(doctor_class.doctors, ordered_columns):
            solver_obj += float(column.cost)
            for option_id in column.option_ids:
                option = option_pool.options[option_id]
                study = studies[option.study_idx]
                assignment[study.research_number] = doctor.id
                details[study.research_number] = {
                    "doctor_id": doctor.id,
                    "doctor_name": doctor.name,
                    "start_dt": option.start_dt,
                    "finish_dt": option.finish_dt,
                    **{key: float(value) for key, value in option.metrics.items()},
                }

    assigned_indices = {
        next(
            index
            for index, study in enumerate(studies)
            if study.research_number == study_number
        )
        for study_number in assignment
    }
    unassigned_meta = {
        studies[index].research_number: dict(unassigned_meta_by_study[index])
        for index in range(len(studies))
        if index not in assigned_indices
    }
    return assignment, details, solver_obj, unassigned_meta


def solve_branch_price_mip(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    objective,
    priority_weights: Dict[str, float],
    planning_now,
    base_constant: float,
    unassigned_meta_by_study: Dict[int, Dict],
    unassigned_cost_by_study: Dict[int, float],
    log: Callable[[str], None],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict]]:
    start_total = time.perf_counter()
    doctor_classes = build_doctor_classes(
        doctors=doctors,
        doc_prebooked_minutes=doc_prebooked_minutes,
        log=log,
    )
    if not doctor_classes:
        return {}, {}, float(base_constant), {
            studies[index].research_number: dict(unassigned_meta_by_study[index])
            for index in range(len(studies))
        }

    option_pools: Dict[int, ClassOptionPool] = {}
    total_representative_options = 0
    t_build_pools = time.perf_counter()
    for doctor_class in doctor_classes:
        option_pool = build_class_option_pool(
            doctor_class=doctor_class,
            studies=studies,
            objective=objective,
            priority_weights=priority_weights,
            planning_now=planning_now,
            unassigned_cost_by_study=unassigned_cost_by_study,
            log=log,
        )
        option_pools[doctor_class.class_id] = option_pool
        total_representative_options += len(option_pool.options)

    log(f"BranchPrice: representative options={total_representative_options}")
    log(f"TIMING branch_price_build_pools: {time.perf_counter() - t_build_pools:.2f}s")

    pattern_repo = PatternRepository()
    seed_initial_columns(
        pattern_repo=pattern_repo,
        option_pools=option_pools,
        study_count=len(studies),
        log=log,
    )

    incumbent_obj = float(base_constant)
    incumbent_columns: set[int] = set()
    node_counter = 0
    pending_nodes: List[BranchPriceNode] = [
        BranchPriceNode(
            priority=float(base_constant),
            node_id=node_counter,
            depth=0,
        )
    ]
    node_counter += 1
    explored_nodes = 0

    while pending_nodes:
        node = heapq.heappop(pending_nodes)
        explored_nodes += 1
        log(
            f"BranchPrice node {node.node_id}: depth={node.depth}, "
            f"fixed_zero={len(node.fixed_zero)}, fixed_one={len(node.fixed_one)}"
        )

        lp_result = run_column_generation(
            node=node,
            doctor_classes=doctor_classes,
            option_pools=option_pools,
            pattern_repo=pattern_repo,
            study_count=len(studies),
            base_constant=base_constant,
            log=log,
        )
        if lp_result is None:
            continue

        if lp_result.objective_value >= incumbent_obj - 1e-6:
            log(
                f"BranchPrice node {node.node_id}: pruned by bound "
                f"({lp_result.objective_value:.6f} >= {incumbent_obj:.6f})"
            )
            continue

        restricted_mip = solve_master_problem(
            pattern_repo=pattern_repo,
            doctor_classes=doctor_classes,
            study_count=len(studies),
            base_constant=base_constant,
            fixed_zero=node.fixed_zero,
            fixed_one=node.fixed_one,
            as_integer=True,
        )
        if restricted_mip.status in {"Optimal", "Integer Feasible"}:
            if restricted_mip.objective_value < incumbent_obj - 1e-6:
                incumbent_obj = restricted_mip.objective_value
                incumbent_columns = _selected_columns_from_values(restricted_mip.variable_values)
                log(
                    f"BranchPrice node {node.node_id}: incumbent improved to "
                    f"{incumbent_obj:.6f} with {len(incumbent_columns)} columns"
                )

        if _is_integral_solution(lp_result.variable_values):
            selected_columns = _selected_columns_from_values(lp_result.variable_values)
            if lp_result.objective_value < incumbent_obj - 1e-6:
                incumbent_obj = lp_result.objective_value
                incumbent_columns = selected_columns
                log(
                    f"BranchPrice node {node.node_id}: integral LP improved incumbent to "
                    f"{incumbent_obj:.6f}"
                )
            continue

        branch_column_id = _choose_branch_column(lp_result.variable_values)
        if branch_column_id is None:
            continue

        left_node = BranchPriceNode(
            priority=lp_result.objective_value,
            node_id=node_counter,
            depth=node.depth + 1,
            fixed_zero=node.fixed_zero | frozenset({branch_column_id}),
            fixed_one=node.fixed_one,
        )
        node_counter += 1
        right_node = BranchPriceNode(
            priority=lp_result.objective_value,
            node_id=node_counter,
            depth=node.depth + 1,
            fixed_zero=node.fixed_zero,
            fixed_one=node.fixed_one | frozenset({branch_column_id}),
        )
        node_counter += 1
        heapq.heappush(pending_nodes, left_node)
        heapq.heappush(pending_nodes, right_node)
        log(
            f"BranchPrice node {node.node_id}: branching on column {branch_column_id}"
        )

    assignment, details, delta_obj, unassigned_meta = _build_solution_payload(
        selected_column_ids=incumbent_columns,
        pattern_repo=pattern_repo,
        option_pools=option_pools,
        doctor_classes=doctor_classes,
        studies=studies,
        unassigned_meta_by_study=unassigned_meta_by_study,
    )
    solver_obj = float(base_constant + delta_obj)
    log(
        f"Exact solver: назначено {len(assignment)} / {len(studies)}, "
        f"неназначено {len(unassigned_meta)} / {len(studies)}"
    )
    log(
        f"BranchPrice: explored_nodes={explored_nodes}, columns={len(pattern_repo.columns)}, "
        f"assigned={len(assignment)}, obj={solver_obj:.6f}"
    )
    log(f"TIMING branch_price_total: {time.perf_counter() - start_total:.2f}s")
    return assignment, details, solver_obj, unassigned_meta
