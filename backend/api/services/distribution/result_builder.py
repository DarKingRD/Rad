"""
Формирование итогового ответа сервиса распределения.

Модуль преобразует сырые результаты solver-слоя в структуру,
удобную для фронтенда и аналитики:
- список назначений;
- статистику по врачам;
- статистику по приоритетам;
- агрегаты по просрочке;
- итоговое диагностическое сообщение.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from .entities import DoctorData, StudyData


def _pct(value: float, total: float) -> float:
    """
    Безопасно вычислить процентное отношение value к total.

    Если total равен нулю, возвращается 0.0.
    """
    if total <= 0:
        return 0.0
    return round(value / total * 100, 2)


def _percentile(values: List[float], q: float) -> float:
    """
    Вычислить q-перцентиль по набору чисел линейной интерполяцией.

    Используется для расчёта p50, p95 и p99 по tardiness.
    """
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
    """
    Построить унифицированный пустой ответ сервиса распределения.

    Используется в случаях, когда расчёт невозможно выполнить:
    например, нет врачей, нет исследований или не сформирован candidate pool.
    """
    return {
        "assigned": 0,
        "unassigned": studies_count,
        "assignment_rate_percent": 0.0,
        "scheduled_pool_size": 0,
        "candidate_pool_size": 0,
        "backlog_outside_pool": studies_count,
        "total_tardiness": 0.0,
        "total_weighted_tardiness": 0.0,
        "avg_tardiness": 0,
        "tardiness_p50": 0.0,
        "tardiness_p95": 0.0,
        "tardiness_p99": 0.0,
        "overdue_total": 0,
        "overdue_assigned": 0,
        "overdue_unassigned": 0,
        "overdue_rate_percent": 0.0,
        "priority_breakdown": {
            "plan": {
                "priority": "normal",
                "total": 0,
                "assigned": 0,
                "unassigned": 0,
                "share_percent": 0.0,
                "assigned_rate_percent": 0.0,
                "overdue_total": 0,
                "overdue_assigned": 0,
                "overdue_unassigned": 0,
                "overdue_rate_percent": 0.0,
                "overdue_hours_total": 0.0,
                "overdue_hours_avg": 0.0,
                "tardiness_p50": 0.0,
                "tardiness_p95": 0.0,
                "tardiness_p99": 0.0,
            },
            "asap": {
                "priority": "asap",
                "total": 0,
                "assigned": 0,
                "unassigned": 0,
                "share_percent": 0.0,
                "assigned_rate_percent": 0.0,
                "overdue_total": 0,
                "overdue_assigned": 0,
                "overdue_unassigned": 0,
                "overdue_rate_percent": 0.0,
                "overdue_hours_total": 0.0,
                "overdue_hours_avg": 0.0,
                "tardiness_p50": 0.0,
                "tardiness_p95": 0.0,
                "tardiness_p99": 0.0,
            },
            "cito": {
                "priority": "cito",
                "total": 0,
                "assigned": 0,
                "unassigned": 0,
                "share_percent": 0.0,
                "assigned_rate_percent": 0.0,
                "overdue_total": 0,
                "overdue_assigned": 0,
                "overdue_unassigned": 0,
                "overdue_rate_percent": 0.0,
                "overdue_hours_total": 0.0,
                "overdue_hours_avg": 0.0,
                "tardiness_p50": 0.0,
                "tardiness_p95": 0.0,
                "tardiness_p99": 0.0,
            },
        },
        "assignments": [],
        "doctor_stats": [],
        "priority_stats": {"cito": 0, "asap": 0, "normal": 0},
        "objective_function": objective_meta,
        "solver_objective_value": 0.0,
        "reported_weighted_tardiness": 0.0,
        "total_unassigned_objective": 0.0,
        "reported_objective_value": 0.0,
        "message": message,
        "_debug": debug_log,
    }


def build_distribution_response(
    *,
    studies: List[StudyData],
    doctors: List[DoctorData],
    assignment: Dict[str, int],
    details: Dict[str, Dict[str, Any]],
    unassigned_meta: Dict[str, Dict[str, Any]],
    candidate_pool: List[StudyData],
    solver_obj: float,
    now: datetime,
    preview_mode: bool,
    target_date_iso: str,
    objective_code: str,
    objective_meta: Dict[str, Any],
    debug_log: List[str],
) -> Dict[str, Any]:
    """
    Построить полный итоговый ответ по результатам распределения.

    Функция:
    - собирает назначения и неназначенные исследования;
    - рассчитывает суммарные метрики tardiness и objective;
    - формирует статистику по врачам;
    - формирует breakdown по приоритетам;
    - подготавливает финальный JSON-совместимый словарь для UI.
    """
    study_map = {s.research_number: s for s in studies}
    doctor_map = {d.id: d for d in doctors}

    # На случай повторного вызова на том же объекте сервиса.
    for doctor in doctors:
        doctor.assigned_ids.clear()
        doctor.used_up = 0.0
        doctor.used_minutes = 0.0

    for sid, did in assignment.items():
        if sid not in study_map or did not in doctor_map:
            continue
        doctor = doctor_map[did]
        doctor.assigned_ids.append(sid)
        doctor.used_up += study_map[sid].up_value
        doctor.used_minutes += study_map[sid].duration_minutes

    all_assignments: List[Dict[str, Any]] = []
    total_tardiness = 0.0
    total_weighted_tardiness = 0.0
    total_objective_value = 0.0
    total_unassigned_objective = 0.0
    pstats = {"cito": 0, "asap": 0, "normal": 0}

    for sid, meta in details.items():
        study = study_map[sid]
        doctor = doctor_map[meta["doctor_id"]]
        tardiness = float(meta["tardiness_hours"])
        weighted_tardiness = float(meta["weighted_tardiness"])
        objective_value = float(meta.get("objective_value", weighted_tardiness))

        total_tardiness += tardiness
        total_weighted_tardiness += weighted_tardiness
        total_objective_value += objective_value
        pstats[study.priority] = pstats.get(study.priority, 0) + 1

        all_assignments.append(
            {
                "study_number": study.research_number,
                "study_modality": list(study.modality),
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "doctor_modality": list(doctor.modality),
                "priority": study.priority,
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

    assigned_ids = set(assignment.keys())

    for study in studies:
        if study.research_number in assigned_ids:
            continue

        unassigned_item = unassigned_meta.get(study.research_number)
        if unassigned_item:
            total_unassigned_objective += float(unassigned_item.get("objective_value", 0.0))

        all_assignments.append(
            {
                "study_number": study.research_number,
                "study_modality": list(study.modality),
                "doctor_id": None,
                "doctor_name": None,
                "doctor_modality": [],
                "priority": study.priority,
                "deadline": study.deadline.isoformat(),
                "start_time": None,
                "completion_time": None,
                "tardiness_hours": None,
                "weighted_tardiness": None,
                "objective_value": round(float(unassigned_item.get("objective_value", 0.0)), 3)
                if unassigned_item
                else None,
                "up_value": study.up_value,
                "is_overdue": study.deadline < now,
                "virtual_completion_time": unassigned_item.get("virtual_finish_dt").isoformat()
                if unassigned_item and unassigned_item.get("virtual_finish_dt")
                else None,
            }
        )

    all_assignments.sort(
        key=lambda item: (
            item["doctor_id"] is None,
            item["doctor_name"] or "",
            item["start_time"] or "",
            item["study_number"] or "",
        )
    )

    n_asgn = len(assignment)
    total_studies = len(studies)
    pool_size = len(candidate_pool)
    backlog_outside_pool = max(0, total_studies - pool_size)
    z = round(total_weighted_tardiness, 3)
    reported_objective_value = round(total_objective_value + total_unassigned_objective, 3)

    assigned_tardiness_by_study = {
        item["study_number"]: float(item["tardiness_hours"])
        for item in all_assignments
        if item["tardiness_hours"] is not None
    }

    priority_labels = {
        "normal": "plan",
        "asap": "asap",
        "cito": "cito",
    }
    priority_breakdown: Dict[str, Dict[str, Any]] = {}

    overdue_total = 0
    overdue_assigned = 0

    for priority_code, output_key in priority_labels.items():
        priority_studies = [s for s in studies if s.priority == priority_code]
        priority_total = len(priority_studies)
        priority_assigned = sum(1 for s in priority_studies if s.research_number in assignment)
        priority_overdue_total = sum(1 for s in priority_studies if s.deadline < now)
        priority_overdue_assigned = sum(
            1
            for s in priority_studies
            if s.deadline < now and s.research_number in assignment
        )
        priority_overdue_hours_total = round(
            sum(max(0.0, (now - s.deadline).total_seconds() / 3600.0) for s in priority_studies),
            2,
        )
        priority_tardiness_values = [
            assigned_tardiness_by_study.get(s.research_number, 0.0)
            for s in priority_studies
        ]

        priority_breakdown[output_key] = {
            "priority": priority_code,
            "total": priority_total,
            "assigned": priority_assigned,
            "unassigned": priority_total - priority_assigned,
            "share_percent": _pct(priority_total, total_studies),
            "assigned_rate_percent": _pct(priority_assigned, priority_total),
            "overdue_total": priority_overdue_total,
            "overdue_assigned": priority_overdue_assigned,
            "overdue_unassigned": priority_overdue_total - priority_overdue_assigned,
            "overdue_rate_percent": _pct(priority_overdue_total, priority_total),
            "overdue_hours_total": priority_overdue_hours_total,
            "overdue_hours_avg": round(priority_overdue_hours_total / priority_overdue_total, 2)
            if priority_overdue_total
            else 0.0,
            "tardiness_p50": _percentile(priority_tardiness_values, 0.5),
            "tardiness_p95": _percentile(priority_tardiness_values, 0.95),
            "tardiness_p99": _percentile(priority_tardiness_values, 0.99),
        }

        overdue_total += priority_overdue_total
        overdue_assigned += priority_overdue_assigned

    n_cito_total = int(priority_breakdown["cito"]["total"])
    n_asap_total = int(priority_breakdown["asap"]["total"])
    n_normal_total = int(priority_breakdown["plan"]["total"])

    n_cito_assigned = int(priority_breakdown["cito"]["assigned"])
    n_asap_assigned = int(priority_breakdown["asap"]["assigned"])
    n_normal_assigned = int(priority_breakdown["plan"]["assigned"])

    tardiness_values = [
        item["tardiness_hours"]
        for item in all_assignments
        if item["tardiness_hours"] is not None
    ]
    tardiness_p50 = _percentile(tardiness_values, 0.5)
    tardiness_p95 = _percentile(tardiness_values, 0.95)
    tardiness_p99 = _percentile(tardiness_values, 0.99)

    return {
        "assigned": n_asgn,
        "unassigned": total_studies - n_asgn,
        "assignment_rate_percent": _pct(n_asgn, total_studies),
        "scheduled_pool_size": pool_size,
        "candidate_pool_size": pool_size,
        "backlog_outside_pool": backlog_outside_pool,
        "cito_assigned": n_cito_assigned,
        "cito_total": n_cito_total,
        "asap_total": n_asap_total,
        "normal_total": n_normal_total,
        "asap_assigned": n_asap_assigned,
        "normal_assigned": n_normal_assigned,
        "total_tardiness": round(total_tardiness, 2),
        "total_weighted_tardiness": z,
        "avg_tardiness": round(total_tardiness / n_asgn, 2) if n_asgn else 0,
        "tardiness_p50": tardiness_p50,
        "tardiness_p95": tardiness_p95,
        "tardiness_p99": tardiness_p99,
        "overdue_total": overdue_total,
        "overdue_assigned": overdue_assigned,
        "overdue_unassigned": overdue_total - overdue_assigned,
        "overdue_rate_percent": _pct(overdue_total, total_studies),
        "priority_breakdown": priority_breakdown,
        "assignments": all_assignments,
        "doctor_stats": [
            {
                "doctor_id": doctor.id,
                "doctor_name": doctor.name,
                "assigned_studies": len(doctor.assigned_ids),
                "total_up": round(doctor.used_up, 3),
                "max_up": round(doctor.max_up, 3),
                "load_percent": round(doctor.used_up / doctor.max_up * 100, 1)
                if doctor.max_up
                else 0,
                "remaining_up": round(doctor.free_up, 3),
            }
            for doctor in doctors
        ],
        "priority_stats": pstats,
        "objective_function": objective_meta,
        "solver_objective_value": round(float(solver_obj), 3),
        "reported_weighted_tardiness": z,
        "total_unassigned_objective": round(total_unassigned_objective, 3),
        "reported_objective_value": reported_objective_value,
        "message": (
            f"Оффлайн: candidate_pool {pool_size} из {total_studies}, назначено {n_asgn} "
            f"({_pct(n_asgn, total_studies):.2f}%). "
            f"CITO: {
                n_cito_assigned}/{n_cito_total}. objective={
                    objective_code}, Obj={reported_objective_value}"
        ),
        "_debug": debug_log,
        "preview_mode": preview_mode,
        "target_date": target_date_iso,
    }
