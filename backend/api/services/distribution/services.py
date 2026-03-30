"""
Главный orchestration-сервис оффлайн-распределения исследований.

Модуль координирует работу остальных компонентов:
- загрузчиков данных;
- candidate pool builder;
- objective-стратегий;
- жадного и exact-решателей;
- builder-а итогового ответа.

Сам сервис не содержит всей вычислительной логики внутри себя, а
управляет последовательностью шагов и передаёт данные между модулями.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from django.utils import timezone
from api.models import Study

from .config import (
    DEADLINE_HOURS,
    MIP_GAP_REL,
    MIP_TIME_LIMIT,
    PRIORITY_WEIGHTS,
    SELECTION_PRIORITY_SCORES,
)
from .entities import DoctorData, StudyData
from .objectives import (
    OBJECTIVE_REGISTRY,
    ObjectiveStrategy,
    PriorityTierTardinessMultiPassObjective,
    WeightedTardinessLexicographicObjective,
)
from .pool import (
    build_candidate_pool as build_candidate_pool_external,
    build_multipass_candidate_pool as build_multipass_candidate_pool_external,
)
from .time_utils import (
    add_work_minutes,
    align_to_work_time,
    effective_start_after_prebook,
    execution_segments,
    occupied_slot_indices,
    planning_horizon_end,
    remaining_work_minutes,
    slot_boundaries,
)
from .exact_solver import solve_exact_mip as solve_exact_mip_external
from .result_builder import (
    build_distribution_response,
    build_empty_distribution_response,
)
from .loaders import (
    load_doctors as load_doctors_external,
    load_studies as load_studies_external,
)


logger = logging.getLogger(__name__)

class DistributionService:
    """
    Сервисный слой оффлайн-распределения исследований.

    Экземпляр класса хранит настройки текущего запуска:
    - целевую дату;
    - режим preview;
    - выбранную objective-стратегию;
    - веса приоритетов;
    - отладочный журнал.

    Основная задача класса — организовать полный сценарий распределения
    от загрузки данных до формирования финального ответа.
    """
    def __init__(
        self,
        target_date: Optional[datetime] = None,
        preview_mode: bool = False,
        objective: Optional[str] = None,
        priority_weights: Optional[Dict[str, float]] = None,
        selection_scores: Optional[Dict[str, float]] = None,
        deadline_hours: Optional[Dict[str, float]] = None,
        objective_params: Optional[Dict[str, Any]] = None,
    ):
        """
        Инициализировать сервис распределения.

        Параметры конструктора позволяют настроить:
        - дату расчёта;
        - preview-режим;
        - objective-функцию;
        - пользовательские веса и SLA;
        - дополнительные параметры objective.
        """
        self.now = timezone.now()
        self.target_date = target_date or self.now.date()
        self.preview_mode = preview_mode
        self.priority_weights = {**PRIORITY_WEIGHTS, **(priority_weights or {})}
        self.selection_scores = {**SELECTION_PRIORITY_SCORES, **(selection_scores or {})}
        self.deadline_hours = {**DEADLINE_HOURS, **(deadline_hours or {})}
        self.objective_params = dict(objective_params or {})
        self._debug: List[str] = []

        self.objective: ObjectiveStrategy
        self.objective_code = ""
        self.objective_description = ""
        # здесь можно поменять целевую функцию
        self.set_objective(objective or "weighted_tardiness_lexicographic")

    def set_preview_mode(self, preview: bool = True):
        """
        Включить или выключить режим предпросмотра.

        В preview-режиме распределение выполняется полностью, но результат
        не сохраняется в БД.
        """
        self.preview_mode = preview


    def _instantiate_objective(self, objective: str) -> ObjectiveStrategy:
        """
        Создать экземпляр objective-стратегии по её коду.

        Если код не найден в реестре, используется стратегия по умолчанию.
        """
        cls = OBJECTIVE_REGISTRY.get(objective, WeightedTardinessLexicographicObjective)
        return cls(
            priority_weights=self.priority_weights,
            selection_scores=self.selection_scores,
            **self.objective_params,
        )

    def _objective_meta(self) -> Dict[str, Any]:
        """Вернуть краткое описание текущей objective-функции для ответа API."""
        return {
            "code": self.objective_code,
            "description": self.objective_description,
            "priority_weights": self.priority_weights,
            "selection_scores": self.selection_scores,
            "deadline_hours": self.deadline_hours,
            "objective_params": self.objective_params,
        }

    def _log(self, msg: str):
        """
        Записать сообщение в системный лог и во внутренний debug-список.

        `_debug` затем отдаётся на фронт, чтобы можно было понимать, что именно
        происходило во время распределения.
        """
        logger.info(msg)
        self._debug.append(msg)

    def set_objective(self, objective: str) -> None:
        """Переключить objective-стратегию."""
        self.objective = self._instantiate_objective(objective)
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
        """
        Сформировать унифицированный payload назначения исследования.

        В payload включаются:
        - врач;
        - время старта и окончания;
        - selection score;
        - все рассчитанные solver-метрики.

        Используется как промежуточный формат между solver-слоем и builder-ом ответа.
        """
        payload: Dict[str, Any] = {
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "start_dt": start_dt,
            "finish_dt": finish_dt,
            "selection_priority_score": self.objective.selection_priority_score(study),
        }
        for key, value in metrics.items():
            payload[key] = float(value)
        payload.setdefault("objective_value", float(metrics.get("objective_value", 0.0)))
        payload.setdefault("tardiness_hours", 0.0)
        payload.setdefault(
            "weighted_tardiness",
            float(payload["tardiness_hours"]) * self.priority_weights.get(study.priority, 1.0),
        )
        return payload

    def _modality_ok(self, study_mods: Set[str], doc_mods: Set[str]) -> bool:
        """
        Проверить совместимость модальностей исследования и врача.

        Правило:
        - если у врача нет модальностей, он не подходит;
        - если у исследования модальность не указана, считаем его совместимым с
          любым врачом;
        - иначе нужен непустой intersection множеств модальностей.
        """
        if not doc_mods:
            return False
        if not study_mods:
            return True
        return bool(study_mods & doc_mods)

    def _align_to_work_time(self, doctor: DoctorData, dt: datetime) -> datetime:
        """
        Wrapper над time_utils.align_to_work_time.

        Нужен для единообразного доступа к временной логике из сервиса.
        """
        return align_to_work_time(doctor, dt)

    def _remaining_work_minutes(self, doctor: DoctorData, prebooked_minutes: float = 0.0) -> float:
        """
        Wrapper над time_utils.remaining_work_minutes.

        Возвращает остаток доступного рабочего времени врача на момент текущего расчёта.
        """
        return remaining_work_minutes(doctor, self.now, prebooked_minutes)

    def _planning_horizon_end(self, doctors: List[DoctorData]) -> datetime:
        """
        Wrapper над time_utils.planning_horizon_end.

        Используется для расчёта штрафов неназначенных исследований.
        """
        return planning_horizon_end(doctors, self.now)

    def _add_work_minutes(self, doctor: DoctorData, start: datetime, minutes: float) -> datetime:
        """
        Wrapper над time_utils.add_work_minutes.

        Используется при расчёте фактического времени завершения исследования.
        """
        return add_work_minutes(doctor, start, minutes)

    def _effective_start_after_prebook(self,
                                       doctor: DoctorData,
                                       prebooked_minutes: float = 0.0
                                    ) -> datetime:
        """
        Wrapper над time_utils.effective_start_after_prebook.

        Возвращает допустимый старт врача с учётом уже занятых минут.
        """
        return effective_start_after_prebook(doctor, self.now, prebooked_minutes)

    def _execution_segments(
        self,
        doctor: DoctorData,
        start: datetime,
        minutes: float,
    ) -> List[Tuple[datetime, datetime]]:
        """
        Wrapper над time_utils.execution_segments.

        Используется exact-решателем для построения занятых временных сегментов.
        """
        return execution_segments(doctor, start, minutes)

    def _slot_boundaries(
        self,
        doctor: DoctorData,
        prebooked_minutes: float = 0.0,
    ) -> List[datetime]:
        """
        Wrapper над time_utils.slot_boundaries.

        Возвращает допустимые стартовые слоты врача для exact MILP.
        """
        return slot_boundaries(doctor, self.now, prebooked_minutes)

    def _occupied_slot_indices(
        self,
        doctor: DoctorData,
        segments,
        slot_boundaries_list,
    ):
        """
        Wrapper над time_utils.occupied_slot_indices.

        Параметр врача сохраняется в сигнатуре для совместимости с exact solver,
        хотя в самом расчёте индексов слотов он напрямую не используется.
        """
        return occupied_slot_indices(segments, slot_boundaries_list)

    def load_studies(
        self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
    ) -> List[StudyData]:
        """
        Загрузить и нормализовать backlog исследований через внешний loader.

        Метод оставлен в сервисе как thin-wrapper, чтобы orchestration-слой
        не зависел от деталей ORM-преобразования.
        """
        return load_studies_external(
            now=self.now,
            deadline_hours=self.deadline_hours,
            log=self._log,
            date_from=date_from,
            date_to=date_to,
        )

    def load_doctors(self) -> List[DoctorData]:
        """
        Загрузить врачей с расписанием на целевую дату через внешний loader.

        Метод возвращает уже нормализованный список DoctorData.
        """
        return load_doctors_external(
            target_date=self.target_date,
            log=self._log,
        )

    def _candidate_priority_key(
        self,
        study: StudyData,
    ) -> Tuple[int, int, datetime, datetime]:
        """
        Построить ключ сортировки исследования для жадного fallback-режима.

        Ключ учитывает просроченность, приоритет, дедлайн и время создания.
        """
        overdue = study.deadline < self.now
        pr = {"cito": 0, "asap": 1, "normal": 2}.get(study.priority, 2)
        if overdue and study.priority == "cito":
            bucket = 0
        elif overdue and study.priority == "asap":
            bucket = 1
        elif overdue and study.priority == "normal":
            bucket = 2
        elif study.deadline.date() <= self.target_date:
            bucket = 3
        else:
            bucket = 4
        return (bucket, pr, study.deadline, study.created_at)


    def build_candidate_pool(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> List[StudyData]:
        """
        Построить shortlist исследований для обычного режима распределения.

        Метод делегирует основную работу модулю pool.py, передавая туда
        сервисные callback-и и параметры текущего запуска.
        """
        return build_candidate_pool_external(
            studies,
            doctors,
            now=self.now,
            target_date=self.target_date,
            modality_ok=self._modality_ok,
            remaining_work_minutes=self._remaining_work_minutes,
            log=self._log,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )


    def _make_pass_doctors(
        self,
        doctors: List[DoctorData],
        used_up_by_doctor: Optional[Dict[int, float]] = None,
    ) -> List[DoctorData]:
        """
        Построить временный список врачей для очередного прохода multi-pass.

        Важно: exact- и greedy-решатели уже умеют учитывать заранее занятое
        ВРЕМЯ через `doc_prebooked_minutes`, но не знают о ранее израсходованном
        УП. Поэтому для очередного прохода мы создаём копии врачей с уменьшенным
        `max_up`.

        Это позволяет решать задачу по приоритетам последовательно:
        - после CITO у врача остаётся меньше доступного УП;
        - этот остаток затем используется на проходе ASAP;
        - после него — на NORMAL.
        """
        used_up_by_doctor = used_up_by_doctor or {}
        result: List[DoctorData] = []

        for d in doctors:
            remaining_up = max(0.0, d.max_up - float(used_up_by_doctor.get(d.id, 0.0)))
            result.append(
                DoctorData(
                    id=d.id,
                    name=d.name,
                    modality=set(d.modality),
                    max_up=remaining_up,
                    shift_start=d.shift_start,
                    shift_end=d.shift_end,
                    break_start=d.break_start,
                    break_end=d.break_end,
                )
            )
        return result

    def _build_multipass_candidate_pool(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        priority: str,
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> List[StudyData]:
        """
        Построить candidate pool для одного приоритетного слоя multi-pass.

        Метод делегирует выбор shortlist внешнему модулю pool.py.
        """
        return build_multipass_candidate_pool_external(
            studies,
            doctors,
            priority=priority,
            now=self.now,
            target_date=self.target_date,
            modality_ok=self._modality_ok,
            remaining_work_minutes=self._remaining_work_minutes,
            log=self._log,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

    def solve_priority_tier_multipass(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        *,
        use_mip: bool = True,
    ) -> Tuple[
        Dict[str, int],
        Dict[str, Dict],
        float,
        Dict[str, Dict[str, float | datetime]],
        List[StudyData],
    ]:
        """
        Реальный multi-pass по приоритетам: CITO → ASAP → NORMAL.

        На каждом проходе:
        1. берутся только исследования текущего приоритета;
        2. учитываются уже занятые минуты врачей;
        3. учитывается уже израсходованный УП;
        4. запускается exact MILP (или greedy fallback) только для этой группы;
        5. выбранные назначения фиксируются и уменьшают доступные ресурсы для
           следующего прохода.

        Именно этого поведения раньше и не хватало классу
        `priority_tier_tardiness_multipass`: objective была объявлена как
        multi-pass, но реально решалась одной общей MILP-задачей.
        """
        priority_order = ["cito", "asap", "normal"]
        study_map = {s.research_number: s for s in studies}

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}
        unassigned_meta: Dict[str, Dict[str, float | datetime]] = {}
        total_solver_obj = 0.0
        multipass_pool: List[StudyData] = []

        doctor_prebooked_minutes: Dict[int, float] = {d.id: 0.0 for d in doctors}
        doctor_used_up: Dict[int, float] = {d.id: 0.0 for d in doctors}

        for priority in priority_order:
            tier_studies = [s for s in studies if s.priority == priority]
            if not tier_studies:
                self._log(f"Multi-pass [{priority.upper()}]: исследований нет, проход пропущен")
                continue

            pass_doctors = self._make_pass_doctors(doctors, doctor_used_up)
            tier_pool = self._build_multipass_candidate_pool(
                tier_studies,
                pass_doctors,
                priority,
                doc_prebooked_minutes=doctor_prebooked_minutes,
            )
            multipass_pool.extend(tier_pool)

            if not tier_pool:
                self._log(
                    f"Multi-pass [{priority.upper()}]: " +
                    "candidate pool пуст, назначений на этом проходе не будет"
                )
                continue

            self._log(
                f"Multi-pass [{priority.upper()}]: старт прохода, pool={len(tier_pool)}, "
                f"already_booked_minutes={sum(doctor_prebooked_minutes.values()):.1f}, "
                f"already_used_up={sum(doctor_used_up.values()):.3f}"
            )

            if use_mip:
                pass_assignment, pass_details, pass_solver_obj, pass_unassigned_meta = self.solve_exact_mip(
                    tier_pool,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
            else:
                pass_assignment, pass_details = self.solve_greedy(
                    tier_pool,
                    pass_doctors,
                    doc_prebooked_minutes=doctor_prebooked_minutes,
                )
                planning_horizon_end = self._planning_horizon_end(pass_doctors)
                pass_unassigned_meta = {
                    s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                    for s in tier_pool
                    if s.research_number not in pass_assignment
                }
                pass_solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in pass_details.values())
                    + sum(float(item.get(
                        "objective_value", 0.0)) for item in pass_unassigned_meta.values())
                )

            total_solver_obj += float(pass_solver_obj)
            assignment.update(pass_assignment)
            details.update(pass_details)
            unassigned_meta.update(pass_unassigned_meta)

            for sid, did in pass_assignment.items():
                study = study_map[sid]
                doctor_prebooked_minutes[
                    did
                ] = doctor_prebooked_minutes.get(did, 0.0) + study.duration_minutes
                doctor_used_up[did] = doctor_used_up.get(did, 0.0) + study.up_value

            self._log(
                f"Multi-pass [{priority.upper()}]: назначено {
                    len(pass_assignment)} / {len(tier_pool)}, "
                f"неназначено {len(pass_unassigned_meta)} / {
                    len(tier_pool)}, obj={float(pass_solver_obj):.6f}"
            )

        self._log(
            f"Multi-pass ИТОГО: назначено {len(assignment)} / {len(studies)}, "
            f"pool={len(multipass_pool)}, obj_sum={float(total_solver_obj):.6f}"
        )
        return assignment, details, float(total_solver_obj), unassigned_meta, multipass_pool

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict]]:
        """
        Распределить candidate pool жадным способом.

        Fallback теперь тоже учитывает текущую objective-стратегию: среди
        допустимых врачей выбирается тот вариант, у которого меньше
        objective_value, а при равенстве — более ранний finish_dt.
        """
        self._log(f"Запуск: жадный fallback по candidate pool (objective={self.objective_code})...")

        ordered = sorted(studies, key=self._candidate_priority_key)

        doctor_state: Dict[int, Dict[str, float | datetime]] = {}
        for d in doctors:
            prebooked = (doc_prebooked_minutes or {}).get(d.id, 0.0)
            doctor_state[d.id] = {
                "cursor": self._effective_start_after_prebook(d, prebooked),
                "used_up": 0.0,
            }

        assignment: Dict[str, int] = {}
        details: Dict[str, Dict] = {}

        for s in ordered:
            best_doctor: Optional[DoctorData] = None
            best_finish: Optional[datetime] = None
            best_metrics: Optional[Dict[str, float]] = None

            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if float(doctor_state[d.id]["used_up"]) + s.up_value > d.max_up + 1e-9:
                    continue

                start_dt = self._align_to_work_time(d, doctor_state[d.id]["cursor"])
                finish_dt = self._add_work_minutes(d, start_dt, s.duration_minutes)
                if finish_dt > d.shift_end:
                    continue

                metrics = self.objective.option_metrics(s, d, start_dt, finish_dt)
                objective_value = float(metrics.get("objective_value", 0.0))

                candidate_key = (objective_value, finish_dt, start_dt, d.id)
                best_key = None
                if best_doctor is not None and best_finish is not None and best_metrics is not None:
                    best_key = (
                        float(best_metrics.get("objective_value", 0.0)),
                        best_finish,
                        self._align_to_work_time(
                            best_doctor,
                            doctor_state[best_doctor.id]["cursor"]
                        ),
                        best_doctor.id,
                    )

                if best_key is None or candidate_key < best_key:
                    best_doctor = d
                    best_finish = finish_dt
                    best_metrics = metrics

            if best_doctor is None or best_finish is None or best_metrics is None:
                continue

            start_dt = self._align_to_work_time(best_doctor, doctor_state[best_doctor.id]["cursor"])
            finish_dt = self._add_work_minutes(best_doctor, start_dt, s.duration_minutes)
            metrics = self.objective.option_metrics(s, best_doctor, start_dt, finish_dt)

            assignment[s.research_number] = best_doctor.id
            details[s.research_number] = self._build_assignment_payload(
                s, best_doctor, start_dt, finish_dt, metrics
            )

            doctor_state[best_doctor.id]["cursor"] = finish_dt
            doctor_state[best_doctor.id]["used_up"] = float(
                doctor_state[best_doctor.id]["used_up"]
                ) + s.up_value

        self._log(f"Жадный fallback: назначено {len(assignment)} / {len(studies)}")
        return assignment, details

    def solve_exact_mip(
    self,
    studies: List[StudyData],
    doctors: List[DoctorData],
    doc_prebooked_minutes: Optional[Dict[int, float]] = None,
) -> Tuple[Dict[str, int], Dict[str, Dict], float, Dict[str, Dict[str, float | datetime]]]:
        """
        Выполнить exact-распределение через внешний MILP-решатель.

        Метод является thin-wrapper’ом:
        - вызывает exact_solver;
        - преобразует его выход в формат assignment payload;
        - возвращает унифицированный результат для сервисного слоя.
        """
        assignment, raw_details, solver_obj, unassigned_meta = solve_exact_mip_external(
            studies=studies,
            doctors=doctors,
            objective=self.objective,
            objective_code=self.objective_code,
            priority_weights=self.priority_weights,
            mip_time_limit=MIP_TIME_LIMIT,
            mip_gap_rel=MIP_GAP_REL,
            solve_greedy_fn=self.solve_greedy,
            planning_horizon_end_fn=self._planning_horizon_end,
            modality_ok=self._modality_ok,
            slot_boundaries_fn=self._slot_boundaries,
            add_work_minutes_fn=self._add_work_minutes,
            execution_segments_fn=self._execution_segments,
            occupied_slot_indices_fn=self._occupied_slot_indices,
            log=self._log,
            doc_prebooked_minutes=doc_prebooked_minutes,
        )

        details: Dict[str, Dict] = {}
        study_map = {s.research_number: s for s in studies}
        doctor_map = {d.id: d for d in doctors}

        for sid, meta in raw_details.items():
            study = study_map[sid]
            doctor = doctor_map[meta["doctor_id"]]
            metrics = {
                k: v
                for k, v in meta.items()
                if k not in {"doctor_id", "doctor_name", "start_dt", "finish_dt"}
            }
            details[sid] = self._build_assignment_payload(
                study=study,
                doctor=doctor,
                start_dt=meta["start_dt"],
                finish_dt=meta["finish_dt"],
                metrics=metrics,
            )

        return assignment, details, solver_obj, unassigned_meta

    def save_to_db(self, assignment: Dict[str, int]) -> None:
        """
        Сохранить результат распределения в БД.

        Если сервис запущен в preview-режиме, изменения не сохраняются.
        Иначе для каждого исследования выставляются:
        - diagnostician_id;
        - статус `confirmed`;
        - planned_at = self.now.
        """
        if self.preview_mode:
            self._log("Режим предпросмотра - сохранение пропущено")
            return

        for study_id, doc_id in assignment.items():
            Study.objects.filter(research_number=study_id).update(
                diagnostician_id=doc_id,
                status="confirmed",
                planned_at=self.now,
            )

    # ── Главный метод ────────────────────────────────────────────────

    def distribute(
        self,
        use_mip: bool = True,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Dict:
        """
        Выполнить полный цикл распределения и вернуть подробный результат.

        Основные этапы метода:
        1. Логирование параметров запуска.
        2. Загрузка врачей и исследований.
        3. Формирование candidate pool текущего дня.
        4. Решение exact MILP или greedy fallback.
        5. Построение агрегированных метрик и структуры ответа для UI.
        6. Сохранение результата в БД, если это не preview.

        Параметры:
        - use_mip: если False, exact MILP принудительно не используется,
          даже если доступен PuLP.
        - date_from / date_to: окно отбора исследований по created_at.
        """
        self._log("=" * 60)
        self._log("OFFLINE DISTRIBUTION SERVICE")
        self._log(f"Время: {self.now}")
        self._log(f"Целевая дата: {self.target_date}")
        self._log(f"Режим предпросмотра: {self.preview_mode}")
        self._log(
            f"Целевая функция: {self.objective_code} | {self.objective_description}"
        )
        self._log("=" * 60)

        doctors = self.load_doctors()

        # Если сервис запущен позже начала смены, в симуляции "сегодняшнего" дня
        # текущее время сдвигается к min_start. Это позволяет избежать ситуации,
        # когда весь утренний интервал автоматически считается потерянным просто
        # из-за времени запуска сервиса.
        if doctors:
            min_start = min(d.shift_start for d in doctors)
            if self.now > min_start:
                self._log(
                    f"Текущее время {self.now} после начала смены {min_start}, " +
                    "используем min_start как единое now для симуляции"
                )
                self.now = min_start

        studies = self.load_studies(date_from, date_to)

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        if self.objective_code == PriorityTierTardinessMultiPassObjective.code:
            assignment, details, solver_obj, unassigned_meta, candidate_pool = self.solve_priority_tier_multipass(
                studies,
                doctors,
                use_mip=use_mip,
            )
            if not candidate_pool:
                return self._empty(
                    "Не удалось сформировать candidate pool ни на одном проходе multi-pass",
                    studies
                )
        else:
            candidate_pool = self.build_candidate_pool(studies, doctors)
            if not candidate_pool:
                return self._empty(
                    "Не удалось сформировать candidate pool на текущий день", studies)

            if use_mip:
                assignment, details, solver_obj, unassigned_meta = self.solve_exact_mip(
                    candidate_pool,
                    doctors
                )
            else:
                assignment, details = self.solve_greedy(candidate_pool, doctors)
                planning_horizon_end = self._planning_horizon_end(doctors)
                unassigned_meta = {
                    s.research_number: self.objective.unassigned_metrics(s, planning_horizon_end)
                    for s in candidate_pool
                    if s.research_number not in assignment
                }
                solver_obj = (
                    sum(float(item.get("objective_value", 0.0)) for item in details.values())
                    + sum(float(
                        item.get("objective_value", 0.0)) for item in unassigned_meta.values())
                )

        result = build_distribution_response(
            studies=studies,
            doctors=doctors,
            assignment=assignment,
            details=details,
            unassigned_meta=unassigned_meta,
            candidate_pool=candidate_pool,
            solver_obj=solver_obj,
            now=self.now,
            preview_mode=self.preview_mode,
            target_date_iso=self.target_date.isoformat(),
            objective_code=self.objective_code,
            objective_meta=self._objective_meta(),
            debug_log=self._debug,
        )

        self.save_to_db(assignment)

        self._log(
            f"Итого: candidate_pool={result['candidate_pool_size']}/{len(studies)}, "
            f"назначено={result['assigned']}/{len(studies)} "
            f"({result['assignment_rate_percent']:.2f}%) | "
            f"CITO: {
                result['cito_assigned']}/{result['cito_total']} | "
            f"ASAP: {
                result['priority_breakdown']['asap']['assigned']}/{
                    result['priority_breakdown']['asap']['total']} | "
            f"NORMAL: {
                result['priority_breakdown']['plan']['assigned']}/{
                    result['priority_breakdown']['plan']['total']} | "
            f"Backlog вне candidate_pool: {result['backlog_outside_pool']} | "
            f"Obj={result['reported_objective_value']}"
        )

        if not self.preview_mode:
            self._log("Данные сохранены в БД")
        else:
            self._log("Данные НЕ сохранены в БД (режим предпросмотра)")

        return result

    def _empty(self, message: str, studies: List = None) -> Dict:
        """
        Сформировать пустой ответ сервиса.

        Используется в случаях, когда дальнейшее распределение невозможно:
        например, при отсутствии врачей, исследований или candidate pool.
        """
        self._log(f"ПУСТО: {message}")
        return build_empty_distribution_response(
            message=message,
            studies_count=len(studies or []),
            objective_meta=self._objective_meta(),
            debug_log=self._debug,
        )
