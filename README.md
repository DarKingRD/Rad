# RadPlan

RadPlan - веб-приложение для планирования работы рентгенологической службы: смены врачей, нагрузка в УП, распределение исследований, прогноз потребности в сменах и отчеты по выполнению.

## Что умеет приложение

- Планирует смены врачей с учетом рабочих часов, перерывов, выходных и статусов дня.
- Ведет справочники врачей, модальностей и типов исследований.
- Показывает текущую нагрузку врачей и активные исследования.
- Распределяет ожидающие исследования между доступными врачами с учетом модальностей, приоритетов и плановой даты.
- Поддерживает предпросмотр и подтверждение распределения.
- Строит дашборд, графики плана/факта и отчеты.
- Прогнозирует потребность в сменах и позволяет сравнивать методы прогноза.

## Архитектура

Проект состоит из двух частей:

- `backend/` - Django REST API, админка и команды импорта/экспорта данных.
- `frontend/` - React/Vite SPA для работы с API.

Основной поток данных:

1. CSV/XLSX-файлы импортируются management-командами Django.
2. Backend хранит врачей, расписание, типы исследований и исследования в PostgreSQL.
3. Frontend получает данные через REST API `http://localhost:8000/api`.
4. Распределение и прогнозы считаются на backend и отображаются в интерфейсе.

## Технологии

### Backend

- Python + Django 6.0
- Django REST Framework
- drf-spectacular для OpenAPI-схемы и Swagger UI
- django-cors-headers и django-filter
- django-unfold для админки
- PostgreSQL, включая `ArrayField` и GIN-индексы
- pandas/openpyxl для импорта Excel
- OR-Tools и PuLP для задач распределения

### Frontend

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Recharts
- Lucide React
- Axios

## Быстрый запуск

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Backend будет доступен на `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend по умолчанию запускается Vite на `http://localhost:5173` и обращается к backend по `http://localhost:8000/api`.

## Переменные окружения backend

Создайте `backend/.env`:

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

## Основные API

- `GET /api/doctors/` - врачи.
- `GET /api/doctors/with_load/` - врачи с текущей нагрузкой.
- `GET /api/study-types/` - типы исследований.
- `GET /api/schedules/` - расписание.
- `GET /api/schedules/by_date/?date=YYYY-MM-DD` - расписание за дату.
- `GET /api/schedules/forecast/` - прогноз потребности в сменах.
- `GET /api/studies/` - исследования.
- `GET /api/studies/pending/` - ожидающие исследования с пагинацией.
- `POST /api/studies/{research_number}/assign/` - назначение врачу.
- `PUT /api/studies/{research_number}/update_status/` - изменение статуса.
- `GET /api/dashboard/stats/` - KPI дашборда.
- `GET /api/dashboard/chart/` - данные графиков.
- `GET /api/distribute/` - информация перед распределением.
- `POST /api/distribute/` - расчет распределения.
- `POST /api/distribute/confirm/` - подтверждение рассчитанного распределения.
- `GET /api/distribute/preview/` - быстрый предпросмотр доступности.
- `GET /api/forecast/compare-methods/` - сравнение методов прогноза.

OpenAPI-схема доступна на `GET /api/schema/`, Swagger UI - на `GET /api/docs/`.

## Данные и импорт

Management-команды находятся в `backend/api/management/commands/`.

Частые сценарии:

```bash
cd backend
python manage.py import_data --data-dir .
python manage.py import_miac_data --data-dir .
python manage.py import_n_pers_data --file .\n_pers_01_10_2025-31_12_2025.xlsx
python manage.py export_data --format json --output exports
```

Подробности по командам описаны в `backend/api/management/commands/README.md`.

## Структура проекта

```text
Rad/
├── backend/
│   ├── api/
│   │   ├── management/commands/
│   │   ├── services/
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── urls.py
│   │   └── views.py
│   ├── rengenols/
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── services/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
└── README.md
```