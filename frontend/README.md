# Frontend RadPlan

Frontend RadPlan - React/Vite SPA для работы с расписанием врачей, распределением исследований, дашбордом, отчетами и прогнозом потребности в сменах.

## Технологический стек

- React 18
- TypeScript
- Vite
- Tailwind CSS
- Recharts
- Lucide React
- Axios

## Запуск

```bash
cd frontend
npm install
npm run dev
```

Сборка:

```bash
npm run build
npm run preview
```

По умолчанию API подключен в `src/services/api.ts` по адресу `http://localhost:8000/api`.

## Структура

```text
frontend/
├── src/
│   ├── components/
│   │   ├── dashboard/
│   │   ├── distribution/
│   │   ├── doctors/
│   │   ├── layout/
│   │   ├── planning/
│   │   └── reports/
│   ├── services/
│   │   └── api.ts
│   ├── types/
│   │   └── index.ts
│   ├── App.tsx
│   ├── index.css
│   └── main.tsx
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## Разделы интерфейса

- Дашборд - KPI, обзорные показатели и графики.
- Планирование смен - расписание врачей, рабочие часы, перерывы, статусы дня и прогноз.
- Распределение исследований - ожидающие исследования, карточки врачей, черновики, предпросмотр и подтверждение распределения.
- Врачи - справочник врачей, активность, должность, модальности и лимиты.
- Отчеты - аналитические представления по исследованиям и нагрузке.

## Работа с API

API-клиент находится в `src/services/api.ts`. Он:

- использует Axios с базовым URL `http://localhost:8000/api`;
- нормализует ошибки в `ApiClientError`;
- повторяет GET-запросы при сетевых ошибках, `5xx` и `429`;
- умеет извлекать списки как из plain array, так и из paginated `{ results: [...] }`.

Основные группы методов:

- `doctorsApi` - врачи и врачи с нагрузкой.
- `studyTypesApi` - типы исследований.
- `schedulesApi` - расписание и прогноз смен.
- `studiesApi` - исследования, CITO/ASAP, назначение и статусы.
- `dashboardApi` - KPI и графики.
- `distributionApi` - информация, расчет, быстрый предпросмотр и подтверждение распределения.

## Скрипты

- `npm run dev` - dev-сервер Vite.
- `npm run build` - TypeScript-проверка и production-сборка.
- `npm run preview` - локальный preview production-сборки.

## Типы

Общие TypeScript-типы лежат в `src/types/index.ts` и используются API-клиентом и компонентами. При изменении backend-контрактов сначала обновляйте типы, затем сервисы и UI.
