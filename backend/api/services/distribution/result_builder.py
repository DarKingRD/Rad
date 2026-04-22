from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping

from .entities import DoctorData, StudyData


def _pct(value: float, total: float) -> float:
    return round(value / total * 100, 2) if total > 0 else 0.0


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)

    ordered = sorted(values)
    idx = (len(ordered) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * frac, 2)


def build_empty_distribution_response(
    *,
    message: str,
    studies_count: int,
    objective_meta: Dict[str, Any],
    debug_log: List[str],
) -> Dict[str, Any]:
    zero_summary = {
        "total": studies_count,
        "assigned": 0,
        "unassigned": studies_count,
        "assignment_rate_percent": 0.0,
        "overdue_total": 0,
        "overdue_assigned": 0,
        "overdue_unassigned": 0,
        "overdue_rate_percent": 0.0,
        "total_tardiness": 0.0,
        "total_weighted_tardiness": 0.0,
        "avg_tardiness": 0.0,
        "tardiness_p50": 0.0,
        "tardiness_p95": 0.0,
        "tardiness_p99": 0.0,
    }
    zero_priority = {
        "priority": "",
        "total": 0,
        "assigned": 0,
        "unassigned": 0,
        "assigned_rate_percent": 0.0,
        "overdue_total": 0,
        "overdue_assigned": 0,
        "overdue_unassigned": 0,
        "projected_tardiness_total": 0.0,
        "projected_weighted_tardiness_total": 0.0,
        "tardiness_p50": 0.0,
        "tardiness_p95": 0.0,
        "tardiness_p99": 0.0,
    }
    return {
        "summary": zero_summary,
        "priority_breakdown": {
            "plan": {**zero_priority, "priority": "normal"},
            "asap": {**zero_priority, "priority": "asap"},
            "cito": {**zero_priority, "priority": "cito"},
        },
        "doctor_stats": [],
        "assignments": [],
        "objective": {
            "solver_objective_value": 0.0,
            "reported_objective_value": 0.0,
            "total_unassigned_objective": 0.0,
            "meta": objective_meta,
        },
        "message": message,
        "_debug": debug_log,
    }


