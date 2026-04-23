"""
Импорт всех данных только из файла n_pers.

Команда намеренно не читает doktora.csv и Grafiki_obrabotannye.csv:
- врачей создаёт из колонки "Диагност";
- модальности врача собирает по исследованиям, которые он описывал;
- типы исследований и сами исследования импортирует как import_data.py;
- расписание строит из факта наличия исследования у врача в дату создания.

Запуск:
    python manage.py import_n_pers_data
    python manage.py import_n_pers_data --file /path/to/n_pers.xlsx
"""
from __future__ import annotations

import hashlib
import os
from datetime import time

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as dj_timezone

from api.management.commands.import_data import (
    STUDIES_XLSX,
    get_modality_and_up,
    get_priority,
    map_status,
    parse_study_entry,
)
from api.models import Doctor, Schedule, Study, StudyType
from api.services.modality_catalog import DOCTOR_DAILY_UP_DEFAULT


DEFAULT_SHIFT_START = time(9, 0)
DEFAULT_SHIFT_END = time(17, 0)
DEFAULT_BREAK_START = time(13, 0)
DEFAULT_BREAK_END = time(14, 0)


def _is_blank(value) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return not str(value).strip()


def _normalize_fio(value) -> str:
    return str(value or "").strip()


def _doctor_id_for_name(name: str) -> int:
    """
    Стабильный synthetic id для врачей из n_pers.

    Берём диапазон 10_000_000+, чтобы не пересекаться с реальными id из
    doktora.csv, если базу импортировали разными командами.
    """
    digest = hashlib.blake2b(name.upper().replace("Ё", "Е").encode("utf-8"), digest_size=4).hexdigest()
    return 10_000_000 + (int(digest, 16) % 900_000_000)


def _parse_datetime(value):
    if _is_blank(value):
        return None
    try:
        parsed = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(parsed):
        return None

    dt = parsed.to_pydatetime()
    return dt if dt.tzinfo else dj_timezone.make_aware(dt)


def _schedule_date_for_row(row):
    created_at = _parse_datetime(row.get("Дата создания"))
    if created_at is not None:
        return created_at.date()

    return None


def _import_research_number(raw_number, occurrence: int, excel_row_number: int) -> str:
    """
    Вернуть ключ исследования для импорта.

    В n_pers один "№ исследования" может занимать несколько строк: например,
    в рамках одного обращения пациенту сделали несколько разных исследований.
    Study.research_number является primary key, поэтому повторные строки нужно
    хранить под стабильным производным ключом, иначе update_or_create схлопнет
    их в одну запись.
    """
    if _is_blank(raw_number):
        return f"BLANK-ROW-{excel_row_number}"

    base_number = str(raw_number).strip()
    if occurrence <= 1:
        return base_number

    return f"{base_number}#{occurrence}"


