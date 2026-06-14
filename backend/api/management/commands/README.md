# Management-команды RadPlan

Команды запускаются из папки `backend` через `python manage.py <command>`.

## Импорт данных

### `generate_demo_data`

Создает демонстрационный набор данных на 4 дня: врачей, расписания, типы исследований и очередь ожидающих исследований. Повторный запуск пересоздает только демо-записи с префиксом `DEMO-`.

```bash
python manage.py generate_demo_data
python manage.py generate_demo_data --start-date 2026-05-22 --days 4 --studies-per-day 45
```

Опции:

- `--start-date` - первый день демо-периода в формате `YYYY-MM-DD`.
- `--days` - количество дней демо-периода, по умолчанию `4`.
- `--studies-per-day` - количество ожидающих исследований на день, по умолчанию `45`.

### `import_data`

Импортирует полный набор исходных файлов:

- `doktora.csv`
- `Grafiki_obrabotannye.csv`
- `n_pers_01_10_2025-31_12_2025.xlsx`

```bash
python manage.py import_data --data-dir .
python manage.py import_data --data-dir . --step doctors
```

Опции:

- `--data-dir` - папка с файлами данных.
- `--step` - один шаг импорта: `doctors`, `schedules`, `study_types`, `studies` или `all`.

### `import_miac_data`

Импортирует только данные МИАЦ: врачей, графики и подходящие исследования. По умолчанию очищает основные таблицы перед импортом.

```bash
python manage.py import_miac_data --data-dir .
python manage.py import_miac_data --data-dir . --no-clear
```

Опции:

- `--data-dir` - папка с файлами.
- `--doctors-file` - CSV со списком врачей.
- `--schedules-file` - CSV с обработанными графиками.
- `--studies-file` - XLSX `n_pers`.
- `--no-clear` - не очищать таблицы перед импортом.

### `import_n_pers_data`

Импортирует данные только из XLSX `n_pers`: создает врачей из колонки `Диагност`, типы исследований, исследования и смены по факту наличия исследований.

```bash
python manage.py import_n_pers_data --file .\n_pers_01_10_2025-31_12_2025.xlsx
python manage.py import_n_pers_data --data-dir . --no-clear
```

Опции:

- `--data-dir` - папка с XLSX-файлом.
- `--file` - явный путь к XLSX.
- `--no-clear` - не очищать `Doctor`, `Schedule`, `StudyType`, `Study`.
- `--shift-start`, `--shift-end` - стандартные границы смены в формате `HH:MM`.
- `--break-start`, `--break-end` - стандартный перерыв в формате `HH:MM`.

## Очистка

### `clear_data`

Удаляет данные из `Study`, `Schedule`, `Doctor`, `StudyType`.

```bash
python manage.py clear_data
```

Команда необратимо очищает основные рабочие таблицы.

## Экспорт

### `export_data`

Выгружает данные моделей Django ORM в `json`, `jsonl` или `csv`.

```bash
python manage.py export_data
python manage.py export_data --format csv --output exports
python manage.py export_data --models api.Doctor api.Study --format jsonl
```

Опции:

- `--models` - список моделей в формате `app_label.ModelName`.
- `--format` - `json`, `jsonl` или `csv`.
- `--output` - папка для файлов выгрузки.
- `--include-system` - включить системные модели Django.

## Аналитические команды

### `count_doctors_by_weekday`

Считает количество врачей по датам и среднее по дням недели на основе расписания.

```bash
python manage.py count_doctors_by_weekday
python manage.py count_doctors_by_weekday --date-from 2025-10-01 --date-to 2025-11-17
```

Опции:

- `--date-from`, `--date-to` - границы периода.
- `--include-inactive` - учитывать неактивных врачей.
- `--include-days-off` - учитывать выходные записи.

### `count_weekday_stats`

Сравнивает количество исследований и врачей по дням недели.

```bash
python manage.py count_weekday_stats
python manage.py count_weekday_stats --doctor-source studies
```

Опции:

- `--date-from`, `--date-to` - границы периода.
- `--doctor-source` - источник врачей: `schedules` или `studies`.
- `--include-inactive` - учитывать неактивных врачей при источнике `schedules`.
- `--include-days-off` - учитывать выходные записи при источнике `schedules`.
