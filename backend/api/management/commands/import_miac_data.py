"""
Импорт данных МИАЦ из файлов doktora.csv, Grafiki_obrabotannye.csv и n_pers.

Правила импорта:
- врачи импортируются все из doktora.csv;
- врач считается работающим только при work_end = 9999-12-31;
- графики импортируются из файла "Графики обработанные" с сохранением day_status;
- исследования берутся только с описывающей организацией МИАЦ;
- исследования с заполненным диагностом вне doktora.csv отбрасываются.

Запуск:
    python manage.py import_miac_data --data-dir .
    python manage.py import_miac_data --data-dir . --no-clear
"""
from __future__ import annotations

import os
import re
from datetime import datetime

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone as dj_timezone

from api.management.commands.import_data import (
    DOCTORS_CSV,
    SCHEDULES_CSV,
    STUDIES_XLSX,
    get_modality_and_up,
    get_priority,
    map_status,
    parse_study_entry,
    parse_time,
)
from api.models import Doctor, Schedule, Study, StudyType
from api.services.modality_catalog import DOCTOR_DAILY_UP_DEFAULT
from api.services.schedule_status import is_day_off_by_status, normalize_day_status

MIAC_ORG_MARKER = "МИАЦ"
DOCTOR_COLUMNS = [
    "id",
    "snils",
    "fio",
    "fio_alias",
    "gender",
    "position_type",
    "work_end",
    "work_start",
    "is_chief",
    "is_nord_region",
]


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _normalize_text(value: object) -> str:
    if _is_blank(value):
        return ""
    return str(value).replace("\xa0", " ").strip().upper().replace("Ё", "Е")


def _normalize_fio_key(value: object) -> str:
    text = _normalize_text(value)
    return re.sub(r"[^0-9A-ZА-Я]", "", text)


def _parse_datetime(value: object):
    if _is_blank(value):
        return None
    try:
        dt = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(dt):
        return None
    if hasattr(dt, "to_pydatetime"):
        dt = dt.to_pydatetime()
    return dt if dt.tzinfo else dj_timezone.make_aware(dt)


def _parse_date(value: object):
    if _is_blank(value):
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _import_research_number(raw_value: object, occurrence: int, excel_row_number: int) -> str:
    """
    В n_pers номер исследования бывает повторным. В БД это primary key, поэтому
    первый номер оставляем как есть, а дубли сохраняем с суффиксом #2, #3 и т.д.
    """
    if _is_blank(raw_value):
        base = f"BLANK-ROW-{excel_row_number}"
    else:
        base = str(raw_value).strip()
    return base if occurrence == 1 else f"{base}#{occurrence}"


