# Backend RadPlan

Backend RadPlan - Django REST API для хранения данных рентгенологической службы, планирования смен, расчета нагрузки, распределения исследований и прогнозирования потребности во врачах.

## Технологический стек

- Django 6.0
- Django REST Framework
- drf-spectacular
- django-cors-headers
- django-filter
- django-unfold
- PostgreSQL и `django.contrib.postgres`
- pandas, openpyxl
- OR-Tools, PuLP
- python-decouple

## Запуск

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Минимальный `backend/.env`:

```env
SECRET_KEY=change-me
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=radplan
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

## Структура

```text
backend/
├── api/
│   ├── management/commands/      # Импорт, экспорт и аналитические команды
│   ├── services/                 # Бизнес-логика, запросы, распределение, прогнозы
│   ├── models.py                 # Модели БД
│   ├── serializers.py            # DRF-сериализаторы и валидация
│   ├── urls.py                   # API-маршруты
│   └── views.py                  # ViewSet и function-based endpoints
├── rengenols/
│   ├── settings.py
│   └── urls.py
├── manage.py
└── requirements.txt
```

## Модели данных

### Doctor

Врач или диагност.

- `id` - внешний идентификатор врача.
- `fio_alias` - ФИО или отображаемое имя.
- `position_type` - должность.
- `max_up_per_day` - дневной лимит УП, по умолчанию 8.
- `is_active` - активность врача.
- `modality` - список модальностей врача.

### StudyType

Тип исследования.

- `id` - внешний идентификатор типа исследования.
- `name` - название исследования.
- `modality` - модальность.
- `up_value` - стоимость исследования в УП.

### Schedule

Смена врача.

- `doctor` - врач.
- `work_date` - дата смены.
- `time_start`, `time_end` - начало и конец работы.
- `break_start`, `break_end` - начало и конец перерыва.
- `is_day_off` - признак нерабочего дня.
- `day_status` - исходный статус дня из графика.
- `planned_up` - план УП на смену.

### Study

Исследование.

- `research_number` - номер исследования, primary key.
- `study_type` - тип исследования.
- `status` - `pending`, `confirmed` или `signed`.
- `priority` - `normal`, `cito` или `asap`.
- `created_at` - дата создания.
- `planned_at` - плановая дата исследования.
- `diagnostician` - назначенный врач.

## API

Базовый префикс: `/api/`.

### Врачи

- `GET /api/doctors/`
- `GET /api/doctors/with_load/`
- `GET /api/doctors/{id}/`
- `POST /api/doctors/`
- `PUT /api/doctors/{id}/`
- `DELETE /api/doctors/{id}/`

### Типы исследований

- `GET /api/study-types/`
- `GET /api/study-types/{id}/`

### Расписание

- `GET /api/schedules/`
- `GET /api/schedules/by_date/?date=YYYY-MM-DD`
- `GET /api/schedules/forecast/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD`
- `GET /api/schedules/{id}/`
- `POST /api/schedules/`
- `PUT /api/schedules/{id}/`
- `DELETE /api/schedules/{id}/`

### Исследования

- `GET /api/studies/`
- `GET /api/studies/pending/?page=1&page_size=100`
- `GET /api/studies/cito/?limit=100`
- `GET /api/studies/asap/?limit=100`
- `GET /api/studies/{research_number}/`
- `POST /api/studies/{research_number}/assign/`
- `PUT /api/studies/{research_number}/update_status/`

### Дашборд и графики

- `GET /api/dashboard/stats/`
- `GET /api/dashboard/chart/`

### Распределение

- `GET /api/distribute/` - входная информация.
- `POST /api/distribute/` - расчет распределения.
- `POST /api/distribute/confirm/` - применение сохраненного результата.
- `GET /api/distribute/preview/?date=YYYY-MM-DD` - быстрый предпросмотр.

### Прогноз

- `GET /api/forecast/compare-methods/` - сравнение методов прогноза.

## Документация API

- `GET /api/schema/` - OpenAPI-схема.
- `GET /api/docs/` - Swagger UI.
- `GET /admin/` - Django admin с темой Unfold.

## Management-команды

Команды импорта, экспорта и аналитики лежат в `api/management/commands/`.

```bash
python manage.py import_data --data-dir .
python manage.py import_miac_data --data-dir .
python manage.py import_n_pers_data --file .\n_pers_01_10_2025-31_12_2025.xlsx
python manage.py export_data --format json --output exports
python manage.py count_doctors_by_weekday --date-from 2025-10-01 --date-to 2025-11-17
```

Подробнее: `api/management/commands/README.md`.

## Особенности бизнес-логики

- Нагрузка считается в УП, значение берется из `StudyType.up_value`.
- Модальности нормализуются через сервис `modality_catalog`.
- В расписании `day_status` приводит `is_day_off` к единой логике.
- Распределение учитывает доступных врачей, модальности, приоритеты и плановые даты.
- Прогноз смен поддерживает несколько методов и endpoint для их сравнения.
