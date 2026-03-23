"""
Сервис оффлайн-распределения исследований по врачам.

Назначение модуля
-----------------
Этот файл реализует прикладной сервис, который берёт:
1. список нераспределённых исследований;
2. список врачей с расписанием на целевую дату;
3. правила приоритетов, дедлайнов, длительностей и ограничений по УП;
и возвращает результат распределения исследований между врачами.

Ключевая идея текущей версии
----------------------------
Текущая реализация использует ДВУХЭТАПНУЮ схему:

1) Из всего backlog формируется дневной shortlist.
   Это подмножество исследований, которое реально можно пытаться поставить
   в расписание текущего дня.

2) Для shortlist решается точная задача вида:

       MIN Z = Σ_i w_i * T_i,
       T_i = max(0, C_i - d_i)

   где:
   - w_i — вес исследования в зависимости от приоритета;
   - C_i — фактическое время завершения исследования;
   - d_i — дедлайн исследования;
   - T_i — просрочка в часах.

Важно понимать ограничения модели
---------------------------------
- Целевая функция Σ w_i T_i применяется ИМЕННО к shortlist текущего дня.
- Исследования, которые не попали в shortlist, остаются в очереди backlog и
  не штрафуются внутри objective текущего запуска.
- Для exact-модели используется time-indexed MILP: время дискретизируется
  слотами по 5 минут.
- Смена врача и перерыв учитываются явно: нельзя ставить исследование в слот,
  который пересекается с перерывом или выходит за пределы рабочей смены.

Fallback-логика
---------------
Если exact-режим по какой-то причине недоступен (например, не установлен PuLP,
нет допустимых стартов или solver завершился нештатно), сервис переходит на
жадный fallback. Жадная версия не гарантирует глобальный оптимум, но позволяет
получить практический результат и не сорвать распределение полностью.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from django.utils import timezone

from api.models import Schedule, Study

logger = logging.getLogger(__name__)


# ==============================================================================
# МАППИНГ МОДАЛЬНОСТЕЙ
# ==============================================================================
#
# В исходных данных модальность может быть записана по-разному:
# - русскими и латинскими сокращениями;
# - в разных регистрах;
# - в виде альтернативных кодов.
#
# Чтобы логика совместимости "врач ↔ исследование" работала корректно,
# мы приводим все варианты к единому внутреннему виду.
#

MODALITY_ALIASES: Dict[str, str] = {
    "KT": "CT",
    "КТ": "CT",
    "COMPUTED_TOMOGRAPHY": "CT",
    "MRT": "MRI",
    "МРТ": "MRI",
    "MAGNETIC_RESONANCE": "MRI",
    "RENTGEN": "XRAY",
    "РЕНТГЕН": "XRAY",
    "X_RAY": "XRAY",
    "US": "US",
    "УЗИ": "US",
    "ULTRASOUND": "US",
}


def normalize_modality(m: str) -> str:
    """
    Нормализовать обозначение модальности к единому внутреннему коду.

    Примеры:
    - "КТ" -> "CT"
    - "рентген" -> "XRAY"
    - "MRI" -> "MRI"

    Если значение пустое, возвращается "OTHER".
    Если значение неизвестно, возвращается его upper-case представление.
    """
    if not m:
        return "OTHER"
    return MODALITY_ALIASES.get(m.strip().upper(), m.strip().upper())



def parse_modalities(data) -> Set[str]:
    """
    Преобразовать поле модальности в множество нормализованных кодов.

    На вход может прийти:
    - список строк;
    - одна строка, где модальности разделены '/';
    - пустое значение.

    Возвращается множество, потому что:
    - дубли нам не нужны;
    - операции пересечения множеств удобны для проверки совместимости
      исследования и врача.
    """
    if not data:
        return set()
    items = data if isinstance(data, list) else str(data).split("/")
    return {normalize_modality(str(m)) for m in items if m and str(m).strip()}


# ==============================================================================
# КОНФИГУРАЦИЯ
# ==============================================================================
#
# Здесь сосредоточены базовые параметры модели:
# - веса приоритетов для objective;
# - SLA/дедлайны по приоритетам;
# - типовые длительности исследований по модальностям;
# - параметры exact MILP.
#
# Замечание: веса и дедлайны жёстко зашиты в коде. Если бизнес-правила
# изменятся, править нужно именно этот блок.
#

# Веса w_i в целевой функции Σ w_i T_i.
PRIORITY_WEIGHTS = {"cito": 36.0, "asap": 3.0, "normal": 1.0}

# Дедлайны d_i в часах от created_at.
DEADLINE_HOURS = {"cito": 2, "asap": 24, "normal": 72}

# Грубая длительность исследования в минутах по модальности.
# Используется как рабочая оценка для планирования времени врача.
MODALITY_DURATION_MINUTES = {
    "XRAY": 5,
    "CT": 15,
    "CT_CON": 25,
    "MRI": 20,
    "MRI_CON": 30,
    "MAMMO": 6,
    "FLUORO": 4,
    "ECG": 4,
    "HOLTER": 25,
    "EEG": 20,
    "US": 10,
}

# Размер временного слота exact-модели.
TIME_SLOT_MINUTES = 5

# Ограничения solver'а CBC.
MIP_TIME_LIMIT = 300
MIP_GAP_REL = 0.01


# ==============================================================================
# СТРУКТУРЫ ДАННЫХ
# ==============================================================================
#
# Вместо постоянной работы прямо с Django-моделями сервис сначала переводит
# данные в компактные dataclass-структуры. Это упрощает расчёты и делает код
# более предсказуемым.
#


@dataclass
class StudyData:
    """
    Внутреннее представление исследования для алгоритма распределения.

    Поля:
    - research_number: внешний идентификатор исследования;
    - priority: приоритет (`cito`, `asap`, `normal`);
    - created_at: время создания исследования;
    - modality: множество допустимых модальностей исследования;
    - up_value: УП исследования;
    - duration_minutes: оценка длительности исследования в минутах;
    - deadline: крайний допустимый срок завершения;
    - weight: вес исследования в objective.
    """

    research_number: str
    priority: str
    created_at: datetime
    modality: Set[str]
    up_value: float
    duration_minutes: float
    deadline: datetime
    weight: float

    @property
    def duration_hours(self) -> float:
        """Длительность исследования в часах."""
        return self.duration_minutes / 60.0


@dataclass
class DoctorData:
    """
    Внутреннее представление врача для алгоритма распределения.

    Поля:
    - modality: множество модальностей, по которым врач может работать;
    - max_up: суточный лимит УП;
    - shift_start / shift_end: границы смены;
    - break_start / break_end: границы перерыва, если он задан;
    - assigned_ids: список исследований, назначенных в рамках текущего запуска;
    - used_up: накопленный УП после распределения;
    - used_minutes: накопленное занятое время после распределения.
    """

    id: int
    name: str
    modality: Set[str]
    max_up: float
    shift_start: datetime
    shift_end: datetime
    break_start: Optional[datetime] = None
    break_end: Optional[datetime] = None
    assigned_ids: List[str] = field(default_factory=list)
    used_up: float = 0.0
    used_minutes: float = 0.0

    @property
    def break_minutes(self) -> float:
        """Длительность перерыва в минутах."""
        if self.break_start and self.break_end and self.break_end > self.break_start:
            return (self.break_end - self.break_start).total_seconds() / 60.0
        return 0.0

    @property
    def shift_hours(self) -> float:
        """
        Эффективная длительность смены в часах.

        Это не просто (shift_end - shift_start), а смена за вычетом перерыва.
        """
        gross = (self.shift_end - self.shift_start).total_seconds() / 3600.0
        return max(0.0, gross - self.break_minutes / 60.0)

    @property
    def free_up(self) -> float:
        """Оставшийся лимит УП после уже назначенных исследований."""
        return max(0.0, self.max_up - self.used_up)


@dataclass
class ScheduleOption:
    """
    Один допустимый вариант старта исследования в exact-модели.

    В универсальной версии опция хранит не только время старта/завершения, но и
    словарь вычисленных метрик. Это позволяет менять матмодель без переписывания
    всего сервиса: новая objective-функция может использовать любые метрики,
    посчитанные на уровне опции.

    Поля:
    - option_id: уникальный идентификатор бинарной переменной x_option_id;
    - study_idx: индекс исследования в shortlist;
    - doctor_idx: индекс врача в списке doctors;
    - start_dt / finish_dt: реальное время начала и завершения;
    - metrics: словарь производных характеристик опции;
    - objective_value: вклад этой опции в текущую objective;
    - occupied_slots: номера временных слотов врача, которые занимает опция.
    """

    option_id: int
    study_idx: int
    doctor_idx: int
    start_dt: datetime
    finish_dt: datetime
    metrics: Dict[str, float] = field(default_factory=dict)
    objective_value: float = 0.0
    occupied_slots: List[int] = field(default_factory=list)

    @property
    def tardiness_hours(self) -> float:
        """Просрочка опции в часах, если эта метрика рассчитана objective-стратегией."""
        return float(self.metrics.get("tardiness_hours", 0.0))

    @property
    def weighted_tardiness(self) -> float:
        """Взвешенная просрочка, если она присутствует среди метрик."""
        return float(self.metrics.get("weighted_tardiness", 0.0))


@dataclass
class MIPModelContext:
    """
    Контекст сборки MILP-модели.

    Мы передаём его в objective-стратегию, чтобы новая матмодель могла строить
    не только другую целевую функцию, но и свои дополнительные переменные и
    ограничения.
    """

    studies: List[StudyData]
    doctors: List[DoctorData]
    options: List[ScheduleOption]
    options_by_study: Dict[int, List[int]]
    options_by_doctor: Dict[int, List[int]]
    slot_boundaries_by_doctor: Dict[int, List[datetime]]


class ObjectiveStrategy(ABC):
    """Базовый интерфейс objective-функции для exact MILP и greedy fallback."""

    code: str = "base"
    description: str = "Base objective"

    def option_metrics(
        self,
        study: StudyData,
        doctor: DoctorData,
        start_dt: datetime,
        finish_dt: datetime,
    ) -> Dict[str, float]:
        """
        Посчитать метрики конкретной опции старта.

        Это место, где удобно вычислять всё, от чего потом может зависеть
        objective: просрочку, weighted tardiness, completion time, отклонения от
        дедлайна и т.д.
        """
        return {}

    @abstractmethod
    def build_objective(self, prob, x, ctx: MIPModelContext, pulp_module):
        """Построить выражение objective для MILP."""
        raise NotImplementedError

    def add_extra_constraints(self, prob, x, ctx: MIPModelContext, pulp_module) -> None:
        """
        Хук для дополнительных ограничений матмодели.

        Благодаря этому новая objective может оказаться не только другой целевой
        функцией, но и полноценной другой постановкой, если ей нужны свои
        переменные/ограничения.
        """
        return None

    def greedy_rank(
        self,
        study: StudyData,
        doctor: DoctorData,
        start_dt: datetime,
        finish_dt: datetime,
        metrics: Dict[str, float],
    ) -> Tuple:
        """
        Правило сравнения вариантов в greedy fallback.

        По умолчанию greedy старается минимизировать вклад в текущую objective.
        Это не делает greedy оптимальным, но хотя бы синхронизирует его с выбранной
        матмоделью.
        """
        return (float(metrics.get("objective_value", 0.0)), finish_dt, doctor.id)

    def assignment_payload(self, option: ScheduleOption, study: StudyData, doctor: DoctorData) -> Dict[str, Any]:
        """Метаданные назначения, которые попадут в details и ответ API."""
        return {
            "doctor_id": doctor.id,
            "doctor_name": doctor.name,
            "start_dt": option.start_dt,
            "finish_dt": option.finish_dt,
            "objective_value": option.objective_value,
            **option.metrics,
        }


class WeightedTardinessObjective(ObjectiveStrategy):
    code = "weighted_tardiness"
    description = "MIN Σ_i w_i * T_i"

    def option_metrics(self, study: StudyData, doctor: DoctorData, start_dt: datetime, finish_dt: datetime) -> Dict[str, float]:
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        weighted_tardiness = tardiness_hours * study.weight
        completion_hour = (finish_dt - study.created_at).total_seconds() / 3600.0
        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": weighted_tardiness,
            "completion_hours_from_created": completion_hour,
            "objective_value": weighted_tardiness,
        }

    def build_objective(self, prob, x, ctx: MIPModelContext, pulp_module):
        return pulp_module.lpSum(
            option.objective_value * x[option.option_id]
            for option in ctx.options
        )


class MinCompletionTimeObjective(ObjectiveStrategy):
    code = "min_completion_time"
    description = "MIN Σ_i C_i (в часах от created_at)"

    def option_metrics(self, study: StudyData, doctor: DoctorData, start_dt: datetime, finish_dt: datetime) -> Dict[str, float]:
        tardiness_hours = max(0.0, (finish_dt - study.deadline).total_seconds() / 3600.0)
        completion_hour = (finish_dt - study.created_at).total_seconds() / 3600.0
        return {
            "tardiness_hours": tardiness_hours,
            "weighted_tardiness": tardiness_hours * study.weight,
            "completion_hours_from_created": completion_hour,
            "objective_value": completion_hour,
        }

    def build_objective(self, prob, x, ctx: MIPModelContext, pulp_module):
        return pulp_module.lpSum(
            option.objective_value * x[option.option_id]
            for option in ctx.options
        )

class TardinessObjective(ObjectiveStrategy):
    code = "tardiness"
    description = "MIN Σ_i T_i, где T_i = max(0, C_i - d_i)"

    def option_metrics(self, study, doctor, start_dt, finish_dt):
        tardiness_hours = max(
            0.0,
            (finish_dt - study.deadline).total_seconds() / 3600.0
        )
        completion_hour = (finish_dt - study.created_at).total_seconds() / 3600.0

        return {
            "tardiness_hours": tardiness_hours,
            "completion_hours_from_created": completion_hour,
            "objective_value": tardiness_hours,
        }

    def build_objective(self, prob, x, ctx, pulp_module):
        return pulp_module.lpSum(
            option.objective_value * x[option.option_id]
            for option in ctx.options
        )


class DistributionService:
    """
    Главный сервис оффлайн-распределения исследований.

    Общий сценарий работы:
    1. Загружаем врачей с расписанием на target_date.
    2. Загружаем неназначенные исследования из backlog.
    3. Формируем shortlist на текущий день.
    4. Пытаемся решить exact MILP для shortlist.
    5. Если exact-режим недоступен — используем greedy fallback.
    6. Собираем подробный ответ для UI и, при необходимости, сохраняем результат.
    """

    def __init__(
        self,
        target_date: Optional[datetime] = None,
        preview_mode: bool = False,
        objective: Optional[str] = None,
    ):
        """
        Инициализация сервиса.

        Параметры:
        - target_date: дата, на которую строится распределение;
        - preview_mode: если True, результат не записывается в БД;
        - objective: код objective-стратегии.

        ВАЖНО: теперь objective действительно влияет на построение модели.
        Чтобы добавить совсем другую матмодель, достаточно зарегистрировать
        новую стратегию в `_build_objective_registry`.
        """
        self.now = timezone.now()
        self.target_date = target_date or self.now.date()
        self.preview_mode = preview_mode
        self._objective_registry = self._build_objective_registry()
        self.objective: ObjectiveStrategy = self._objective_registry.get(
            objective or "weighted_tardiness",
            self._objective_registry["weighted_tardiness"],
        )
        self.objective_code = self.objective.code
        self.objective_description = self.objective.description
        self._debug: List[str] = []

    def set_preview_mode(self, preview: bool = True):
        """Включить или выключить режим предпросмотра."""
        self.preview_mode = preview

    def _build_objective_registry(self) -> Dict[str, ObjectiveStrategy]:
        """Реестр доступных objective-стратегий."""
        strategies: List[ObjectiveStrategy] = [
            WeightedTardinessObjective(),
            MinCompletionTimeObjective(),
            TardinessObjective(),
        ]
        return {strategy.code: strategy for strategy in strategies}

    def _objective_meta(self) -> Dict[str, str]:
        """Вернуть краткое описание текущей objective-функции для ответа API."""
        return {
            "code": self.objective_code,
            "description": self.objective_description,
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
        """
        Сменить objective-функцию на одну из зарегистрированных стратегий.

        Примеры:
        - `weighted_tardiness`
        - `min_completion_time`
        - `tardiness`
        """
        strategy = self._objective_registry.get(objective)
        if strategy is None:
            available = ", ".join(sorted(self._objective_registry))
            raise ValueError(
                f"Неизвестная objective '{objective}'. Доступно: {available}"
            )

        self.objective = strategy
        self.objective_code = strategy.code
        self.objective_description = strategy.description
        self._log(f"Целевая функция переключена на: {self.objective_code}")

    def _make_aware(self, dt: Optional[datetime]) -> Optional[datetime]:
        """
        Привести datetime к timezone-aware формату.

        В Django легко столкнуться со смешением aware и naive datetime.
        Для расчётов это критично, поэтому здесь приводим значения к единому виду.
        """
        if dt is None:
            return None
        return dt if timezone.is_aware(dt) else timezone.make_aware(dt)

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
        Сдвинуть момент времени к допустимому рабочему времени врача.

        Что делает метод:
        - если время раньше начала смены, переносит его на shift_start;
        - если время попало в перерыв, переносит его на конец перерыва.

        Это базовый helper, который используется почти во всех расчётах времени.
        """
        if dt < doctor.shift_start:
            dt = doctor.shift_start
        if (
            doctor.break_start
            and doctor.break_end
            and doctor.break_start <= dt < doctor.break_end
        ):
            dt = doctor.break_end
        return dt

    def _work_minutes_between(
        self, doctor: DoctorData, start: datetime, end: datetime
    ) -> float:
        """
        Посчитать, сколько рабочих минут врача содержится в интервале [start, end].

        При этом:
        - интервалы за пределами смены отсекаются;
        - время, попадающее в перерыв, вычитается.

        Метод нужен в первую очередь для грубой оценки доступной мощности врача.
        """
        start = max(start, doctor.shift_start)
        end = min(end, doctor.shift_end)
        if end <= start:
            return 0.0

        total = (end - start).total_seconds() / 60.0
        if doctor.break_start and doctor.break_end:
            ov_start = max(start, doctor.break_start)
            ov_end = min(end, doctor.break_end)
            if ov_end > ov_start:
                total -= (ov_end - ov_start).total_seconds() / 60.0
        return max(0.0, total)

    def _remaining_work_minutes(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> float:
        """
        Оценить, сколько рабочих минут у врача осталось доступными.

        `prebooked_minutes` — это уже занятое или заранее зарезервированное время,
        которое нужно учитывать до начала нового распределения.
        """
        effective_start = self._effective_start_after_prebook(doctor, prebooked_minutes)
        available = self._work_minutes_between(doctor, effective_start, doctor.shift_end)
        return max(0.0, available)

    def _add_work_minutes(
        self, doctor: DoctorData, start: datetime, minutes: float
    ) -> datetime:
        """
        Добавить к моменту `start` указанное количество РАБОЧИХ минут врача.

        Это один из самых важных методов во всём сервисе.
        Он не просто делает `start + timedelta(minutes=...)`, а двигается по
        реальному календарю врача:
        - учитывает начало смены;
        - пропускает перерыв;
        - не считает нерабочие интервалы;
        - если минут больше, чем осталось в смене, возвращает момент уже за её
          пределами.

        Именно этот helper позволяет корректно вычислять фактическое `finish_dt`
        и, следовательно, точное `C_i` в objective Σ w_i T_i.
        """
        remaining = max(0.0, float(minutes))
        current = self._align_to_work_time(doctor, start)

        while remaining > 1e-9:
            current = self._align_to_work_time(doctor, current)

            if current >= doctor.shift_end:
                return current + timedelta(minutes=remaining)

            next_stop = doctor.shift_end
            if doctor.break_start and doctor.break_end and current < doctor.break_start:
                next_stop = min(next_stop, doctor.break_start)

            available = max(0.0, (next_stop - current).total_seconds() / 60.0)

            if remaining <= available + 1e-9:
                return current + timedelta(minutes=remaining)

            remaining -= available
            current = next_stop

            if (
                doctor.break_start
                and doctor.break_end
                and current == doctor.break_start
            ):
                current = doctor.break_end

        return current

    def _effective_start_after_prebook(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> datetime:
        """
        Посчитать фактический старт врача с учётом already booked времени.

        В качестве базовой точки берётся максимум из:
        - начала смены;
        - текущего времени `self.now`.

        После этого к базовой точке добавляются заранее занятые рабочие минуты.
        """
        base = max(doctor.shift_start, self.now)
        return self._add_work_minutes(doctor, base, prebooked_minutes)

    def _round_up_to_slot(self, dt: datetime) -> datetime:
        """
        Округлить время вверх до ближайшей границы временного слота.

        Exact MILP дискретизирует время слотами по TIME_SLOT_MINUTES.
        Поэтому все допустимые старты должны лежать на этих границах.
        """
        minute = dt.minute
        remainder = minute % TIME_SLOT_MINUTES
        if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
            return dt.replace(second=0, microsecond=0)
        delta = TIME_SLOT_MINUTES - remainder if remainder else 0
        rounded = dt + timedelta(minutes=delta)
        return rounded.replace(second=0, microsecond=0)

    def _execution_segments(
        self, doctor: DoctorData, start: datetime, minutes: float
    ) -> List[Tuple[datetime, datetime]]:
        """
        Разбить выполнение исследования на рабочие сегменты.

        Зачем это нужно:
        если исследование началось до перерыва и заканчивается после перерыва,
        его исполнение состоит из двух сегментов. Exact-модель должна понимать,
        какие временные слоты действительно заняты этим исследованием.

        Результат — список интервалов `(segment_start, segment_end)`.
        """
        remaining = max(0.0, float(minutes))
        current = self._align_to_work_time(doctor, start)
        segments: List[Tuple[datetime, datetime]] = []

        while remaining > 1e-9 and current < doctor.shift_end:
            current = self._align_to_work_time(doctor, current)
            if current >= doctor.shift_end:
                break

            next_stop = doctor.shift_end
            if doctor.break_start and doctor.break_end and current < doctor.break_start:
                next_stop = min(next_stop, doctor.break_start)

            available = max(0.0, (next_stop - current).total_seconds() / 60.0)
            chunk = min(remaining, available)
            if chunk > 1e-9:
                seg_end = current + timedelta(minutes=chunk)
                segments.append((current, seg_end))
                remaining -= chunk
                current = seg_end
            else:
                current = next_stop

            if (
                doctor.break_start
                and doctor.break_end
                and current == doctor.break_start
            ):
                current = doctor.break_end

        return segments

    def _slot_boundaries(
        self, doctor: DoctorData, prebooked_minutes: float = 0.0
    ) -> List[datetime]:
        """
        Сгенерировать все допустимые начала временных слотов для врача.

        Важно:
        - стартуем не раньше эффективного доступного времени врача;
        - пропускаем перерыв;
        - не выходим за пределы смены.

        Это основа для построения exact MILP: каждый слот становится кандидатом
        на старт исследования.
        """
        start = self._round_up_to_slot(
            self._effective_start_after_prebook(doctor, prebooked_minutes)
        )
        slots: List[datetime] = []
        current = start
        while current < doctor.shift_end:
            if (
                doctor.break_start
                and doctor.break_end
                and doctor.break_start <= current < doctor.break_end
            ):
                current = self._round_up_to_slot(doctor.break_end)
                continue
            slots.append(current)
            current += timedelta(minutes=TIME_SLOT_MINUTES)
        return slots

    def _occupied_slot_indices(
        self,
        doctor: DoctorData,
        segments: List[Tuple[datetime, datetime]],
        slot_boundaries: List[datetime],
    ) -> List[int]:
        """
        Найти индексы временных слотов, которые занимает исследование.

        Exact-модели нужно ограничение вида:
        "в один и тот же слот у врача не может стоять больше одного исследования".

        Поэтому для каждой опции старта мы заранее вычисляем, какие именно слоты
        она занимает.
        """
        occupied: List[int] = []
        for idx, slot_start in enumerate(slot_boundaries):
            slot_end = slot_start + timedelta(minutes=TIME_SLOT_MINUTES)
            if any(
                seg_start < slot_end and slot_start < seg_end
                for seg_start, seg_end in segments
            ):
                occupied.append(idx)
        return occupied

    # ── Загрузка данных ──────────────────────────────────────────────

    def _get_duration(self, study: Study) -> float:
        """
        Оценить длительность исследования в минутах.

        Если у исследования известна модальность study_type, длительность берётся
        из конфигурационного словаря `MODALITY_DURATION_MINUTES`.
        Иначе используется значение по умолчанию 15 минут.
        """
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return float(MODALITY_DURATION_MINUTES.get(mod, 15))
        return 15.0

    def _get_up(self, study: Study) -> float:
        """
        Получить УП исследования.

        Приоритет источников:
        1. Явное значение `study.study_type.up_value`, если оно есть.
        2. Грубая оценка по модальности.
        3. Значение по умолчанию 0.25.
        """
        if study.study_type and study.study_type.up_value:
            return float(study.study_type.up_value)
        if study.study_type:
            mod = normalize_modality(study.study_type.modality or "")
            return {"XRAY": 0.083, "CT": 0.25, "MRI": 0.333, "US": 0.10}.get(mod, 0.25)
        return 0.25

    def load_studies(
        self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None
    ) -> List[StudyData]:
        """
        Загрузить все неназначенные исследования, которые можно рассматривать
        для распределения.

        Фильтрация:
        - берём только исследования без diagnostician;
        - опционально ограничиваем backlog временным окном `created_at`.

        На выходе Django-модели преобразуются в `StudyData`.
        Здесь же рассчитываются:
        - приоритет;
        - дедлайн;
        - вес исследования.
        """
        qs = Study.objects.filter(diagnostician__isnull=True).select_related("study_type")

        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lt=date_to)

        result: List[StudyData] = []
        for s in qs:
            priority = (s.priority or "normal").strip().lower()
            if priority not in PRIORITY_WEIGHTS:
                priority = "normal"

            created = self._make_aware(s.created_at) or self.now
            deadline = created + timedelta(hours=DEADLINE_HOURS.get(priority, 72))
            weight = PRIORITY_WEIGHTS.get(priority, 1.0)

            result.append(
                StudyData(
                    research_number=s.research_number,
                    priority=priority,
                    created_at=created,
                    modality=parse_modalities(
                        s.study_type.modality if s.study_type else ""
                    ),
                    up_value=self._get_up(s),
                    duration_minutes=self._get_duration(s),
                    deadline=deadline,
                    weight=weight,
                )
            )

        self._log(f"Исследований без назначения: {len(result)}")
        for s in result[:3]:
            self._log(
                f"  Пример: research_number={s.research_number}, priority={s.priority}, "
                f"modality={s.modality}, up={s.up_value}, dur={s.duration_minutes}мин"
            )
        return result

    def load_doctors(self) -> List[DoctorData]:
        """
        Загрузить врачей, у которых есть рабочее расписание на target_date.

        Что здесь происходит:
        - выбираются записи Schedule на целевую дату;
        - отбрасываются выходные и неактивные врачи;
        - формируются интервалы смены и перерыва;
        - модальности врача приводятся к нормализованному множеству.
        """
        target = self.target_date
        schedules = Schedule.objects.filter(
            work_date=target, is_day_off=0
        ).select_related("doctor")

        self._log(f"Расписаний на {target}: {schedules.count()}")

        result: List[DoctorData] = []
        for sch in schedules:
            doc = sch.doctor
            if not doc or not doc.is_active:
                self._log(
                    f"  Пропуск: врач {getattr(doc, 'id', '?')}, active={getattr(doc, 'is_active', '?')}"
                )
                continue

            max_up = float(doc.max_up_per_day or 50)

            if sch.time_start and sch.time_end:
                s_start = timezone.make_aware(datetime.combine(target, sch.time_start))
                s_end = timezone.make_aware(datetime.combine(target, sch.time_end))
            else:
                # Если в расписании время смены не задано, используем разумный дефолт.
                s_start = self.now.replace(hour=9, minute=0, second=0, microsecond=0)
                s_end = self.now.replace(hour=17, minute=0, second=0, microsecond=0)

            b_start = (
                timezone.make_aware(datetime.combine(target, sch.break_start))
                if sch.break_start
                else None
            )
            b_end = (
                timezone.make_aware(datetime.combine(target, sch.break_end))
                if sch.break_end
                else None
            )

            break_h = (
                (b_end - b_start).total_seconds() / 3600.0 if b_start and b_end else 0.0
            )
            shift_h = (s_end - s_start).total_seconds() / 3600.0
            mods = parse_modalities(doc.modality)

            self._log(
                f"  Врач {doc.fio_alias} (id={doc.id}): "
                f"max_up={max_up}, смена={shift_h:.1f}ч, "
                f"перерыв={break_h * 60:.0f}мин, эфф.время={shift_h - break_h:.1f}ч, мод={list(mods)}"
            )

            result.append(
                DoctorData(
                    id=doc.id,
                    name=doc.fio_alias or f"Врач {doc.id}",
                    modality=mods,
                    max_up=max_up,
                    shift_start=s_start,
                    shift_end=s_end,
                    break_start=b_start,
                    break_end=b_end,
                )
            )

        self._log(f"Врачей загружено: {len(result)}")
        return result

    # ── Shortlist на день ───────────────────────────────────────────

    def _shortlist_priority_key(self, study: StudyData) -> Tuple:
        """
        Построить ключ сортировки исследования для формирования shortlist.

        Логика bucket'ов:
        0 - просроченные CITO;
        1 - просроченные ASAP;
        2 - просроченные NORMAL;
        3 - исследования, чей дедлайн наступает не позже target_date;
        4 - остальные.

        Далее внутри bucket используется приоритет и более ранние сроки.
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

    def build_daily_pool(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> List[StudyData]:
        """
        Построить shortlist исследований на текущий день.

        Это НЕ окончательное расписание и НЕ точная оптимизация.
        Здесь решается более грубая задача: выбрать из backlog такой пул
        исследований, который вообще имеет шанс поместиться в доступную дневную
        мощность врачей.

        Логика:
        - исследования сортируются по приоритетному ключу;
        - для каждого исследования ищутся врачи, у которых хватает и УП, и минут;
        - если кандидаты есть, исследование попадает в shortlist, а доступный
          ресурс выбранного врача уменьшается.

        Важно:
        выбранный здесь врач не является окончательным назначением. Мы используем
        его лишь как способ оценить, что shortlist в целом реалистичен по ресурсам.
        """
        ordered = sorted(studies, key=self._shortlist_priority_key)

        remaining_up = {d.id: d.max_up for d in doctors}
        remaining_minutes = {
            d.id: self._remaining_work_minutes(d, (doc_prebooked_minutes or {}).get(d.id, 0.0))
            for d in doctors
        }

        selected: List[StudyData] = []

        for s in ordered:
            candidates = []
            for d in doctors:
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if remaining_up[d.id] + 1e-9 < s.up_value:
                    continue
                if remaining_minutes[d.id] + 1e-9 < s.duration_minutes:
                    continue

                # Чем больше запас по времени и УП после помещения исследования,
                # тем предпочтительнее врач для грубой shortlist-оценки.
                score = (
                    remaining_minutes[d.id] - s.duration_minutes,
                    remaining_up[d.id] - s.up_value,
                )
                candidates.append((score, d.id))

            if not candidates:
                continue

            candidates.sort(reverse=True)
            chosen_doc_id = candidates[0][1]
            remaining_up[chosen_doc_id] -= s.up_value
            remaining_minutes[chosen_doc_id] -= s.duration_minutes
            selected.append(s)

        self._log(
            f"Shortlist на текущий день: {len(selected)} из {len(studies)} исследований"
        )
        return selected

    # ── Жадный fallback ─────────────────────────────────────────────

    def solve_greedy(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict]]:
        """
        Распределить shortlist жадным способом.

        Это fallback-алгоритм, который используется, если exact MILP недоступен
        или не дал пригодного решения.

        Идея:
        - исследования обрабатываются в порядке shortlist-приоритета;
        - для каждого исследования ищется врач, у которого самый ранний finish_dt;
        - если подходящий врач найден, исследование фиксируется за ним.

        Возвращает:
        - assignment: mapping research_number -> doctor_id;
        - details: подробные метаданные по каждому назначенному исследованию.
        """
        self._log("Запуск: жадный fallback по shortlist...")

        ordered = sorted(studies, key=self._shortlist_priority_key)

        # Для каждого врача храним текущее положение "курсора времени" и уже
        # использованный УП в рамках жадного распределения.
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
            best = None
            best_finish = None

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
                rank = self.objective.greedy_rank(s, d, start_dt, finish_dt, metrics)

                # Жадное правило теперь согласовано с выбранной objective.
                if best is None or rank < best_finish:
                    best = (d, metrics)
                    best_finish = rank

            if best is None:
                continue

            best_doctor, best_metrics = best
            start_dt = self._align_to_work_time(best_doctor, doctor_state[best_doctor.id]["cursor"])
            finish_dt = self._add_work_minutes(best_doctor, start_dt, s.duration_minutes)
            option = ScheduleOption(
                option_id=-1,
                study_idx=-1,
                doctor_idx=-1,
                start_dt=start_dt,
                finish_dt=finish_dt,
                metrics=best_metrics,
                objective_value=float(best_metrics.get("objective_value", 0.0)),
                occupied_slots=[],
            )

            assignment[s.research_number] = best_doctor.id
            details[s.research_number] = self.objective.assignment_payload(option, s, best_doctor)

            doctor_state[best_doctor.id]["cursor"] = finish_dt
            doctor_state[best_doctor.id]["used_up"] = float(doctor_state[best_doctor.id]["used_up"]) + s.up_value

        self._log(f"Жадный fallback: назначено {len(assignment)} / {len(studies)}")
        return assignment, details

    # ── Exact MILP: MIN Σ w_i T_i ───────────────────────────────────

    def _build_exact_options(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[List[ScheduleOption], Dict[int, List[int]], Dict[int, List[int]], Dict[int, List[datetime]]]:
        """
        Построить все допустимые опции старта для exact MILP.

        Для каждой пары (исследование, врач) генерируются допустимые моменты
        старта по сетке временных слотов. Для каждого такого старта рассчитываются:
        - реальное время завершения finish_dt;
        - просрочка tardiness_hours;
        - вклад в objective weighted_tardiness;
        - список занятых временных слотов occupied_slots.

        Возвращаются:
        - список всех опций;
        - mapping study_idx -> список option_id;
        - mapping doctor_idx -> список option_id;
        - mapping doctor_idx -> границы слотов по времени.
        """
        options: List[ScheduleOption] = []
        options_by_study: Dict[int, List[int]] = {i: [] for i in range(len(studies))}
        options_by_doctor: Dict[int, List[int]] = {j: [] for j in range(len(doctors))}
        slot_boundaries_by_doctor: Dict[int, List[datetime]] = {}

        option_id = 0
        for j, d in enumerate(doctors):
            prebooked = (doc_prebooked_minutes or {}).get(d.id, 0.0)
            slot_boundaries = self._slot_boundaries(d, prebooked)
            slot_boundaries_by_doctor[j] = slot_boundaries

            if not slot_boundaries:
                continue

            for i, s in enumerate(studies):
                if not self._modality_ok(s.modality, d.modality):
                    continue
                if s.up_value > d.max_up + 1e-9:
                    continue

                for start_dt in slot_boundaries:
                    finish_dt = self._add_work_minutes(d, start_dt, s.duration_minutes)
                    if finish_dt > d.shift_end:
                        continue

                    segments = self._execution_segments(d, start_dt, s.duration_minutes)
                    occupied_slots = self._occupied_slot_indices(d, segments, slot_boundaries)
                    if not occupied_slots:
                        continue

                    metrics = self.objective.option_metrics(s, d, start_dt, finish_dt)

                    option = ScheduleOption(
                        option_id=option_id,
                        study_idx=i,
                        doctor_idx=j,
                        start_dt=start_dt,
                        finish_dt=finish_dt,
                        metrics=metrics,
                        objective_value=float(metrics.get("objective_value", 0.0)),
                        occupied_slots=occupied_slots,
                    )
                    options.append(option)
                    options_by_study[i].append(option_id)
                    options_by_doctor[j].append(option_id)
                    option_id += 1

        return options, options_by_study, options_by_doctor, slot_boundaries_by_doctor

    def solve_exact_mip(
        self,
        studies: List[StudyData],
        doctors: List[DoctorData],
        doc_prebooked_minutes: Optional[Dict[int, float]] = None,
    ) -> Tuple[Dict[str, int], Dict[str, Dict], float]:
        """
        Решить точную задачу распределения shortlist через MILP.

        В универсальной версии exact MILP сам по себе остаётся тем же по
        структуре (assignment + временные слоты + ограничения по УП), но
        целевая функция и её дополнительные ограничения делегируются выбранной
        objective-стратегии.

        Благодаря этому можно подставлять другие матмодели, не переписывая
        базовый сервис распределения.
        """
        try:
            import pulp
        except ImportError:
            self._log("PuLP не установлен → используем жадный fallback")
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
            return assignment, details, float(solver_obj)

        self._log(f"Exact MILP: shortlist={len(studies)}, doctors={len(doctors)}")

        options, options_by_study, options_by_doctor, slot_boundaries_by_doctor = self._build_exact_options(
            studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
        )

        self._log(f"  Кандидатных стартов: {len(options)}")
        if not options:
            self._log("  Нет допустимых стартов → жадный fallback")
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
            return assignment, details, float(solver_obj)

        # Если для какого-то исследования из shortlist вообще нет допустимых опций,
        # exact-модель для всего shortlist становится неудобной/невыполнимой.
        # В таком случае переходим на жадную схему.
        infeasible_studies = [i for i, ids in options_by_study.items() if not ids]
        if infeasible_studies:
            self._log(
                f"  В shortlist попали исследования без допустимых стартов: {len(infeasible_studies)} → жадный fallback"
            )
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
            return assignment, details, float(solver_obj)

        prob = pulp.LpProblem(f"Exact_{self.objective_code}", pulp.LpMinimize)
        x = {
            option.option_id: pulp.LpVariable(f"x_{option.option_id}", cat="Binary")
            for option in options
        }

        ctx = MIPModelContext(
            studies=studies,
            doctors=doctors,
            options=options,
            options_by_study=options_by_study,
            options_by_doctor=options_by_doctor,
            slot_boundaries_by_doctor=slot_boundaries_by_doctor,
        )

        # Целевая функция строится выбранной стратегией.
        prob += self.objective.build_objective(prob, x, ctx, pulp), "Obj"

        # Каждое исследование из shortlist должно быть назначено ровно один раз.
        for study_idx, option_ids in options_by_study.items():
            prob += (
                pulp.lpSum(x[oid] for oid in option_ids) == 1,
                f"Study_{study_idx}",
            )

        # В один момент времени у врача не более одного исследования.
        # Реализуется через ограничения по занятым временным слотам.
        options_by_id = {option.option_id: option for option in options}
        for doctor_idx, slot_boundaries in slot_boundaries_by_doctor.items():
            for slot_idx, _ in enumerate(slot_boundaries):
                occupying = [
                    x[option.option_id]
                    for option in options
                    if option.doctor_idx == doctor_idx and slot_idx in option.occupied_slots
                ]
                if occupying:
                    prob += (
                        pulp.lpSum(occupying) <= 1,
                        f"Cap_d{doctor_idx}_s{slot_idx}",
                    )

        # Ограничение по дневному лимиту УП врача.
        for doctor_idx, d in enumerate(doctors):
            up_terms = [
                studies[options_by_id[oid].study_idx].up_value * x[oid]
                for oid in x
                if options_by_id[oid].doctor_idx == doctor_idx
            ]
            if up_terms:
                prob += pulp.lpSum(up_terms) <= d.max_up, f"UP_{doctor_idx}"

        self.objective.add_extra_constraints(prob, x, ctx, pulp)

        try:
            solver = pulp.PULP_CBC_CMD(
                timeLimit=MIP_TIME_LIMIT,
                msg=0,
                gapRel=MIP_GAP_REL,
            )
            prob.solve(solver)
            status = pulp.LpStatus[prob.status]
            solver_obj = float(pulp.value(prob.objective) or 0.0)
            self._log(f"CBC: статус={status}, obj={solver_obj:.3f}")

            if status not in {"Optimal", "Not Solved", "Undefined", "Infeasible", "Integer Feasible"}:
                self._log("  Неожиданный статус решателя → жадный fallback")
                assignment, details = self.solve_greedy(
                    studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
                )
                solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
                return assignment, details, float(solver_obj)

            chosen = [option for option in options if (pulp.value(x[option.option_id]) or 0) > 0.5]
            if len(chosen) != len(studies):
                self._log(
                    f"  Exact MILP выбрал {len(chosen)} вместо {len(studies)} → жадный fallback"
                )
                assignment, details = self.solve_greedy(
                    studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
                )
                solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
                return assignment, details, float(solver_obj)

            assignment: Dict[str, int] = {}
            details: Dict[str, Dict] = {}
            for option in chosen:
                study = studies[option.study_idx]
                doctor = doctors[option.doctor_idx]
                assignment[study.research_number] = doctor.id
                details[study.research_number] = self.objective.assignment_payload(option, study, doctor)

            self._log(f"Exact MILP: назначено {len(assignment)} / {len(studies)}")
            return assignment, details, solver_obj

        except Exception as e:
            self._log(f"CBC ошибка: {e} → жадный fallback")
            assignment, details = self.solve_greedy(
                studies, doctors, doc_prebooked_minutes=doc_prebooked_minutes
            )
            solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())
            return assignment, details, float(solver_obj)

    # ── Сохранение ───────────────────────────────────────────────────

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
        3. Формирование shortlist текущего дня.
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
                    f"Текущее время {self.now} после начала смены {min_start}, используем min_start как единое now для симуляции"
                )
                self.now = min_start

        studies = self.load_studies(date_from, date_to)

        if not doctors:
            return self._empty("Нет врачей с расписанием на сегодня", studies)
        if not studies:
            return self._empty("Нет исследований без назначения", studies)

        daily_pool = self.build_daily_pool(studies, doctors)
        if not daily_pool:
            return self._empty("Не удалось сформировать shortlist на текущий день", studies)

        if use_mip:
            assignment, details, solver_obj = self.solve_exact_mip(daily_pool, doctors)
        else:
            assignment, details = self.solve_greedy(daily_pool, doctors)
            solver_obj = sum(float(item.get("objective_value", 0.0)) for item in details.values())

        study_map = {s.research_number: s for s in studies}
        doctor_map = {d.id: d for d in doctors}

        # Переносим итог назначения в агрегаты врача, чтобы потом отдать doctor_stats.
        for sid, did in assignment.items():
            if sid not in study_map or did not in doctor_map:
                continue
            d = doctor_map[did]
            d.assigned_ids.append(sid)
            d.used_up += study_map[sid].up_value
            d.used_minutes += study_map[sid].duration_minutes

        all_assignments = []
        total_tardiness = 0.0
        total_weighted_tardiness = 0.0
        pstats = {"cito": 0, "asap": 0, "normal": 0}

        # Сначала добавляем в итоговый список назначенные исследования.
        for sid, meta in details.items():
            s = study_map[sid]
            d = doctor_map[meta["doctor_id"]]
            tardiness = float(meta.get("tardiness_hours", 0.0))
            weighted_tardiness = float(meta.get("weighted_tardiness", 0.0))
            objective_value = float(meta.get("objective_value", weighted_tardiness))

            total_tardiness += tardiness
            total_weighted_tardiness += weighted_tardiness
            pstats[s.priority] = pstats.get(s.priority, 0) + 1

            all_assignments.append(
                {
                    "study_number": s.research_number,
                    "study_modality": list(s.modality),
                    "doctor_id": d.id,
                    "doctor_name": d.name,
                    "doctor_modality": list(d.modality),
                    "priority": s.priority,
                    "deadline": s.deadline.isoformat(),
                    "start_time": meta["start_dt"].isoformat(),
                    "completion_time": meta["finish_dt"].isoformat(),
                    "tardiness_hours": round(tardiness, 2),
                    "weighted_tardiness": round(weighted_tardiness, 3),
                    "objective_value": round(objective_value, 3),
                    "up_value": s.up_value,
                    "is_overdue": s.deadline < self.now,
                }
            )

        # Затем добавляем исследования, которые остались неназначенными.
        # Это нужно фронту для вкладки "Не назначено" и общей аналитики.
        assigned_ids = set(assignment.keys())

        for s in studies:
            if s.research_number in assigned_ids:
                continue

            all_assignments.append(
                {
                    "study_number": s.research_number,
                    "study_modality": list(s.modality),
                    "doctor_id": None,
                    "doctor_name": None,
                    "doctor_modality": [],
                    "priority": s.priority,
                    "deadline": s.deadline.isoformat(),
                    "start_time": None,
                    "completion_time": None,
                    "tardiness_hours": None,
                    "weighted_tardiness": None,
                    "objective_value": None,
                    "up_value": s.up_value,
                    "is_overdue": s.deadline < self.now,
                }
            )

        # Сортировка нужна прежде всего для удобства UI:
        # - сначала назначенные;
        # - потом неназначенные;
        # - внутри — по врачу, времени старта и номеру исследования.
        all_assignments.sort(
            key=lambda item: (
                item["doctor_id"] is None,
                item["doctor_name"] or "",
                item["start_time"] or "",
                item["study_number"] or "",
            )
        )
        self.save_to_db(assignment)

        n_asgn = len(assignment)
        total_studies = len(studies)
        pool_size = len(daily_pool)
        backlog_outside_pool = max(0, total_studies - pool_size)
        z = round(total_weighted_tardiness, 3)

        def _pct(value: float, total: float) -> float:
            """Безопасно посчитать процент `value / total * 100`."""
            if total <= 0:
                return 0.0
            return round(value / total * 100, 2)

        def _percentile(values: List[float], q: float) -> float:
            """
            Посчитать q-перцентиль линейной интерполяцией.

            Используется для p50/p95/p99 по tardiness.
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

        # Словарь вида research_number -> tardiness для уже назначенных исследований.
        # Нужен для priority_breakdown и percentile-метрик.
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
        priority_breakdown: Dict[str, Dict[str, float | int | str]] = {}

        overdue_total = 0
        overdue_assigned = 0

        # Формируем подробную статистику по каждому уровню приоритета.
        for priority_code, output_key in priority_labels.items():
            priority_studies = [s for s in studies if s.priority == priority_code]
            priority_total = len(priority_studies)
            priority_assigned = sum(
                1 for s in priority_studies if s.research_number in assignment
            )
            priority_overdue_total = sum(
                1 for s in priority_studies if s.deadline < self.now
            )
            priority_overdue_assigned = sum(
                1
                for s in priority_studies
                if s.deadline < self.now and s.research_number in assignment
            )
            priority_overdue_hours_total = round(
                sum(
                    max(0.0, (self.now - s.deadline).total_seconds() / 3600.0)
                    for s in priority_studies
                ),
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
                "overdue_hours_avg": round(
                    priority_overdue_hours_total / priority_overdue_total, 2
                )
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

        self._log(
            f"Итого: shortlist={pool_size}/{total_studies}, назначено={n_asgn}/{total_studies} "
            f"({_pct(n_asgn, total_studies):.2f}%) | "
            f"CITO: {n_cito_assigned}/{n_cito_total} | "
            f"ASAP: {n_asap_assigned}/{n_asap_total} | "
            f"NORMAL: {n_normal_assigned}/{n_normal_total} | "
            f"Backlog вне shortlist: {backlog_outside_pool} | Z={z}"
        )

        if not self.preview_mode:
            self._log("Данные сохранены в БД")
        else:
            self._log("Данные НЕ сохранены в БД (режим предпросмотра)")

        return {
            "assigned": n_asgn,
            "unassigned": total_studies - n_asgn,
            "assigment_rate_percent": _pct(n_asgn, total_studies),
            "scheduled_pool_size": pool_size,
            "backlog_outside_pool": backlog_outside_pool,
            "cito_assigned": n_cito_assigned,
            "cito_total": n_cito_total,
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
                    "doctor_id": d.id,
                    "doctor_name": d.name,
                    "assigned_studies": len(d.assigned_ids),
                    "total_up": round(d.used_up, 3),
                    "max_up": round(d.max_up, 3),
                    "load_percent": round(d.used_up / d.max_up * 100, 1)
                    if d.max_up
                    else 0,
                    "remaining_up": round(d.free_up, 3),
                }
                for d in doctors
            ],
            "priority_stats": pstats,
            "objective_function": self._objective_meta(),
            "solver_objective_value": round(float(solver_obj), 3),
            "reported_weighted_tardiness": z,
            "message": (
                f"Оффлайн: shortlist {pool_size} из {total_studies}, назначено {n_asgn} "
                f"({_pct(n_asgn, total_studies):.2f}%). "
                f"CITO: {n_cito_assigned}/{n_cito_total}. objective={self.objective_code}, Z={z}"
            ),
            "_debug": self._debug,
            "preview_mode": self.preview_mode,
            "target_date": self.target_date.isoformat(),
        }

    def _empty(self, message: str, studies: List = None) -> Dict:
        """
        Сформировать пустой ответ сервиса.

        Используется в ситуациях, когда распределение невозможно начать или
        продолжить: нет врачей, нет исследований, не сформировался shortlist и т.п.
        """
        self._log(f"ПУСТО: {message}")
        return {
            "assigned": 0,
            "unassigned": len(studies or []),
            "assignment_rate_percent": 0.0,
            "scheduled_pool_size": 0,
            "backlog_outside_pool": len(studies or []),
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
            "objective_function": self._objective_meta(),
            "solver_objective_value": 0.0,
            "reported_weighted_tardiness": 0.0,
            "message": message,
            "_debug": self._debug,
        }
