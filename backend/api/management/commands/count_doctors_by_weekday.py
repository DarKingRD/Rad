from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count

from api.models import Schedule


WEEKDAY_LABELS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


class Command(BaseCommand):
    help = "Посчитать количество врачей по датам и среднее по дням недели"

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-from",
            default=None,
            help="Начальная дата включительно, YYYY-MM-DD",
        )
        parser.add_argument(
            "--date-to",
            default=None,
            help="Конечная дата включительно, YYYY-MM-DD",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Включить неактивных врачей",
        )
        parser.add_argument(
            "--include-days-off",
            action="store_true",
            help="Включить записи с is_day_off != 0",
        )

    def handle(self, *args, **options):
        queryset = Schedule.objects.filter(work_date__isnull=False)

        if options["date_from"]:
            queryset = queryset.filter(work_date__gte=options["date_from"])
        if options["date_to"]:
            queryset = queryset.filter(work_date__lte=options["date_to"])
        if not options["include_inactive"]:
            queryset = queryset.filter(doctor__is_active=True)
        if not options["include_days_off"]:
            queryset = queryset.filter(is_day_off=0)

        rows = (
            queryset.values("work_date")
            .annotate(doctors_count=Count("doctor_id", distinct=True))
            .order_by("work_date")
        )

        by_weekday: dict[str, list[tuple[object, int]]] = defaultdict(list)

        self.stdout.write("Врачи по датам:")
        for row in rows:
            day = row["work_date"]
            count = int(row["doctors_count"] or 0)
            weekday = WEEKDAY_LABELS[day.weekday()]
            by_weekday[weekday].append((day, count))
            self.stdout.write(f"{day:%d.%m.%Y} {weekday}: {count}")

        self.stdout.write("")
        self.stdout.write("Среднее по дням недели:")
        for weekday in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]:
            values = by_weekday[weekday]
            if not values:
                self.stdout.write(f"{weekday}: нет данных")
                continue

            counts = [count for _, count in values]
            avg = sum(counts) / len(counts)
            dates_text = ", ".join(f"{day:%d.%m}={count}" for day, count in values)
            self.stdout.write(f"{weekday}: {dates_text} | среднее={avg:.2f}")
