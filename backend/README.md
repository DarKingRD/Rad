# Backend часть RadPlan

Это серверная часть приложения RadPlan, реализованная на Python с использованием фреймворка Django и Django REST Framework.

## Технологический стек

- **Django 5.0.1** - мощный веб-фреймворк Python
- **Django REST Framework** - инструмент для создания REST API
- **drf-spectacular** - генерация документации API
- **django-cors-headers** - поддержка CORS
- **django-filter** - фильтрация данных
- **python-decouple** - управление конфигурацией
- **psycopg2-binary** - драйвер для PostgreSQL

## Структура проекта

```
backend/
├── api/                 # Основное приложение с API
│   ├── models.py        # Модели данных
│   ├── views.py         # Представления и API эндпоинты
│   ├── serializers.py  # Сериализаторы для API
│   ├── urls.py          # Маршруты API
│   └── ...
├── rengenols/           # Основной проект Django
│   ├── settings.py     # Конфигурация проекта
│   ├── urls.py          # Основные маршруты
│   └── ...
├── manage.py           # Утилита управления Django
└── requirements.txt     # Зависимости проекта
```

## Модели данных

### Doctor (Врач)
- `fio_alias` - ФИО или псевдоним врача
- `position_type` - тип позиции (radiologist/ct)
- `max_up_per_day` - максимальная нагрузка в УП в день
- `is_active` - активен ли врач
- `created_at` - дата создания
- `updated_at` - дата обновления

### StudyType (Тип исследования)
- `name` - название типа исследования
- `default_up` - стандартная нагрузка в УП
- `is_active` - активен ли тип исследования

### Schedule (Расписание)
- `doctor` - ссылка на врача
- `work_date` - дата работы
- `is_day_off` - выходной день
- `shift_type` - тип смены

### Study (Исследование)
- `study_type` - тип исследования
- `patient_name` - имя пациента
- `priority` - приоритет (normal/cito/asap)
- `status` - статус (pending/confirmed/signed)
- `diagnostician` - врач-диагност
- `created_at` - дата создания
- `signed_at` - дата подписания

## API эндпоинты

### Врачи
- `GET /api/doctors/` - список всех врачей
- `GET /api/doctors/with_load/` - врачи с текущей нагрузкой
- `POST /api/doctors/` - создание врача
- `PUT /api/doctors/{id}/` - обновление врача
- `DELETE /api/doctors/{id}/` - удаление врача

### Типы исследований
- `GET /api/study-types/` - список типов исследований

### Расписание
- `GET /api/schedule/` - расписание
- `GET /api/schedule/by_date/?date=YYYY-MM-DD` - расписание на дату
- `POST /api/schedule/` - создание записи в расписании
- `PUT /api/schedule/{id}/` - обновление записи
- `DELETE /api/schedule/{id}/` - удаление записи

### Исследования
- `GET /api/studies/` - список исследований
- `GET /api/studies/pending/` - ожидающие исследования
- `GET /api/studies/cito/` - CITO исследования
- `GET /api/studies/asap/` - ASAP исследования
- `POST /api/studies/{id}/assign/` - назначение исследования врачу
- `PUT /api/studies/{id}/update_status/` - обновление статуса

### Дашборд
- `GET /api/dashboard/stats/` - статистика для дашборда
- `GET /api/chart/data/` - данные для графиков

## Логика работы

### Расчет нагрузки
Нагрузка врача рассчитывается в условных единицах (УП) на основе количества назначенных исследований. Каждое исследование имеет базовую нагрузку в 1.5 УП.

### Статусы исследований
- `pending` - исследование создано, но не назначено врачу
- `confirmed` - исследование назначено врачу, но еще не выполнено
- `signed` - исследование выполнено и подписано врачом

### Приоритеты исследований
- `normal` - плановое исследование
- `cito` - срочное исследование
- `asap` - немедленное исследование

## Настройка и запуск

1. Создайте виртуальное окружение:
```bash
python -m venv venv
```

2. Активируйте виртуальное окружение:
```bash
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` в корне backend с необходимыми переменными окружения:
```
SECRET_KEY=ваш_секретный_ключ
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DB_NAME=название_базы
DB_USER=пользователь
DB_PASSWORD=пароль
DB_HOST=localhost
DB_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

5. Выполните миграции:
```bash
python manage.py migrate
```

6. Запустите сервер разработки:
```bash
python manage.py runserver
```

## Документация API

Документация API доступна по адресу `/api/schema/swagger/` или `/api/schema/redoc/` при запущенном сервере.