class Command(BaseCommand):
    help = "Импорт врачей, модальностей, смен, типов и исследований только из n_pers XLSX"

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=".",
            help="Папка с n_pers файлом (по умолчанию: текущая директория)",
        )
        parser.add_argument(
            "--file",
            default=None,
            help=f"Путь к XLSX. По умолчанию: <data-dir>/{STUDIES_XLSX}",
        )
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="Не очищать Doctor/Schedule/StudyType/Study перед импортом",
        )
        parser.add_argument(
            "--shift-start",
            default=DEFAULT_SHIFT_START.strftime("%H:%M"),
            help="Начало стандартной смены, HH:MM",
        )
        parser.add_argument(
            "--shift-end",
            default=DEFAULT_SHIFT_END.strftime("%H:%M"),
            help="Конец стандартной смены, HH:MM",
        )
        parser.add_argument(
            "--break-start",
            default=DEFAULT_BREAK_START.strftime("%H:%M"),
            help="Начало обеда, HH:MM",
        )
        parser.add_argument(
            "--break-end",
            default=DEFAULT_BREAK_END.strftime("%H:%M"),
            help="Конец обеда, HH:MM",
        )

    def handle(self, *args, **options):
        xlsx_path = options["file"] or os.path.join(options["data_dir"], STUDIES_XLSX)
        if not os.path.exists(xlsx_path):
            raise CommandError(f"Файл не найден: {xlsx_path}")

        shift_start = self._parse_time_option(options["shift_start"], "shift-start")
        shift_end = self._parse_time_option(options["shift_end"], "shift-end")
        break_start = self._parse_time_option(options["break_start"], "break-start")
        break_end = self._parse_time_option(options["break_end"], "break-end")

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ИМПОРТ ТОЛЬКО ИЗ N_PERS"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Файл: {xlsx_path}")

        self.stdout.write("\nЗагрузка Excel...")
        df = pd.read_excel(xlsx_path)
        self.stdout.write(f"  Строк: {len(df)}")

        required = {"№ исследования", "Исследование", "Дата создания", "Плановая дата", "Диагност"}
        missing = sorted(required - set(df.columns))
        if missing:
            raise CommandError(f"В файле нет обязательных колонок: {', '.join(missing)}")

        with transaction.atomic():
            if not options["no_clear"]:
                self._clear_existing()

            doctor_map = self._import_doctors(df)
            self._import_study_types(df)
            self._import_schedules(
                df,
                doctor_map,
                shift_start=shift_start,
                shift_end=shift_end,
                break_start=break_start,
                break_end=break_end,
            )
            self._import_studies(df, doctor_map)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ГОТОВО"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Врачей:       {Doctor.objects.count()}")
        self.stdout.write(f"  Расписаний:   {Schedule.objects.count()}")
        self.stdout.write(f"  Типов иссл.:  {StudyType.objects.count()}")
        self.stdout.write(f"  Исследований: {Study.objects.count()}")

    def _parse_time_option(self, value: str, option_name: str) -> time:
        try:
            return pd.to_datetime(value, format="%H:%M").time()
        except Exception as exc:
            raise CommandError(f"--{option_name} должен быть в формате HH:MM") from exc

    def _clear_existing(self) -> None:
        self.stdout.write(self.style.WARNING("\nОчистка существующих данных..."))
        Study.objects.all().delete()
        Schedule.objects.all().delete()
        Doctor.objects.all().delete()
        StudyType.objects.all().delete()

    def _import_doctors(self, df: pd.DataFrame) -> dict[str, int]:
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 1: Врачи из n_pers --"))

        doctor_modalities: dict[str, set[str]] = {}

        for _, row in df.iterrows():
            if _is_blank(row.get("Диагност")):
                continue

            doctor_name = _normalize_fio(row.get("Диагност"))
            doctor_modalities.setdefault(doctor_name, set())
            _, study_name = parse_study_entry(row.get("Исследование"))
            if not study_name:
                continue

            modality, _ = get_modality_and_up(study_name)
            if modality == "OTHER":
                continue

            doctor_modalities.setdefault(doctor_name, set()).add(modality)

        created = updated = 0
        doctor_map: dict[str, int] = {}

        for doctor_name in sorted(doctor_modalities):
            doctor_id = _doctor_id_for_name(doctor_name)
            doctor_map[doctor_name.upper().replace("Ё", "Е")] = doctor_id

            _, created_flag = Doctor.objects.update_or_create(
                id=doctor_id,
                defaults={
                    "fio_alias": doctor_name,
                    "position_type": None,
                    "max_up_per_day": DOCTOR_DAILY_UP_DEFAULT,
                    "is_active": True,
                    "modality": sorted(doctor_modalities[doctor_name]),
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(f"  OK создано={created}, обновлено={updated}")
        self.stdout.write(f"  Врачей с модальностями: {len(doctor_map)}")
        return doctor_map

    def _import_study_types(self, df: pd.DataFrame) -> None:
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 2: Типы исследований --"))

        created = updated = skipped = 0
        for raw in df["Исследование"].dropna().unique():
            study_type_id, name = parse_study_entry(raw)
            if study_type_id is None or not name:
                skipped += 1
                continue

            modality, up_value = get_modality_and_up(name)
            _, created_flag = StudyType.objects.update_or_create(
                id=study_type_id,
                defaults={"name": name, "modality": modality, "up_value": up_value},
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )

    def _import_schedules(
        self,
        df: pd.DataFrame,
        doctor_map: dict[str, int],
        *,
        shift_start: time,
        shift_end: time,
        break_start: time,
        break_end: time,
    ) -> None:
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 3: Смены из факта исследований --"))

        schedule_keys: set[tuple[int, object]] = set()
        skipped = no_doctor = 0

        for _, row in df.iterrows():
            if _is_blank(row.get("Диагност")):
                skipped += 1
                continue

            doctor_key = _normalize_fio(row.get("Диагност")).upper().replace("Ё", "Е")
            doctor_id = doctor_map.get(doctor_key)
            if doctor_id is None:
                no_doctor += 1
                continue

            work_date = _schedule_date_for_row(row)
            if work_date is None:
                skipped += 1
                continue

            schedule_keys.add((doctor_id, work_date))

        created = updated = 0
        for doctor_id, work_date in sorted(schedule_keys, key=lambda item: (item[1], item[0])):
            defaults = {
                "time_start": shift_start,
                "time_end": shift_end,
                "break_start": break_start,
                "break_end": break_end,
                "is_day_off": 0,
                "day_status": 0,
            }
            schedule = Schedule.objects.filter(doctor_id=doctor_id, work_date=work_date).order_by("id").first()
            if schedule is None:
                Schedule.objects.create(doctor_id=doctor_id, work_date=work_date, **defaults)
                created += 1
            else:
                for field, value in defaults.items():
                    setattr(schedule, field, value)
                schedule.save(update_fields=list(defaults))
                updated += 1

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}, нет врача={no_doctor}"
        )

    def _import_studies(self, df: pd.DataFrame, doctor_map: dict[str, int]) -> None:
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 4: Исследования --"))

        known_types = set(StudyType.objects.values_list("id", flat=True))
        created = updated = no_type = no_diag = duplicate_rows = blank_numbers = 0
        pstats = {"cito": 0, "asap": 0, "normal": 0}
        unmatched: set[str] = set()
        research_number_occurrences: dict[str, int] = {}

        for row_index, row in df.iterrows():
            raw_research_number = row.get("№ исследования")
            if _is_blank(raw_research_number):
                blank_numbers += 1
                occurrence = 1
            else:
                base_research_number = str(raw_research_number).strip()
                occurrence = research_number_occurrences.get(base_research_number, 0) + 1
                research_number_occurrences[base_research_number] = occurrence
                if occurrence > 1:
                    duplicate_rows += 1

            research_number = _import_research_number(
                raw_research_number,
                occurrence,
                excel_row_number=int(row_index) + 2,
            )

            study_type_id, _ = parse_study_entry(row.get("Исследование"))
            if study_type_id not in known_types:
                no_type += 1
                study_type_id = None

            priority = get_priority(row.get("Столбец2"))
            pstats[priority] += 1

            diagnostician_id = None
            if not _is_blank(row.get("Диагност")):
                doctor_name = _normalize_fio(row.get("Диагност"))
                diagnostician_id = doctor_map.get(doctor_name.upper().replace("Ё", "Е"))
                if diagnostician_id is None:
                    no_diag += 1
                    unmatched.add(doctor_name)

            _, created_flag = Study.objects.update_or_create(
                research_number=research_number,
                defaults={
                    "study_type_id": study_type_id,
                    "status": map_status(row.get("Статус")),
                    "priority": priority,
                    "created_at": _parse_datetime(row.get("Дата создания")),
                    "planned_at": _parse_datetime(row.get("Плановая дата")),
                    "diagnostician_id": diagnostician_id,
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

            if (created + updated) % 10000 == 0 and (created + updated) > 0:
                self.stdout.write(f"    -> {created + updated} исследований...")

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, строк обработано={created + updated}"
        )
        self.stdout.write(
            f"  повторных строк с тем же №={duplicate_rows}, пустых №={blank_numbers}"
        )
        self.stdout.write(f"  нет типа={no_type}, нет диагноста={no_diag}")
        self.stdout.write(
            f"  Приоритеты: CITO={pstats['cito']}, "
            f"ASAP={pstats['asap']}, normal={pstats['normal']}"
        )

        if unmatched:
            self.stdout.write(
                self.style.WARNING(
                    f"  ! {len(unmatched)} диагностов не импортированы как врачи:"
                )
            )
            for fio in sorted(unmatched):
                self.stdout.write(f"      - {fio}")
