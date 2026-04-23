from __future__ import annotations

from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.db.models.functions import TruncDate

from api.models import Schedule, Study


WEEKDAY_LABELS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}
WEEKDAY_ORDER = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _parse_date_arg(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CommandError(f"Некорректная дата {value!r}, нужен формат YYYY-MM-DD") from exc


def _format_number(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _format_dates(values: list[tuple[date, int]]) -> str:
    return ", ".join(f"{day:%d.%m}" for day, _ in values)


def _format_counts(values: list[tuple[date, int]]) -> str:
    return ", ".join(str(count) for _, count in values)


class Command(BaseCommand):
    help = "Считает по моделям БД таблицы исследований и врачей на сменах по дням недели"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-from",
            default="2025-10-01",
            help="Начальная дата включительно, YYYY-MM-DD",
        )
        parser.add_argument(
            "--date-to",
            default="2025-11-17",
            help="Конечная дата включительно, YYYY-MM-DD",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Включить в графиках неактивных врачей",
        )
        parser.add_argument(
            "--include-days-off",
            action="store_true",
            help="Включить в графиках записи с is_day_off != 0",
        )
        parser.add_argument(
            "--doctor-source",
            choices=["schedules", "studies"],
            default="schedules",
            help=(
                "Откуда считать врачей: schedules = врачи на сменах из Schedule, "
                "studies = уникальные diagnostician_id из Study"
            ),
        )

    def handle(self, *args, **options):
        date_from = _parse_date_arg(options["date_from"])
        date_to = _parse_date_arg(options["date_to"])

        study_by_weekday = self._count_studies_by_weekday(date_from, date_to)
        self._print_weekday_table(
            title="Проверим, сколько исследований приходило в каждый день недели:",
            count_header="Кол-во исследований",
            by_weekday=study_by_weekday,
        )

        self.stdout.write("")

        if options["doctor_source"] == "studies":
            doctor_by_weekday = self._count_study_doctors_by_weekday(date_from, date_to)
            title = "Теперь посчитаем кол-во врачей/диагностов по исследованиям:"
        else:
            doctor_by_weekday = self._count_schedule_doctors_by_weekday(
                date_from=date_from,
                date_to=date_to,
                include_inactive=options["include_inactive"],
                include_days_off=options["include_days_off"],
            )
            title = "Теперь посчитаем кол-во врачей на сменах:"

        self._print_weekday_table(
            title=title,
            count_header="Кол-во врачей",
            by_weekday=doctor_by_weekday,
        )

    def _count_studies_by_weekday(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, list[tuple[date, int]]]:
        queryset = Study.objects.filter(created_at__isnull=False)
        if date_from is not None:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to is not None:
            queryset = queryset.filter(created_at__date__lte=date_to)

        rows = (
            queryset.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("research_number"))
            .order_by("day")
        )
        return self._rows_to_weekday_table(rows, "count")

    def _count_schedule_doctors_by_weekday(
        self,
        date_from: date | None,
        date_to: date | None,
        include_inactive: bool,
        include_days_off: bool,
    ) -> dict[str, list[tuple[date, int]]]:
        queryset = Schedule.objects.filter(work_date__isnull=False)
        if date_from is not None:
            queryset = queryset.filter(work_date__gte=date_from)
        if date_to is not None:
            queryset = queryset.filter(work_date__lte=date_to)
        if not include_inactive:
            queryset = queryset.filter(doctor__is_active=True)
        if not include_days_off:
            queryset = queryset.filter(is_day_off=0)

        rows = (
            queryset.values("work_date")
            .annotate(count=Count("doctor_id", distinct=True))
            .order_by("work_date")
        )

        by_weekday: dict[str, list[tuple[date, int]]] = defaultdict(list)
        for row in rows:
            day = row["work_date"]
            if day is None:
                continue
            by_weekday[WEEKDAY_LABELS[day.weekday()]].append((day, int(row["count"] or 0)))
        return by_weekday

    def _count_study_doctors_by_weekday(
        self,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, list[tuple[date, int]]]:
        queryset = Study.objects.filter(
            created_at__isnull=False,
            diagnostician_id__isnull=False,
        )
        if date_from is not None:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to is not None:
            queryset = queryset.filter(created_at__date__lte=date_to)

        rows = (
            queryset.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("diagnostician_id", distinct=True))
            .order_by("day")
        )
        return self._rows_to_weekday_table(rows, "count")

    def _rows_to_weekday_table(
        self,
        rows,
        count_key: str,
    ) -> dict[str, list[tuple[date, int]]]:
        by_weekday: dict[str, list[tuple[date, int]]] = defaultdict(list)
        for row in rows:
            day = row["day"]
            if day is None:
                continue
            by_weekday[WEEKDAY_LABELS[day.weekday()]].append((day, int(row[count_key] or 0)))
        return by_weekday

    def _print_weekday_table(
        self,
        title: str,
        count_header: str,
        by_weekday: dict[str, list[tuple[date, int]]],
    ):
        self.stdout.write(title)
        self.stdout.write(f"День недели\tДаты\t{count_header}\tСреднее")

        for weekday in WEEKDAY_ORDER:
            values = by_weekday.get(weekday, [])
            if not values:
                self.stdout.write(f"{weekday}\tнет данных\tнет данных\tнет данных")
                continue

            counts = [count for _, count in values]
            average = sum(counts) / len(counts)
            self.stdout.write(
                f"{weekday}\t{_format_dates(values)}\t"
                f"{_format_counts(values)}\t{_format_number(average)}"
            )
