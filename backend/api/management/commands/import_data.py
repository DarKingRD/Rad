# api/management/commands/import_data.py
"""
Команда импорта всех данных в БД.

Запуск:
    python manage.py import_data
    python manage.py import_data --data-dir /path/to/files
    python manage.py import_data --step doctors   # только один шаг

Файлы (положи рядом с manage.py или укажи --data-dir):
    doktora.csv
    Grafiki_obrabotannye.csv
    n_pers_01_10_2025-31_12_2025.xlsx
"""

import os
import re
from decimal import Decimal
from datetime import datetime, timezone

import pandas as pd

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import Doctor, StudyType, Schedule, Study


DOCTORS_CSV   = "doktora.csv"
SCHEDULES_CSV = "Grafiki_obrabotannye.csv"
STUDIES_XLSX  = "n_pers_01_10_2025-31_12_2025.xlsx"


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

def parse_study_entry(raw):
    """
    '7002892 / Рентгенография грудной клетки'
        -> (7002892, 'Рентгенография грудной клетки')
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    m = re.match(r"^(\d+)\s*/\s*(.+)$", str(raw).strip())
    if m:
        return int(m.group(1)), m.group(2).strip()
    return None, str(raw).strip()


def get_modality_and_up(name: str):
    """
    Определяет модальность и УП по названию исследования.

    Из Положения об оплате ОМС:
      Флюорография                -> XRAY,   0.067,  4 мин
      Маммография                 -> MAMMO,  0.10,   6 мин
      Рентгенография              -> XRAY,   0.083,  5 мин
      КТ без контраста            -> CT,     0.25,  15 мин
      КТ с контрастом             -> CT,     0.417, 25 мин
      МРТ без контраста           -> MRI,    0.333, 20 мин
      МРТ с контрастом            -> MRI,    0.50,  30 мин
      ЭКГ                         -> ECG,    0.067,  4 мин
      Холтер                      -> HOLTER, 0.417, 25 мин
      ЭЭГ                         -> EEG,    0.333, 20 мин
      Суточное мониторирование АД -> HOLTER, 0.25,  15 мин
      УЗИ                         -> US,     0.083,  5 мин
    """
    if not name:
        return "OTHER", Decimal("0.083")
    n = name.lower()
    has_contrast = "контраст" in n or "болюс" in n
    if "флюоро" in n:
        return "XRAY", Decimal("0.067")
    if "маммо" in n:
        return "MAMMO", Decimal("0.10")
    if "рентген" in n:
        return "XRAY", Decimal("0.083")
    if "компьютерная томограф" in n:
        return ("CT", Decimal("0.417")) if has_contrast else ("CT", Decimal("0.25"))
    if "магнитно-резонансная" in n:
        return ("MRI", Decimal("0.50")) if has_contrast else ("MRI", Decimal("0.333"))
    if "электрокардиограф" in n or "экг" in n:
        return "ECG", Decimal("0.067")
    if "холтеровское" in n or "холтер" in n:
        return "HOLTER", Decimal("0.417")
    if "электроэнцефало" in n or "ээг" in n:
        return "EEG", Decimal("0.333")
    if "суточное мониторирование" in n and "давлени" in n:
        return "HOLTER", Decimal("0.25")
    if "ультразвук" in n or "узи" in n or "сонограф" in n:
        return "US", Decimal("0.083")
    return "OTHER", Decimal("0.083")


def get_priority(html_col) -> str:
    if html_col is None or (isinstance(html_col, float) and pd.isna(html_col)):
        return "normal"
    s = str(html_col).lower()
    if "cito" in s:
        return "cito"
    if "asap" in s or "экстренно" in s:
        return "asap"
    return "normal"


def map_status(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "confirmed"
    s = str(raw).strip().lower()
    if "подписано" in s or "заключение выполнено" in s or "выполнено" in s:
        return "signed"
    return "confirmed"


def parse_time(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return datetime.strptime(str(val).strip()[:8], "%H:%M:%S").time()
    except Exception:
        return None


# ==============================================================================
# КОМАНДА
# ==============================================================================

class Command(BaseCommand):
    help = "Импорт врачей, расписаний, типов исследований и исследований из CSV/XLSX"

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            default=".",
            help="Папка с файлами данных (по умолчанию: текущая директория)",
        )
        parser.add_argument(
            "--step",
            choices=["doctors", "schedules", "study_types", "studies", "all"],
            default="all",
            help="Какой шаг выполнить (по умолчанию: all)",
        )

    def handle(self, *args, **options):
        data_dir = options["data_dir"]
        step     = options["step"]

        files = {
            "doctors":   os.path.join(data_dir, DOCTORS_CSV),
            "schedules": os.path.join(data_dir, SCHEDULES_CSV),
            "studies":   os.path.join(data_dir, STUDIES_XLSX),
        }
        for key, path in files.items():
            if not os.path.exists(path):
                raise CommandError(f"Файл не найден: {path}")
            self.stdout.write(f"  OK {path}")

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ИМПОРТ ДАННЫХ"))
        self.stdout.write(self.style.SUCCESS("=" * 60))

        self.stdout.write("\nЗагрузка Excel...")
        df_studies = pd.read_excel(files["studies"])
        self.stdout.write(f"  {len(df_studies)} строк")

        if step in ("doctors", "all"):
            with transaction.atomic():
                self._step1_doctors(files["doctors"], df_studies)

        if step in ("schedules", "all"):
            with transaction.atomic():
                self._step2_schedules(files["schedules"])

        if step in ("study_types", "all"):
            with transaction.atomic():
                self._step3_study_types(df_studies)

        if step in ("studies", "all"):
            with transaction.atomic():
                self._step4_studies(df_studies)

        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  ГОТОВО"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Врачей:       {Doctor.objects.count()}")
        self.stdout.write(f"  Расписаний:   {Schedule.objects.count()}")
        self.stdout.write(f"  Типов иссл.:  {StudyType.objects.count()}")
        self.stdout.write(f"  Исследований: {Study.objects.count()}")

    # ──────────────────────────────────────────────────────────────
    # ШАГ 1: ВРАЧИ + МОДАЛЬНОСТИ
    # ──────────────────────────────────────────────────────────────
    def _step1_doctors(self, csv_path: str, df_studies: pd.DataFrame):
        """
        Импорт врачей из doktora.csv.

        Модальности вычисляются из реальных данных исследований:
        смотрим все исследования которые описывал каждый диагност,
        собираем уникальные модальности — это его специализация.
        Doctor.modality = ArrayField -> ['CT', 'MRI', ...]

        Маппинг CSV -> модель Doctor:
          col[0]  id            -> Doctor.id
          fio_alias             -> Doctor.fio_alias
          position_type         -> Doctor.position_type
          work_end = 9999-12-31 -> Doctor.is_active = True, иначе False
          is_chief = true       -> Doctor.max_up_per_day = 40  (завед., Положение)
          иначе                 -> Doctor.max_up_per_day = 50  (врач,   Положение)
          из исследований       -> Doctor.modality
        """
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 1: Врачи + модальности --"))

        # Вычисляем модальности из исследований для каждого диагноста
        diag_modalities: dict = {}
        for _, row in df_studies.iterrows():
            diag = row.get("Диагност")
            if diag is None or (isinstance(diag, float) and pd.isna(diag)):
                continue
            _, name = parse_study_entry(row.get("Исследование"))
            if not name:
                continue
            mod, _ = get_modality_and_up(name)
            if mod == "OTHER":
                continue
            diag_modalities.setdefault(str(diag).strip(), set()).add(mod)

        self.stdout.write(
            f"  Диагностов с модальностями из исследований: {len(diag_modalities)}"
        )

        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        id_col = df.columns[0]

        created = updated = skipped = 0

        for _, row in df.iterrows():
            try:
                doctor_id = int(row[id_col])
            except (ValueError, TypeError):
                skipped += 1
                continue

            fio_alias     = str(row.get("fio_alias") or "").strip() or None
            position_type = str(row.get("position_type") or "").strip() or None
            work_end      = str(row.get("work_end") or "").strip()
            is_chief      = str(row.get("is_chief", "false")).strip().lower() in ("true", "1", "да")
            is_active     = work_end in ("9999-12-31", "")
            max_up        = 6 if is_chief else 8
            modalities    = sorted(diag_modalities.get(fio_alias, set())) if fio_alias else []

            _, created_flag = Doctor.objects.update_or_create(
                id=doctor_id,
                defaults={
                    "fio_alias":      fio_alias,
                    "position_type":  position_type,
                    "is_active":      is_active,
                    "max_up_per_day": max_up,
                    "modality":       modalities,
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )

        no_mod = Doctor.objects.extra(where=["array_length(modality, 1) IS NULL"])
        if no_mod.exists():
            self.stdout.write(
                self.style.WARNING(
                    f"  ! Врачей без модальностей: {no_mod.count()} (нет в файле исследований)"
                )
            )
            for d in no_mod:
                self.stdout.write(f"      [{d.id}] {d.fio_alias}")

        self.stdout.write(f"  Врачей в БД: {Doctor.objects.count()}")

    # ──────────────────────────────────────────────────────────────
    # ШАГ 2: РАСПИСАНИЯ
    # ──────────────────────────────────────────────────────────────
    def _step2_schedules(self, csv_path: str):
        """
        Импорт расписания из Grafiki_obrabotannye.csv.

        Маппинг CSV -> модель Schedule:
          col[0]  id            -> Schedule.id
          doctor_id             -> Schedule.doctor (FK -> Doctor)
          date                  -> Schedule.work_date
          start_time            -> Schedule.time_start
          end_time              -> Schedule.time_end
          lunch_start_time      -> Schedule.break_start
          lunch_end_time        -> Schedule.break_end
          day_status = 0  -> Schedule.is_day_off = 0 (рабочий день)
          day_status != 0 -> Schedule.is_day_off = 1 (выходной/отпуск/прочее)

        Значения day_status из источника:
          0 - рабочий, 1 - выходной, 2 - отпуск, 3 - больничный, 5/6 - прочие
        """
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 2: Расписания --"))

        df = pd.read_csv(csv_path, encoding="utf-8-sig")
        id_col = df.columns[0]

        known_ids = set(Doctor.objects.values_list("id", flat=True))
        self.stdout.write(f"  Строк: {len(df)}, врачей в БД: {len(known_ids)}")

        created = updated = skipped = no_doctor = 0

        for _, row in df.iterrows():
            try:
                sched_id  = int(row[id_col])
                doctor_id = int(row["doctor_id"])
            except (ValueError, TypeError):
                skipped += 1
                continue

            if doctor_id not in known_ids:
                no_doctor += 1
                continue

            try:
                work_date = datetime.strptime(str(row["date"]).strip(), "%Y-%m-%d").date()
            except Exception:
                skipped += 1
                continue

            day_status = int(row.get("day_status") or 0)

            _, created_flag = Schedule.objects.update_or_create(
                id=sched_id,
                defaults={
                    "doctor_id":   doctor_id,
                    "work_date":   work_date,
                    "time_start":  parse_time(row.get("start_time")),
                    "time_end":    parse_time(row.get("end_time")),
                    "break_start": parse_time(row.get("lunch_start_time")),
                    "break_end":   parse_time(row.get("lunch_end_time")),
                    "is_day_off":  0 if day_status == 0 else 1,
                },
            )
            if created_flag:
                created += 1
            else:
                updated += 1

            if (created + updated) % 2000 == 0:
                self.stdout.write(f"    -> {created + updated} записей...")

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, "
            f"пропущено={skipped}, нет врача={no_doctor}"
        )
        self.stdout.write(f"  Расписаний в БД: {Schedule.objects.count()}")

    # ──────────────────────────────────────────────────────────────
    # ШАГ 3: ТИПЫ ИССЛЕДОВАНИЙ
    # ──────────────────────────────────────────────────────────────
    def _step3_study_types(self, df: pd.DataFrame):
        """
        Импорт типов исследований из XLSX.

        Берём уникальные значения колонки 'Исследование'.
        Модальность и УП определяются по названию согласно
        Положению об оплате ОМС (см. функцию get_modality_and_up).

        Маппинг -> StudyType:
          числовой код ('7002892 / ...') -> StudyType.id
          текст после '/ '              -> StudyType.name
          по названию                   -> StudyType.modality (строка)
          по названию                   -> StudyType.up_value (Decimal)
        """
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 3: Типы исследований --"))

        unique_raw = df["Исследование"].dropna().unique()
        self.stdout.write(f"  Уникальных типов: {len(unique_raw)}")

        created = updated = skipped = 0

        for raw in unique_raw:
            study_id, name = parse_study_entry(raw)
            if study_id is None:
                skipped += 1
                continue
            modality, up_value = get_modality_and_up(name)
            _, created_flag = StudyType.objects.update_or_create(
                id=study_id,
                defaults={"name": name, "modality": modality, "up_value": up_value},
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )
        self.stdout.write(f"  Типов в БД: {StudyType.objects.count()}")

        from django.db.models import Count
        for s in StudyType.objects.values("modality").annotate(n=Count("id")).order_by("-n"):
            self.stdout.write(f"    {s['modality']:8s}: {s['n']} типов")

    # ──────────────────────────────────────────────────────────────
    # ШАГ 4: ИССЛЕДОВАНИЯ
    # ──────────────────────────────────────────────────────────────
    def _step4_studies(self, df: pd.DataFrame):
        """
        Импорт исследований из XLSX (upsert по research_number).

        Маппинг колонок -> модель Study:
          '№ исследования'  -> Study.research_number  (ключ upsert)
          'Исследование'    -> Study.study_type_id
          'Статус'          -> Study.status  (signed / confirmed)
          'Столбец2'        -> Study.priority  (cito / asap / normal)
          'Дата создания'   -> Study.created_at
          'Плановая дата'   -> Study.planned_at
          'Диагност'        -> Study.diagnostician_id  (FK по fio_alias)

        Строки без '№ исследования' пропускаются.
        Диагносты без совпадения -> diagnostician_id = NULL.
        """
        self.stdout.write(self.style.HTTP_INFO("\n-- ШАГ 4: Исследования --"))
        self.stdout.write(f"  Строк в файле: {len(df)}")

        fio_to_id = {
            str(fio).strip().upper().replace("Ё", "Е"): did
            for did, fio in Doctor.objects.values_list("id", "fio_alias")
            if fio
        }
        known_types = set(StudyType.objects.values_list("id", flat=True))

        created = updated = skipped = no_type = no_diag = 0
        pstats = {"cito": 0, "asap": 0, "normal": 0}
        unmatched: set = set()



        for _, row in df.iterrows():
            rn = row.get("№ исследования")
            if rn is None or (isinstance(rn, float) and pd.isna(rn)) or not str(rn).strip():
                skipped += 1
                continue
            research_number = str(rn).strip()

            study_type_id, _ = parse_study_entry(row.get("Исследование"))
            if study_type_id not in known_types:
                no_type += 1
                study_type_id = None

            priority = get_priority(row.get("Столбец2"))
            pstats[priority] += 1

            created_at = None
            ca = row.get("Дата создания")
            if ca is not None and not (isinstance(ca, float) and pd.isna(ca)):
                try:
                    dt = pd.to_datetime(ca).to_pydatetime()
                    created_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            planned_at = None
            pa = row.get("Плановая дата")
            if pa is not None and not (isinstance(pa, float) and pd.isna(pa)):
                try:
                    dt = pd.to_datetime(pa).to_pydatetime()
                    planned_at = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            diagnostician_id = None
            diag_raw = row.get("Диагност")
            if diag_raw is not None and not (isinstance(diag_raw, float) and pd.isna(diag_raw)):
                norm = str(diag_raw).strip().upper().replace("Ё", "Е")
                diagnostician_id = fio_to_id.get(norm)
                if diagnostician_id is None:
                    unmatched.add(str(diag_raw).strip())
                    no_diag += 1

            try:
                _, created_flag = Study.objects.update_or_create(
                    research_number=research_number,
                    defaults={
                        "study_type_id":    study_type_id,
                        "status":           map_status(row.get("Статус")),
                        "priority":         priority,
                        "created_at":       created_at,
                        "planned_at":       planned_at,
                        "diagnostician_id": diagnostician_id,
                    },
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                skipped += 1
                if skipped <= 3:
                    self.stderr.write(f"  ERR [{research_number}]: {e}")
                continue

            if (created + updated) % 10000 == 0 and (created + updated) > 0:
                self.stdout.write(f"    -> {created + updated} исследований...")

        self.stdout.write(
            f"  OK создано={created}, обновлено={updated}, пропущено={skipped}"
        )
        self.stdout.write(f"  нет типа={no_type}, нет диагноста={no_diag}")
        self.stdout.write(
            f"  Приоритеты: CITO={pstats['cito']}, "
            f"ASAP={pstats['asap']}, normal={pstats['normal']}"
        )
        self.stdout.write(f"  Исследований в БД: {Study.objects.count()}")

        if unmatched:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  ! {len(unmatched)} диагностов не найдено -> diagnostician_id = NULL:"
                )
            )
            for fio in sorted(unmatched):
                self.stdout.write(f"      - {fio}")
            self.stdout.write(
                "  Добавь их в doktora.csv и перезапусти: "
                "python manage.py import_data --step doctors"
            )
