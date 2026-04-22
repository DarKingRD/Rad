"""
Главный orchestration-сервис оффлайн-распределения исследований.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from django.utils import timezone
from api.models import Study

from .config import DEADLINE_HOURS, MIP_GAP_REL, MIP_TIME_LIMIT, PRIORITY_WEIGHTS, CBC_THREADS
from .entities import DoctorData, StudyData
from .exact_solver import solve_exact_mip as solve_exact_mip_external
from .loaders import load_doctors as load_doctors_external
from .loaders import load_studies as load_studies_external
from .objectives import (
    OBJECTIVE_REGISTRY,
    ObjectiveStrategy,
    PriorityTierTardinessMultiPassObjective,
    WeightedTardinessLexicographicObjective,
)
from .result_builder import build_distribution_response, build_empty_distribution_response
from .time_utils import (
    add_work_minutes,
    align_to_work_time,
    effective_start_after_prebook,
    execution_segments,
    occupied_slot_indices,
    planning_horizon_end,
    slot_boundaries,
)

logger = logging.getLogger(__name__)

_PRIORITY_SORT_INDEX = {"cito": 0, "asap": 1, "normal": 2}


def _study_sort_key(study: StudyData, now: datetime, target_date: date):
    overdue_bucket = (
        0 if study.deadline < now and study.priority == "cito"
        else 1 if study.deadline < now and study.priority == "asap"
        else 2 if study.deadline < now and study.priority == "normal"
        else 3 if study.deadline.date() <= target_date
        else 4
    )
    return (
        overdue_bucket,
        _PRIORITY_SORT_INDEX.get(study.priority, 3),
        study.deadline,
        study.created_at,
        study.research_number,
    )


class DistributionService:
    """Сервисный слой оффлайн-распределения исследований."""

    def __init__(
        self,
        target_date: Optional[date] = None,
        preview_mode: bool = False,
        objective: Optional[str] = None,
        priority_weights: Optional[Dict[str, float]] = None,
        deadline_hours: Optional[Dict[str, float]] = None,
        objective_params: Optional[Dict[str, Any]] = None,
    ):
        self.real_now = timezone.now()
        self.now = self.real_now
        self.target_date = target_date or self.real_now.date()
        self.preview_mode = preview_mode
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.deadline_hours = {**DEADLINE_HOURS, **(deadline_hours or {})}
        self.objective_params = dict(objective_params or {})
        self._debug: List[str] = []

        self.objective: ObjectiveStrategy
        self.objective_code = ""
        self.objective_description = ""
        self.set_objective(objective or WeightedTardinessLexicographicObjective.code)

    def set_preview_mode(self, preview: bool = True) -> None:
        self.preview_mode = preview

    def _instantiate_objective(self, objective_code: str) -> ObjectiveStrategy:
        objective_cls = OBJECTIVE_REGISTRY.get(
            objective_code,
            WeightedTardinessLexicographicObjective,
        )
        return objective_cls(priority_weights=self.priority_weights, **self.objective_params)

    def _objective_meta(self) -> Dict[str, Any]:
        return {
            "code": self.objective_code,
            "description": self.objective_description,
            "priority_weights": self.priority_weights,
            "deadline_hours": self.deadline_hours,
            "objective_params": self.objective_params,
        }

    def _log(self, message: str) -> None:
        logger.info(message)
        self._debug.append(message)

    def set_objective(self, objective_code: str) -> None:
        self.objective = self._instantiate_objective(objective_code)
        self.objective_code = self.objective.code
        self.objective_description = self.objective.description
        self._log(f"Objective переключена на {self.objective_code}")

    def _build_assignment_payload(
        self,
        study: StudyData,
        doctor: DoctorData,
        start_dt: datetime,
        finish_dt: datetime,
        metrics: Dict[str, float],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "start_dt": start_dt,
            "finish_dt": finish_dt,
        }
        payload.update({key: float(value) for key, value in metrics.items()})
        payload.setdefault("objective_value", float(metrics.get("objective_value", 0.0)))
        payload.setdefault("tardiness_hours", 0.0)
        payload.setdefault(
            "weighted_tardiness",
            float(payload["tardiness_hours"]) * self.priority_weights.get(study.priority, 1.0),
        )
        return payload

    def _modality_ok(self, study_mods: Set[str], doctor_mods: Set[str]) -> bool:
        if not doctor_mods:
            return False
        if not study_mods:
            return True
        return bool(study_mods & doctor_mods)

    def _align_to_work_time(self, doctor: DoctorData, dt: datetime) -> datetime:
        return align_to_work_time(doctor, dt)

    def _planning_horizon_end(self, doctors: List[DoctorData]) -> datetime:
        return planning_horizon_end(doctors, self.now)

    def _add_work_minutes(self, doctor: DoctorData, start: datetime, minutes: float) -> datetime:
        return add_work_minutes(doctor, start, minutes)

    def _effective_start_after_prebook(
        self,
        doctor: DoctorData,
        prebooked_minutes: float = 0.0,
    ) -> datetime:
        return effective_start_after_prebook(doctor, self.now, prebooked_minutes)

    def _sync_planning_now(self, doctors: List[DoctorData]) -> None:
        self.now = self.real_now
        if not doctors:
            return

        min_shift_start = min(doctor.shift_start for doctor in doctors)
        if self.target_date != self.real_now.date():
            self.now = min_shift_start
            self._log(
                f"Целевая дата {self.target_date} не равна сегодняшней; "
                f"планирование начинается от {self.now}"
            )
            return

        if self.real_now < min_shift_start:
            self.now = min_shift_start
            self._log(
                f"Текущее время раньше начала смены; используем {self.now} как начало планирования"
            )
            return

        self._log(f"Планирование выполняется от реального текущего времени {self.now}")

    def load_studies(
        self,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[StudyData]:
        studies = load_studies_external(
            now=self.now,
            deadline_hours=self.deadline_hours,
            priority_weights=self.priority_weights,
            log=self._log,
            date_from=date_from,
            date_to=date_to,
        )
        studies.sort(key=lambda study: _study_sort_key(study, self.now, self.target_date))
        return studies

    def load_doctors(self) -> List[DoctorData]:
        return load_doctors_external(target_date=self.target_date, log=self._log)

    def _complete_unassigned_meta(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        assignment: Dict[str, int],
        partial_unassigned_meta: Dict[str, Dict[str, float | datetime]],
    ) -> Dict[str, Dict[str, float | datetime]]:
        horizon_end = self._planning_horizon_end(doctors)
        full_unassigned_meta = dict(partial_unassigned_meta)
        for study in studies:
            if study.research_number not in assignment and study.research_number not in full_unassigned_meta:
                full_unassigned_meta[study.research_number] = self.objective.unassigned_metrics(study, horizon_end)
        return full_unassigned_meta

    def _make_pass_doctors(
        self,
        doctors: List[DoctorData],
        used_up_by_doctor: Optional[Dict[int, float]] = None,
    ) -> List[DoctorData]:
        used_up_by_doctor = used_up_by_doctor or {}
        return [
            doctor.clone_with_remaining_up(doctor.max_up - float(used_up_by_doctor.get(doctor.id, 0.0)))
            for doctor in doctors
        ]

    def solve_priority_tier_multipass(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        *,
        use_mip: bool = True,
    ) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict[str, float | datetime]]]:
        priority_order = ["cito", "asap", "normal"]
        study_map = {study.research_number: study for study in studies}
        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}
        unassigned_meta: Dict[str, Dict[str, float | datetime]] = {}
        total_solver_obj = 0.0
        doctor_prebooked_minutes: Dict[int, float] = {doctor.id: 0.0 for doctor in doctors}
        doctor_used_up: Dict[int, float] = {doctor.id: 0.0 for doctor in doctors}

        for priority in priority_order:
            tier_studies = [study for study in studies if study.priority == priority]
            if not tier_studies:
                self._log(f"Multi-pass [{priority.upper()}]: исследований нет, проход пропущен")
                continue

            pass_doctors = self._make_pass_doctors(doctors, doctor_used_up)
            self._log(
                f"Multi-pass [{priority.upper()}]: старт прохода, studies={len(tier_studies)}, "
                f"already_booked_minutes={sum(doctor_prebooked_minutes.values()):.1f}, "
                f"already_used_up={sum(doctor_used_up.values()):.3f}"
            )

            if use_mip:
                pass_assignment, pass_details, pass_solver_obj, pass_unassigned_meta = self.solve_exact_mip(
                    tier_studies,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
            else:
                pass_assignment, pass_details = self.solve_greedy(
                    tier_studies,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
                horizon_end = self._planning_horizon_end(pass_doctors)
                pass_unassigned_meta = {
                    study.research_number: self.objective.unassigned_metrics(study, horizon_end)
                    for study in tier_studies
                    if study.research_number not in pass_assignment
                }
                pass_solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in pass_details.values())
                    + sum(float(item.get("objective_value", 0.0)) for item in pass_unassigned_meta.values())
                )

            total_solver_obj += float(pass_solver_obj)
            assignment.update(pass_assignment)
            details.update(pass_details)
            unassigned_meta.update(pass_unassigned_meta)

            for study_id, doctor_id in pass_assignment.items():
                study = study_map[study_id]
                doctor_prebooked_minutes[doctor_id] = doctor_prebooked_minutes.get(doctor_id, 0.0) + study.duration_minutes
                doctor_used_up[doctor_id] = doctor_used_up.get(doctor_id, 0.0) + study.up_value

            self._log(
                f"Multi-pass [{priority.upper()}]: назначено {len(pass_assignment)} / {len(tier_studies)}, "
                f"неназначено {len(pass_unassigned_meta)} / {len(tier_studies)}, "
                f"obj={float(pass_solver_obj):.6f}"
            )

        self._log(f"Multi-pass ИТОГО: назначено {len(assignment)} / {len(studies)}, obj_sum={float(total_solver_obj):.6f}")
        return assignment, details, float(total_solver_obj), unassigned_meta

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict]]:
        self._log(f"Запуск: жадный fallback (objective={self.objective_code})...")
        ordered = sorted(studies, key=lambda study: _study_sort_key(study, self.now, self.target_date))

        doctor_state: Dict[int, Dict[str, float | datetime]] = {}
        for doctor in doctors:
            prebooked = (doc_prebooked_minutes or {}).get(doctor.id, 0.0)
            doctor_state[doctor.id] = {
                "cursor": self._effective_start_after_prebook(doctor, prebooked),
                "used_up": 0.0,
            }

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}

        for study in ordered:
            best_choice: Optional[Tuple[Tuple[Any, ...], DoctorData, datetime, datetime, Dict[str, float]]] = None

            for doctor in doctors:
                state = doctor_state[doctor.id]
                if not self._modality_ok(study.modality, doctor.modality):
                    continue
                if float(state["used_up"]) + study.up_value > doctor.max_up + 1e-9:
                    continue

                start_dt = self._align_to_work_time(doctor, state["cursor"])
                finish_dt = self._add_work_minutes(doctor, start_dt, study.duration_minutes)
                if finish_dt > doctor.shift_end:
                    continue

                metrics = self.objective.option_metrics(study, doctor, start_dt, finish_dt)
                choice_key = (
                    float(metrics.get("objective_value", 0.0)),
                    finish_dt,
                    start_dt,
                    doctor.id,
                )
                choice = (choice_key, doctor, start_dt, finish_dt, metrics)
                if best_choice is None or choice_key < best_choice[0]:
                    best_choice = choice

            if best_choice is None:
                continue

            _, best_doctor, start_dt, finish_dt, metrics = best_choice
            assignment[study.research_number] = best_doctor.id
            details[study.research_number] = self._build_assignment_payload(
                study,
                best_doctor,
                start_dt,
                finish_dt,
                metrics,
            )
            doctor_state[best_doctor.id]["cursor"] = finish_dt
            doctor_state[best_doctor.id]["used_up"] = float(doctor_state[best_doctor.id]["used_up"]) + study.up_value

        self._log(f"Жадный fallback: назначено {len(assignment)} / {len(studies)}")
        return assignment, details

    def solve_exact_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict[str, float | datetime]]]:
        assignment, raw_details, solver_obj, unassigned_meta = solve_exact_mip_external(
            studies=studies,
            doctors=doctors,
            objective=self.objective,
            objective_code=self.objective_code,
            priority_weights=self.priority_weights,
            mip_time_limit=MIP_TIME_LIMIT,
            mip_gap_rel=MIP_GAP_REL,
            mip_threads=CBC_THREADS,
            planning_now=self.now,
            solve_greedy_fn=self.solve_greedy,
            planning_horizon_end_fn=self._planning_horizon_end,
            log=self._log,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

        details: Dict[str, Dict] = {}
        study_map = {study.research_number: study for study in studies}
        doctor_map = {doctor.id: doctor for doctor in doctors}

        for study_id, meta in raw_details.items():
            study = study_map[study_id]
            doctor = doctor_map[meta["doctor_id"]]
            metrics = {
                key: value
                for key, value in meta.items()
                if key not in {"doctor_id", "doctor_name", "start_dt", "finish_dt"}
            }
            details[study_id] = self._build_assignment_payload(
                study=study,
                doctor=doctor,
                start_dt=meta["start_dt"],
                finish_dt=meta["finish_dt"],
                metrics=metrics,
            )

        return assignment, details, solver_obj, unassigned_meta

    def save_to_db(self, assignment: Dict[str, int]) -> None:
        if self.preview_mode:
            self._log("Режим предпросмотра - сохранение пропущено")
            return
        if not assignment:
            self._log("Нет назначений для сохранения")
            return

        studies_by_number = Study.objects.in_bulk(list(assignment.keys()), field_name="research_number")
        to_update = []
        for research_number, doctor_id in assignment.items():
            study = studies_by_number.get(research_number)
            if study is None:
                continue
            study.diagnostician_id = doctor_id
            study.status = "confirmed"
            study.planned_at = self.now
            to_update.append(study)

        if to_update:
            Study.objects.bulk_update(to_update, ["diagnostician_id", "status", "planned_at"], batch_size=500)

    def distribute(
        self,
        use_mip: bool = True,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        self._log("=" * 60)
        self._log("OFFLINE DISTRIBUTION SERVICE")
        self._log(f"Время запроса: {self.real_now}")
        self._log(f"Целевая дата: {self.target_date}")
        self._log(f"Режим предпросмотра: {self.preview_mode}")
        self._log(f"Целевая функция: {self.objective_code} | {self.objective_description}")
        self._log(f"Параллельность CBC: threads={CBC_THREADS}")
        self._log("=" * 60)

        doctors = self.load_doctors()
        self._sync_planning_now(doctors)
        studies = self.load_studies(date_from=date_from, date_to=date_to)

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        if self.objective_code == PriorityTierTardinessMultiPassObjective.code:
            assignment, details, solver_obj, unassigned_meta = self.solve_priority_tier_multipass(
                studies,
                doctors,
                use_mip=use_mip,
            )
        elif use_mip:
            assignment, details, solver_obj, unassigned_meta = self.solve_exact_mip(studies, doctors)
        else:
            assignment, details = self.solve_greedy(studies, doctors)
            horizon_end = self._planning_horizon_end(doctors)
            unassigned_meta = {
                study.research_number: self.objective.unassigned_metrics(study, horizon_end)
                for study in studies
                if study.research_number not in assignment
            }
            solver_obj = (
                sum(float(item.get("objective_value", 0.0)) for item in details.values())
                + sum(float(item.get("objective_value", 0.0)) for item in unassigned_meta.values())
            )

        full_unassigned_meta = self._complete_unassigned_meta(studies, doctors, assignment, unassigned_meta)

        result = build_distribution_response(
            studies=studies,
            doctors=doctors,
            assignment=assignment,
            details=details,
            unassigned_meta=full_unassigned_meta,
            solver_obj=solver_obj,
            now=self.now,
            preview_mode=self.preview_mode,
            target_date_iso=self.target_date.isoformat(),
            objective_code=self.objective_code,
            objective_meta=self._objective_meta(),
            debug_log=self._debug,
        )

        self.save_to_db(assignment)
        summary = result["summary"]
        priority = result["priority_breakdown"]
        objective = result["objective"]

        self._log(
            f"Итого: назначено={summary['assigned']}/{len(studies)} "
            f"({summary['assignment_rate_percent']:.2f}%) | "
            f"CITO: {priority['cito']['assigned']}/{priority['cito']['total']} | "
            f"ASAP: {priority['asap']['assigned']}/{priority['asap']['total']} | "
            f"NORMAL: {priority['plan']['assigned']}/{priority['plan']['total']} | "
            f"Obj={objective['reported_objective_value']}"
        )

        self._log("Данные НЕ сохранены в БД (режим предпросмотра)" if self.preview_mode else "Данные сохранены в БД")
        return result

    def _empty(self, message: str, studies: Optional[List[StudyData]] = None) -> Dict[str, Any]:
        self._log(f"ПУСТО: {message}")
        return build_empty_distribution_response(
            message=message,
            studies_count=len(studies or []),
            objective_meta=self._objective_meta(),
            debug_log=self._debug,
        )