def build_distribution_response(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    assignment: Mapping[str, int],
    details: Mapping[str, Dict[str, Any]],
    unassigned_meta: Mapping[str, Dict[str, Any]],
    solver_obj: float,
    now: datetime,
    preview_mode: bool,
    target_date_iso: str,
    objective_code: str,
    objective_meta: Dict[str, Any],
    debug_log: List[str],
) -> Dict[str, Any]:
    study_map = {study.research_number: study for study in studies}
    doctor_map = {doctor.id: doctor for doctor in doctors}
    assigned_ids = set(assignment.keys())

    for doctor in doctors:
        doctor.reset_runtime_stats()

    for study_id, doctor_id in assignment.items():
        study = study_map.get(study_id)
        doctor = doctor_map.get(doctor_id)
        if study is None or doctor is None:
            continue
        doctor.assigned_ids.append(study_id)
        doctor.used_up += study.up_value
        doctor.used_minutes += study.duration_minutes

    all_assignments: List[Dict[str, Any]] = []
    total_assigned_objective = 0.0
    total_unassigned_objective = 0.0
    assigned_completion_tardiness = 0.0
    assigned_completion_weighted_tardiness = 0.0
    projected_unassigned_tardiness = 0.0
    projected_unassigned_weighted_tardiness = 0.0

    assigned_tardiness_by_study: Dict[str, float] = {}
    assigned_weighted_tardiness_by_study: Dict[str, float] = {}
    unassigned_tardiness_by_study: Dict[str, float] = {}
    unassigned_weighted_tardiness_by_study: Dict[str, float] = {}

    for study_id, meta in details.items():
        study = study_map[study_id]
        doctor = doctor_map[meta["doctor_id"]]
        tardiness = float(meta["tardiness_hours"])
        weighted_tardiness = float(meta["weighted_tardiness"])
        objective_value = float(meta.get("objective_value", weighted_tardiness))

        assigned_completion_tardiness += tardiness
        assigned_completion_weighted_tardiness += weighted_tardiness
        total_assigned_objective += objective_value
        assigned_tardiness_by_study[study_id] = tardiness
        assigned_weighted_tardiness_by_study[study_id] = weighted_tardiness

        all_assignments.append(
            {
                "study_number": study.research_number,
                "priority": study.priority,
                "study_modality": list(study.modality),
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "deadline": study.deadline.isoformat(),
                "start_time": meta["start_dt"].isoformat(),
                "completion_time": meta["finish_dt"].isoformat(),
                "tardiness_hours": round(tardiness, 2),
                "weighted_tardiness": round(weighted_tardiness, 3),
                "objective_value": round(objective_value, 3),
                "up_value": study.up_value,
                "is_overdue": study.deadline < now,
            }
        )

    for study in studies:
        if study.research_number in assigned_ids:
            continue

        meta = unassigned_meta.get(study.research_number, {})
        tardiness = float(meta.get("tardiness_hours", 0.0))
        weighted_tardiness = float(meta.get("weighted_tardiness", 0.0))
        objective_value = float(meta.get("objective_value", 0.0))
        virtual_finish_dt = meta.get("virtual_finish_dt")

        projected_unassigned_tardiness += tardiness
        projected_unassigned_weighted_tardiness += weighted_tardiness
        total_unassigned_objective += objective_value
        unassigned_tardiness_by_study[study.research_number] = tardiness
        unassigned_weighted_tardiness_by_study[study.research_number] = weighted_tardiness

        all_assignments.append(
            {
                "study_number": study.research_number,
                "priority": study.priority,
                "study_modality": list(study.modality),
                "doctor_id": None,
                "doctor_name": None,
                "deadline": study.deadline.isoformat(),
                "start_time": None,
                "completion_time": None,
                "virtual_completion_time": virtual_finish_dt.isoformat() if virtual_finish_dt else None,
                "tardiness_hours": round(tardiness, 2),
                "weighted_tardiness": round(weighted_tardiness, 3),
                "objective_value": round(objective_value, 3),
                "up_value": study.up_value,
                "is_overdue": study.deadline < now,
            }
        )

    total_studies = len(studies)
    assigned_count = len(assignment)
    overdue_total = sum(1 for study in studies if study.deadline < now)
    overdue_assigned = sum(1 for study in studies if study.deadline < now and study.research_number in assigned_ids)

    projected_total_tardiness = assigned_completion_tardiness + projected_unassigned_tardiness
    projected_total_weighted_tardiness = assigned_completion_weighted_tardiness + projected_unassigned_weighted_tardiness

    all_tardiness_values: List[float] = []
    priority_breakdown: Dict[str, Dict[str, Any]] = {}
    priority_labels = {"normal": "plan", "asap": "asap", "cito": "cito"}

    for priority_code, output_key in priority_labels.items():
        priority_studies = [study for study in studies if study.priority == priority_code]
        priority_total = len(priority_studies)
        priority_assigned = sum(1 for study in priority_studies if study.research_number in assigned_ids)
        priority_overdue_total = sum(1 for study in priority_studies if study.deadline < now)
        priority_overdue_assigned = sum(
            1 for study in priority_studies if study.deadline < now and study.research_number in assigned_ids
        )

        priority_tardiness_values: List[float] = []
        priority_weighted_values: List[float] = []

        for study in priority_studies:
            if study.research_number in assigned_ids:
                tardiness = assigned_tardiness_by_study.get(study.research_number, 0.0)
                weighted = assigned_weighted_tardiness_by_study.get(study.research_number, 0.0)
            else:
                tardiness = unassigned_tardiness_by_study.get(study.research_number, 0.0)
                weighted = unassigned_weighted_tardiness_by_study.get(study.research_number, 0.0)

            priority_tardiness_values.append(tardiness)
            priority_weighted_values.append(weighted)
            all_tardiness_values.append(tardiness)

        priority_breakdown[output_key] = {
            "priority": priority_code,
            "total": priority_total,
            "assigned": priority_assigned,
            "unassigned": priority_total - priority_assigned,
            "assigned_rate_percent": _pct(priority_assigned, priority_total),
            "overdue_total": priority_overdue_total,
            "overdue_assigned": priority_overdue_assigned,
            "overdue_unassigned": priority_overdue_total - priority_overdue_assigned,
            "projected_tardiness_total": round(sum(priority_tardiness_values), 2),
            "projected_weighted_tardiness_total": round(sum(priority_weighted_values), 3),
            "tardiness_p50": _percentile(priority_tardiness_values, 0.5),
            "tardiness_p95": _percentile(priority_tardiness_values, 0.95),
            "tardiness_p99": _percentile(priority_tardiness_values, 0.99),
        }

    all_assignments.sort(
        key=lambda item: (
            item["doctor_id"] is None,
            item["doctor_name"] or "",
            item["start_time"] or "",
            item["study_number"] or "",
        )
    )

    return {
        "summary": {
            "total": total_studies,
            "assigned": assigned_count,
            "unassigned": total_studies - assigned_count,
            "assignment_rate_percent": _pct(assigned_count, total_studies),
            "overdue_total": overdue_total,
            "overdue_assigned": overdue_assigned,
            "overdue_unassigned": overdue_total - overdue_assigned,
            "overdue_rate_percent": _pct(overdue_total, total_studies),
            "total_tardiness": round(projected_total_tardiness, 2),
            "total_weighted_tardiness": round(projected_total_weighted_tardiness, 3),
            "avg_tardiness": round(projected_total_tardiness / total_studies, 2) if total_studies else 0.0,
            "tardiness_p50": _percentile(all_tardiness_values, 0.5),
            "tardiness_p95": _percentile(all_tardiness_values, 0.95),
            "tardiness_p99": _percentile(all_tardiness_values, 0.99),
        },
        "priority_breakdown": priority_breakdown,
        "doctor_stats": [
            {
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "assigned_studies": len(doctor.assigned_ids),
                "assigned_minutes": round(doctor.used_minutes, 2),
                "shift_hours": round(doctor.shift_hours, 2),
                "time_load_percent": round(doctor.used_minutes / doctor.shift_minutes * 100, 1)
                if doctor.shift_minutes
                else 0.0,
                "total_up": round(doctor.used_up, 3),
                "max_up": round(doctor.max_up, 3),
                "load_percent": round(doctor.used_up / doctor.max_up * 100, 1) if doctor.max_up else 0.0,
                "remaining_up": round(doctor.free_up, 3),
            }
            for doctor in doctors
        ],
        "assignments": all_assignments,
        "objective": {
            "solver_objective_value": round(float(solver_obj), 3),
            "reported_objective_value": round(total_assigned_objective + total_unassigned_objective, 3),
            "total_unassigned_objective": round(total_unassigned_objective, 3),
            "meta": objective_meta,
        },
        "message": (
            f"Оффлайн: назначено {assigned_count} из {total_studies} "
            f"({_pct(assigned_count, total_studies):.2f}%). "
            f"CITO: {priority_breakdown['cito']['assigned']}/{priority_breakdown['cito']['total']}. "
            f"objective={objective_code}"
        ),
        "_debug": debug_log,
        "preview_mode": preview_mode,
        "target_date": target_date_iso,
    }