class Command(BaseCommand):
    help = "Импортирует только данные МИАЦ: врачи, графики и подходящие исследования"

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=".",
            help="Папка с файлами данных (по умолчанию: текущая директория)",
        )
        parser.add_argument(
            "--doctors-file",
            default=DOCTORS_CSV,
            help=f"CSV со списком врачей (по умолчанию: {DOCTORS_CSV})",
        )
        parser.add_argument(
            "--schedules-file",
            default=SCHEDULES_CSV,
            help=f"CSV с обработанными графиками (по умолчанию: {SCHEDULES_CSV})",
        )
        parser.add_argument(
            "--studies-file",
            default=STUDIES_XLSX,
            help=f"XLSX n_pers (по умолчанию: {STUDIES_XLSX})",
        )
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="Не очищать таблицы перед импортом",
        )

    def handle(self, *args, **options):
        data_dir = options["data_dir"]
        files = {
            "doctors": os.path.join(data_dir, options["doctors_file"]),
            "schedules": os.path.join(data_dir, options["schedules_file"]),
            "studies": os.path.join(data_dir, options["studies_file"]),
        }
        for label, path in files.items():
            if not os.path.exists(path):
                raise CommandError(f"Файл {label} не найден: {path}")
            self.stdout.write(f"  OK {path}")

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ИМПОРТ ДАННЫХ МИАЦ"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        self.stdout.write("\nЗагрузка файлов...")
        df_doctors = self._read_doctors(files["doctors"])
        df_schedules = self._read_schedules(files["schedules"])
        df_studies_raw = pd.read_excel(files["studies"])
        df_studies = self._filter_miac_studies(df_studies_raw)
        eligible_studies, skipped_unknown_diag = self._drop_unknown_diagnosticians(
            df_studies,
            df_doctors,
        )

        self.stdout.write(f"  Врачей в doktora.csv: {len(df_doctors)}")
        self.stdout.write(f"  Графиков в файле: {len(df_schedules)}")
        self.stdout.write(f"  Строк n_pers всего: {len(df_studies_raw)}")
        self.stdout.write(f"  Строк n_pers с МИАЦ: {len(df_studies)}")
        self.stdout.write(f"  Строк отброшено из-за диагноста вне doktora.csv: {skipped_unknown_diag}")
        self.stdout.write(f"  Строк исследований к импорту: {len(eligible_studies)}")

        with transaction.atomic():
            if not options["no_clear"]:
                self._clear_existing()

            doctor_fio_to_id = self._import_doctors(df_doctors, eligible_studies)
            self._import_schedules(df_schedules)
            self._import_study_types(eligible_studies)
            self._import_studies(eligible_studies, doctor_fio_to_id)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ГОТОВО"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Врачей:       {Doctor.objects.count()}")
        self.stdout.write(f"  Расписаний:   {Schedule.objects.count()}")
        self.stdout.write(f"  Типов иссл.:  {StudyType.objects.count()}")
        self.stdout.write(f"  Исследований: {Study.objects.count()}")

    def _read_doctors(self, csv_path: str) -> pd.DataFrame:
        return pd.read_csv(
            csv_path,
            encoding="utf-8-sig",
            skiprows=1,
            names=DOCTOR_COLUMNS,
        )

    def _read_schedules(self, csv_path: str) -> pd.DataFrame:
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        df.columns = [str(column).lstrip("\ufeff").strip().strip('"') for column in df.columns]
        return df

    def _filter_miac_studies(self, df: pd.DataFrame) -> pd.DataFrame:
        if "Орг. для описания" not in df.columns:
            raise CommandError('В n_pers нет столбца "Орг. для описания"')
        mask = df["Орг. для описания"].map(
            lambda value: MIAC_ORG_MARKER in _normalize_text(value)
        )
        return df.loc[mask].copy()

    def _drop_unknown_diagnosticians(
        self,
        df_studies: pd.DataFrame,
        df_doctors: pd.DataFrame,
    ) -> tuple[pd.DataFrame, int]:
        known_fio = {
            _normalize_fio_key(row.get("fio_alias"))
            for _, row in df_doctors.iterrows()
            if not _is_blank(row.get("fio_alias"))
        }

        keep_indexes = []
        skipped_unknown_diag = 0
        unknown_diagnosticians: set[str] = set()
        for idx, row in df_studies.iterrows():
            diag = row.get("Диагност")
            if _is_blank(diag):
                keep_indexes.append(idx)
                continue

            diag_key = _normalize_fio_key(diag)
            if diag_key in known_fio:
                keep_indexes.append(idx)
                continue

            skipped_unknown_diag += 1
            unknown_diagnosticians.add(str(diag).strip())

        if unknown_diagnosticians:
            self.stdout.write(
                self.style.WARNING(
                    f"  Диагностов МИАЦ вне doktora.csv: {len(unknown_diagnosticians)}"
                )
            )
            for fio in sorted(unknown_diagnosticians)[:20]:
                self.stdout.write(f"    - {fio}")
            if len(unknown_diagnosticians) > 20:
                self.stdout.write(f"    ... и еще {len(unknown_diagnosticians) - 20}")

        return df_studies.loc[keep_indexes].copy(), skipped_unknown_diag

    def _clear_existing(self):
        self.stdout.write(self.style.WARNING("\n-- ОЧИСТКА ТАБЛИЦ --"))
        Study.objects.all().delete()
        Schedule.objects.all().delete()
        Doctor.objects.all().delete()
        StudyType.objects.all().delete()
        self.stdout.write("  Таблицы очищены")

    def _import_doctors(self, df_doctors: pd.DataFrame, df_studies: pd.DataFrame) -> dict[str, int]:
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 1: Врачи из doktora.csv --"))

        diag_modalities: dict[str, set[str]] = {}
        for _, row in df_studies.iterrows():
            diag_key = _normalize_fio_key(row.get("Диагност"))
            if not diag_key:
                continue

            _, name = parse_study_entry(row.get("Исследование"))
            if not name:
                continue

            modality, _ = get_modality_and_up(name)
            if modality == "OTHER":
                continue
            diag_modalities.setdefault(diag_key, set()).add(modality)

        created = updated = skipped = active = inactive = 0
        doctor_fio_to_id: dict[str, int] = {}

        for _, row in df_doctors.iterrows():
            try:
                doctor_id = int(row["id"])
            except (ValueError, TypeError):
                skipped += 1
                continue

            fio_alias = None if _is_blank(row.get("fio_alias")) else str(row.get("fio_alias")).strip()
            position_type = (
                None
                if _is_blank(row.get("position_type"))
                else str(row.get("position_type")).strip()
            )
            fio_key = _normalize_fio_key(fio_alias)
            if fio_key:
                doctor_fio_to_id[fio_key] = doctor_id

            work_end = "" if _is_blank(row.get("work_end")) else str(row.get("work_end")).strip()
            is_active = work_end == "9999-12-31"
            active += 1 if is_active else 0
            inactive += 0 if is_active else 1

            _, created_flag = Doctor.objects.update_or_create(
                id=doctor_id,
                defaults={
                    "fio_alias": fio_alias,
                    "position_type": position_type,
                    "is_active": is_active,
                    "max_up_per_day": DOCTOR_DAILY_UP_DEFAULT,
                    "modality": sorted(diag_modalities.get(fio_key, set())),
                },
            )
            created += 1 if created_flag else 0
            updated += 0 if created_flag else 1

        no_modality = Doctor.objects.filter(modality=[])
        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}, "
            f"работающих={active}, уволенных={inactive}"
        )
        self.stdout.write(f"  Врачей без модальностей по МИАЦ-исследованиям: {no_modality.count()}")
        return doctor_fio_to_id

    def _import_schedules(self, df_schedules: pd.DataFrame):
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 2: Графики обработанные --"))

        id_col = "id" if "id" in df_schedules.columns else df_schedules.columns[0]
        known_doctor_ids = set(Doctor.objects.values_list("id", flat=True))
        created = updated = skipped = no_doctor = 0
        day_status_stats: dict[int, int] = {}

        for _, row in df_schedules.iterrows():
            try:
                schedule_id = int(row[id_col])
                doctor_id = int(row["doctor_id"])
            except (ValueError, TypeError, KeyError):
                skipped += 1
                continue

            if doctor_id not in known_doctor_ids:
                no_doctor += 1
                continue

            work_date = _parse_date(row.get("date"))
            if work_date is None:
                skipped += 1
                continue

            day_status = normalize_day_status(row.get("day_status"))
            day_status_stats[day_status] = day_status_stats.get(day_status, 0) + 1

            _, created_flag = Schedule.objects.update_or_create(
                id=schedule_id,
                defaults={
                    "doctor_id": doctor_id,
                    "work_date": work_date,
                    "time_start": parse_time(row.get("start_time")),
                    "time_end": parse_time(row.get("end_time")),
                    "break_start": parse_time(row.get("lunch_start_time")),
                    "break_end": parse_time(row.get("lunch_end_time")),
                    "is_day_off": 1 if is_day_off_by_status(day_status) else 0,
                    "day_status": day_status,
                },
            )
            created += 1 if created_flag else 0
            updated += 0 if created_flag else 1

            if (created + updated) % 5000 == 0:
                self.stdout.write(f"    -> {created + updated} графиков...")

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, "
            f"пропущено={skipped}, нет врача={no_doctor}"
        )
        self.stdout.write(
            "  day_status: "
            + ", ".join(f"{status}={count}" for status, count in sorted(day_status_stats.items()))
        )

    def _import_study_types(self, df_studies: pd.DataFrame):
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 3: Типы исследований --"))

        created = updated = skipped = 0
        unique_raw = df_studies["Исследование"].dropna().unique()
        for raw in unique_raw:
            study_type_id, name = parse_study_entry(raw)
            if study_type_id is None or not name:
                skipped += 1
                continue

            modality, up_value = get_modality_and_up(name)
            _, created_flag = StudyType.objects.update_or_create(
                id=study_type_id,
                defaults={
                    "name": name,
                    "modality": modality,
                    "up_value": up_value,
                },
            )
            created += 1 if created_flag else 0
            updated += 0 if created_flag else 1

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )

    def _import_studies(self, df_studies: pd.DataFrame, doctor_fio_to_id: dict[str, int]):
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 4: Исследования МИАЦ --"))

        known_types = set(StudyType.objects.values_list("id", flat=True))
        research_occurrences: dict[str, int] = {}
        created = updated = skipped = no_type = blank_diag = 0
        pstats = {"cito": 0, "asap": 0, "normal": 0}

        for index, row in df_studies.iterrows():
            raw_research_number = row.get("№ исследования")
            base_research_number = (
                f"BLANK-ROW-{index + 2}"
                if _is_blank(raw_research_number)
                else str(raw_research_number).strip()
            )
            occurrence = research_occurrences.get(base_research_number, 0) + 1
            research_occurrences[base_research_number] = occurrence
            research_number = _import_research_number(
                raw_research_number,
                occurrence,
                index + 2,
            )

            study_type_id, _ = parse_study_entry(row.get("Исследование"))
            if study_type_id not in known_types:
                no_type += 1
                study_type_id = None

            diagnostician_id = None
            diag_key = _normalize_fio_key(row.get("Диагност"))
            if diag_key:
                diagnostician_id = doctor_fio_to_id.get(diag_key)
                if diagnostician_id is None:
                    skipped += 1
                    continue
            else:
                blank_diag += 1

            priority = get_priority(row.get("Столбец2"))
            pstats[priority] += 1

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
            created += 1 if created_flag else 0
            updated += 0 if created_flag else 1

            if (created + updated) % 10000 == 0:
                self.stdout.write(f"    -> {created + updated} исследований...")

        duplicate_count = sum(count - 1 for count in research_occurrences.values() if count > 1)
        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )
        self.stdout.write(
            f"  нет типа={no_type}, пустой диагност={blank_diag}, "
            f"дублей номеров сохранено с суффиксом={duplicate_count}"
        )
        self.stdout.write(
            f"  Приоритеты: CITO={pstats['cito']}, "
            f"ASAP={pstats['asap']}, normal={pstats['normal']}"
        )
