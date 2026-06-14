import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, RefreshCw, Users, X } from 'lucide-react';
import { ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, BarChart, Bar, LineChart, Line } from 'recharts';

import { schedulesApi } from '../../services/api';
import type { Doctor, Schedule, ShiftForecastResponse } from '../../types';

interface ShiftForecastPanelProps {
  refreshKey?: number;
  doctors?: Doctor[];
  schedules?: Schedule[];
  doctorMonthlyCompletedLoad?: Record<number, number>;
  onScheduleDoctor?: (doctorId: number, date: string, suggestedPlannedUp?: number) => void;
}

type DoctorRecord = Doctor & Record<string, unknown>;

const formatLocalDate = (d: Date) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const formatMetric = (value?: number | null, digits = 1) => {
  if (value === null || value === undefined) return '0';
  return new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  }).format(value);
};

const formatStudiesCount = (value?: number | null) => {
  if (value === null || value === undefined) return '0';
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(Math.ceil(value));
};

const formatDateFullLabel = (value?: string | null) => {
  if (!value) return '—';
  return new Date(`${value}T12:00:00`).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const normalizeModality = (value?: string | null) =>
  (value || '')
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/\s+/g, ' ')
    .trim();

const modalityToKey = (value?: string | null) => {
  const normalized = normalizeModality(value);
  if (!normalized) return 'other';

  if (normalized.includes('флюор') || normalized.includes('flg') || normalized.includes('fluoro')) {
    return 'fluorography';
  }

  if (normalized.includes('рентген') || normalized.includes('xray') || normalized.includes('x-ray')) {
    return 'xray';
  }

  const isCt =
    normalized.includes('кт') ||
    (normalized.includes('компьютерн') &&
      (normalized.includes('томограф') || normalized.includes('томограм')));

  if (isCt) {
    return normalized.includes('контраст') ? 'ct_contrast' : 'ct';
  }

  const isMri =
    normalized.includes('мрт') ||
    normalized.includes('магнитно-резонанс') ||
    (normalized.includes('магнитно') && normalized.includes('резонанс'));

  if (isMri) {
    return normalized.includes('контраст') ? 'mri_contrast' : 'mri';
  }

  if (normalized.includes('проч') || normalized.includes('other')) return 'other';

  return normalized;
};

const getStringField = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object') {
    const item = value as Record<string, unknown>;
    return String(item.name ?? item.title ?? item.label ?? item.modality ?? item.modality_name ?? item.code ?? '');
  }
  return '';
};

const getDoctorModalities = (doctor: Doctor): string[] => {
  const doctorRecord = doctor as DoctorRecord;
  const rawValues = [
    doctorRecord.modality,
    doctorRecord.modalities,
    doctorRecord.modality_names,
    doctorRecord.available_modalities,
    doctorRecord.specializations,
  ];

  return rawValues
    .flatMap((value) => (Array.isArray(value) ? value : value ? [value] : []))
    .map(getStringField)
    .map((value) => value.trim())
    .filter(Boolean);
};

const getDoctorModalityKeys = (doctor: Doctor): string[] => {
  const keys = new Set<string>();
  getDoctorModalities(doctor).forEach((item) => keys.add(modalityToKey(item)));

  // Fallback используем только если API вообще не вернул модальности.
  // Иначе поле должности «врач-рентгенолог» ошибочно добавит всем врачам рентген и флюорографию.
  if (keys.size === 0) {
    const doctorRecord = doctor as DoctorRecord;
    const specialty = normalizeModality(
      String(doctorRecord.specialty ?? doctorRecord.position_type ?? doctorRecord.position ?? '')
    );
    if (specialty.includes('рентген')) {
      keys.add('xray');
      keys.add('fluorography');
    }
  }

  return [...keys];
};

const isDoctorActive = (doctor: Doctor): boolean => {
  const doctorRecord = doctor as unknown as Record<string, unknown>;
  const value = doctorRecord.is_active ?? doctorRecord.active ?? true;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    return !['false', '0', 'no', 'нет', 'ложь'].includes(value.toLowerCase().trim());
  }
  return true;
};

const getDoctorName = (doctor: Doctor): string => {
  const doctorRecord = doctor as DoctorRecord;
  return String(doctorRecord.fio_alias ?? doctorRecord.full_name ?? doctorRecord.fio ?? doctorRecord.name ?? 'Без имени');
};

const getDoctorStableId = (doctor: Doctor): string => {
  const doctorRecord = doctor as DoctorRecord;
  return String(doctorRecord.id ?? doctorRecord.doctor_id ?? doctorRecord.external_id ?? getDoctorName(doctor));
};

const getDoctorNumericId = (doctor: Doctor): number | null => {
  const doctorRecord = doctor as DoctorRecord;
  const id = Number(doctorRecord.id ?? doctorRecord.doctor_id ?? doctorRecord.external_id);
  return Number.isFinite(id) ? id : null;
};

const getDoctorCapacity = (doctor: Doctor): number => {
  const value = Number((doctor as DoctorRecord).max_up_per_day ?? 0);
  return Number.isFinite(value) ? value : 0;
};

const hashString = (value: string): number =>
  value.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);

const modalityMatchesDoctor = (forecastModality: string, doctor: Doctor): boolean => {
  const target = modalityToKey(forecastModality);
  const doctorKeys = getDoctorModalityKeys(doctor);

  if (doctorKeys.includes(target)) return true;

  // Врач с контрастной модальностью может закрывать обычную КТ/МРТ.
  // Обратное не делаем: обычная КТ/МРТ не должна автоматически закрывать контраст.
  if (target === 'ct' && doctorKeys.includes('ct_contrast')) return true;
  if (target === 'mri' && doctorKeys.includes('mri_contrast')) return true;

  return false;
};

type ForecastDay = ShiftForecastResponse['days'][number];

type DayDoctorRecommendation = {
  doctor: Doctor;
  modalities: string[];
  isScheduled: boolean;
  monthlyLoad: number;
  score: number;
};

type MissingModalityRequest = {
  date: string;
  weekday: string;
  modality: string;
  candidates: DayDoctorRecommendation[];
};

const getScheduleDoctorId = (schedule: Schedule): number | null => {
  if (typeof schedule.doctor === 'object' && schedule.doctor?.id) return schedule.doctor.id;
  const id = Number(schedule.doctor_id || (typeof schedule.doctor === 'number' ? schedule.doctor : 0));
  return Number.isFinite(id) && id > 0 ? id : null;
};

const isWorkingSchedule = (schedule?: Schedule | null) => !!schedule && schedule.day_status === 0;

const getScheduleForDoctor = (schedules: Schedule[], doctorId: number, date: string) =>
  schedules.find((schedule) => {
    const scheduleDoctorId = getScheduleDoctorId(schedule);
    const scheduleDate = schedule.work_date?.split('T')[0];
    return scheduleDoctorId === doctorId && scheduleDate === date;
  });

const getMonthlyLoad = (doctor: Doctor, monthlyLoadByDoctor: Record<number, number>) => {
  const doctorId = getDoctorNumericId(doctor);
  return doctorId === null ? 0 : monthlyLoadByDoctor[doctorId] || 0;
};

const getSchedulePlannedUp = (schedule?: Schedule | null) => {
  if (!isWorkingSchedule(schedule)) return 0;
  const value = Number(schedule?.planned_up ?? 0);
  return Number.isFinite(value) ? Math.max(value, 0) : 0;
};

const getProjectedMonthlyLoadBeforeDate = (
  doctor: Doctor,
  date: string,
  schedules: Schedule[],
  monthlyLoadByDoctor: Record<number, number>
) => {
  const doctorId = getDoctorNumericId(doctor);
  const factualLoad = getMonthlyLoad(doctor, monthlyLoadByDoctor);
  if (doctorId === null) return factualLoad;

  const plannedLoadBeforeDate = schedules.reduce((sum, schedule) => {
    const scheduleDoctorId = getScheduleDoctorId(schedule);
    const scheduleDate = schedule.work_date?.split('T')[0];
    if (scheduleDoctorId !== doctorId || !scheduleDate || scheduleDate >= date) return sum;
    return sum + getSchedulePlannedUp(schedule);
  }, 0);

  return factualLoad + plannedLoadBeforeDate;
};

const buildCandidateScore = (
  doctor: Doctor,
  day: ForecastDay,
  modality: string,
  schedules: Schedule[],
  monthlyLoadByDoctor: Record<number, number>,
  scarcityRank = 0
) => {
  const doctorId = getDoctorNumericId(doctor);
  const schedule = doctorId === null ? undefined : getScheduleForDoctor(schedules, doctorId, day.date);
  const monthlyLoad = getProjectedMonthlyLoadBeforeDate(doctor, day.date, schedules, monthlyLoadByDoctor);
  const modalityCount = getDoctorModalityKeys(doctor).length || 1;
  const capacity = getDoctorCapacity(doctor);
  const scheduledPenalty = isWorkingSchedule(schedule) ? -8 : schedule ? 30 : 0;
  const universalPenalty = modalityCount > 1 ? modalityCount * 1.5 : 0;
  const capacityBonus = Math.min(capacity, 12) * -0.2;
  const seed = (hashString(`${day.date}-${modality}-${getDoctorStableId(doctor)}`) % 100) / 100;

  return monthlyLoad + scheduledPenalty + universalPenalty + capacityBonus + scarcityRank * 0.1 + seed;
};

const buildCandidatesForModality = (
  day: ForecastDay,
  modality: string,
  doctors: Doctor[],
  schedules: Schedule[],
  monthlyLoadByDoctor: Record<number, number>,
  scarcityRank = 0
): DayDoctorRecommendation[] =>
  doctors
    .filter(isDoctorActive)
    .filter((doctor) => modalityMatchesDoctor(modality, doctor))
    .map((doctor) => {
      const doctorId = getDoctorNumericId(doctor);
      const schedule = doctorId === null ? undefined : getScheduleForDoctor(schedules, doctorId, day.date);
      const monthlyLoad = getProjectedMonthlyLoadBeforeDate(doctor, day.date, schedules, monthlyLoadByDoctor);

      return {
        doctor,
        modalities: [modality],
        isScheduled: isWorkingSchedule(schedule),
        monthlyLoad,
        score: buildCandidateScore(doctor, day, modality, schedules, monthlyLoadByDoctor, scarcityRank),
      };
    })
    .sort((a, b) => {
      if (a.isScheduled !== b.isScheduled) return a.isScheduled ? -1 : 1;
      if (a.score !== b.score) return a.score - b.score;
      return getDoctorName(a.doctor).localeCompare(getDoctorName(b.doctor), 'ru');
    });

const buildDayDoctorRecommendations = (
  day: ForecastDay,
  doctors: Doctor[],
  schedules: Schedule[],
  monthlyLoadByDoctor: Record<number, number>
) => {
  const activeDoctors = doctors.filter(isDoctorActive);
  const availableByModality = new Map<string, Doctor[]>();

  day.required_modalities.forEach((modality) => {
    availableByModality.set(
      modality.modality,
      activeDoctors.filter((doctor) => modalityMatchesDoctor(modality.modality, doctor))
    );
  });

  const sortedModalities = [...day.required_modalities].sort((a, b) => {
    const aAvailable = availableByModality.get(a.modality)?.length ?? 0;
    const bAvailable = availableByModality.get(b.modality)?.length ?? 0;

    // Сначала закрываем дефицитные модальности, чтобы рентген/флюорография
    // не забирали врачей, которые нужны для КТ/МРТ.
    if (aAvailable !== bAvailable) return aAvailable - bAvailable;

    return (b.recommended_doctors || 0) - (a.recommended_doctors || 0);
  });

  const recommendationsByModality = new Map<string, Doctor[]>();
  const recommendationsByDoctor = new Map<string, DayDoctorRecommendation>();

  sortedModalities.forEach((modality, scarcityRank) => {
    const needCount = modality.recommended_doctors || 0;
    const selected = buildCandidatesForModality(
      day,
      modality.modality,
      availableByModality.get(modality.modality) || activeDoctors,
      schedules,
      monthlyLoadByDoctor,
      scarcityRank
    ).slice(0, needCount);

    selected.forEach((item) => {
      const doctorId = getDoctorStableId(item.doctor);

      const existing = recommendationsByDoctor.get(doctorId);
      if (existing) {
        existing.modalities.push(modality.modality);
        existing.score = Math.min(existing.score, item.score);
      } else {
        recommendationsByDoctor.set(doctorId, {
          ...item,
          modalities: [modality.modality],
        });
      }
    });
    recommendationsByModality.set(modality.modality, selected.map((item) => item.doctor));
  });

  const totalNeed = day.required_modalities.reduce(
    (sum, modality) => sum + (modality.recommended_doctors || 0),
    0
  );
  const coveredCount = [...recommendationsByModality.values()].reduce(
    (sum, selected) => sum + selected.length,
    0
  );

  return {
    byModality: recommendationsByModality,
    doctors: [...recommendationsByDoctor.values()].sort((a, b) => {
      if (a.isScheduled !== b.isScheduled) return a.isScheduled ? -1 : 1;
      if (a.score !== b.score) return a.score - b.score;
      return getDoctorName(a.doctor).localeCompare(getDoctorName(b.doctor), 'ru');
    }),
    totalNeed,
    coveredCount,
    missingCount: Math.max(0, totalNeed - coveredCount),
  };
};

const getDefaultRange = () => {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  return {
    dateFrom: formatLocalDate(start),
    dateTo: formatLocalDate(end),
  };
};

export const ShiftForecastPanel: React.FC<ShiftForecastPanelProps> = ({
  refreshKey = 0,
  doctors = [],
  schedules = [],
  doctorMonthlyCompletedLoad = {},
  onScheduleDoctor,
}) => {
  const defaults = useMemo(() => getDefaultRange(), []);
  const [inputDateFrom, setInputDateFrom] = useState(defaults.dateFrom);
  const [inputDateTo, setInputDateTo] = useState(defaults.dateTo);
  const [inputHistoryStartDate, setInputHistoryStartDate] = useState('');
  const [inputHistoryEndDate, setInputHistoryEndDate] = useState('');
  const [appliedDateFrom, setAppliedDateFrom] = useState(defaults.dateFrom);
  const [appliedDateTo, setAppliedDateTo] = useState(defaults.dateTo);
  const [appliedHistoryStartDate, setAppliedHistoryStartDate] = useState('');
  const [appliedHistoryEndDate, setAppliedHistoryEndDate] = useState('');
  const [forecast, setForecast] = useState<ShiftForecastResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [missingRequest, setMissingRequest] = useState<MissingModalityRequest | null>(null);

  const loadForecast = async (
    dateFrom: string,
    dateTo: string,
    historyStartDate = '',
    historyEndDate = ''
  ) => {
    try {
      setLoading(true);
      setError(null);
      const data = await schedulesApi.getForecast({
        date_from: dateFrom,
        date_to: dateTo,
        ...(historyStartDate ? { history_start_date: historyStartDate } : {}),
        ...(historyEndDate ? { history_end_date: historyEndDate } : {}),
      });
      setForecast(data);
    } catch (err) {
      console.error('Error loading shift forecast:', err);
      setError(err instanceof Error ? err.message : 'Не удалось загрузить прогноз.');
      setForecast(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadForecast(appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate);
  }, [appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate, refreshKey]);


  const handleApply = () => {
    if (!inputDateFrom || !inputDateTo) {
      setError('Нужно выбрать обе даты диапазона.');
      return;
    }
    if (inputDateFrom > inputDateTo) {
      setError('Дата окончания не может быть раньше даты начала.');
      return;
    }
    if ((inputHistoryStartDate && !inputHistoryEndDate) || (!inputHistoryStartDate && inputHistoryEndDate)) {
      setError('Для исторического периода нужно выбрать обе даты или оставить оба поля пустыми.');
      return;
    }
    if (inputHistoryStartDate && inputHistoryEndDate && inputHistoryStartDate > inputHistoryEndDate) {
      setError('Дата окончания истории не может быть раньше даты начала истории.');
      return;
    }
    setAppliedDateFrom(inputDateFrom);
    setAppliedDateTo(inputDateTo);
    setAppliedHistoryStartDate(inputHistoryStartDate);
    setAppliedHistoryEndDate(inputHistoryEndDate);
  };

  const chartData = forecast?.chart || [];
  const summary = forecast?.summary;
  const days = forecast?.days || [];
  const dayRecommendations = useMemo(
    () =>
      new Map(
        days.map((day) => [
          day.date,
          buildDayDoctorRecommendations(day, doctors, schedules, doctorMonthlyCompletedLoad),
        ])
      ),
    [days, doctors, schedules, doctorMonthlyCompletedLoad]
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-lg font-semibold text-slate-950">Прогноз потребности в специалистах</div>
          {!isExpanded && (
            <div className="mt-3 text-xs text-slate-500">
              {forecast
                ? `Последний диапазон: ${formatDateFullLabel(forecast.date_from)} — ${formatDateFullLabel(forecast.date_to)}`
                : 'Прогноз появится после выбора диапазона.'}
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700"
        >
          {isExpanded ? 'Скрыть прогноз' : 'Показать прогноз'}
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {isExpanded && (
        <div className="mt-4 space-y-4">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-end">
            <div className="flex flex-col gap-3 xl:min-w-[680px]">
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
                <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                  Прогноз от
                  <input
                    type="date"
                    value={inputDateFrom}
                    onChange={(e) => setInputDateFrom(e.target.value)}
                    className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                  Прогноз до
                  <input
                    type="date"
                    value={inputDateTo}
                    onChange={(e) => setInputDateTo(e.target.value)}
                    className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                  История от
                  <input
                    type="date"
                    value={inputHistoryStartDate}
                    onChange={(e) => setInputHistoryStartDate(e.target.value)}
                    className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  />
                </label>
                <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
                  История до
                  <input
                    type="date"
                    value={inputHistoryEndDate}
                    onChange={(e) => setInputHistoryEndDate(e.target.value)}
                    className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  />
                </label>
              </div>
              <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
                <button
                  type="button"
                  onClick={handleApply}
                  className="rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700"
                >
                  Построить прогноз
                </button>
                <button
                  type="button"
                  onClick={() => loadForecast(appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate)}
                  className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50"
                >
                  <RefreshCw size={16} />
                  Обновить
                </button>
              </div>
            </div>
          </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Ожидается исследований</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : formatStudiesCount(summary?.total_expected_studies)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Ожидаемый объём, УП</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : formatMetric(summary?.total_expected_up, 2)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Пиковая потребность во врачах</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : summary?.max_min_doctors_per_shift ?? 0}</div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs text-slate-600 md:text-sm">
        {forecast?.message || 'Прогноз будет загружен после выбора диапазона.'}
      </div>

      {error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
          {error}
        </div>
      )}

      {!loading && !error && chartData.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="font-semibold text-slate-900 mb-1">Ожидаемые исследования</div>
            <div className="text-xs text-slate-500 mb-4">Прогноз потока по дням выбранного диапазона.</div>
            <div className="h-64 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => [formatStudiesCount(value), 'Исследований']} />
                  <Bar dataKey="expected_studies_total" name="Исследований" fill="#2563eb" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="font-semibold text-slate-900 mb-1">Потребность во врачах</div>
            <div className="text-xs text-slate-500 mb-4">Минимальное число врачей по дням.</div>
            <div className="h-64 sm:h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis allowDecimals={false} />
                  <Tooltip formatter={(value: number) => [value, 'Врачей']} />
                  <Line type="monotone" dataKey="min_doctors" name="Врачей" stroke="#2563eb" strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
      {!loading && !error && days.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-2 border-b border-slate-200 bg-slate-50/80 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="font-semibold text-slate-900">Кого поставить в смену</div>
              <div className="text-xs text-slate-500">
                Подбор учитывает модальности, уже выставленные смены и месячную нагрузку врачей.
              </div>
            </div>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600">
              <Users size={14} />
              {doctors.length} активных врачей
            </div>
          </div>
          <div className="grid gap-2.5 p-3 md:grid-cols-2 xl:grid-cols-3">
            {days.map((day) => {
              const recommendations = dayRecommendations.get(day.date) ||
                buildDayDoctorRecommendations(day, doctors, schedules, doctorMonthlyCompletedLoad);
              const scheduledCountFor = (modalityName: string) => {
                const selected = recommendations.byModality.get(modalityName) || [];
                return selected.filter((doctor) => {
                  const doctorId = getDoctorNumericId(doctor);
                  return doctorId !== null && isWorkingSchedule(getScheduleForDoctor(schedules, doctorId, day.date));
                }).length;
              };
              const scheduledCoveredCount = day.required_modalities.reduce(
                (sum, modality) => sum + scheduledCountFor(modality.modality),
                0
              );
              const isCovered = recommendations.totalNeed === 0 || scheduledCoveredCount >= recommendations.totalNeed;
              const missingModalities = day.required_modalities.filter(
                (modality) => scheduledCountFor(modality.modality) < (modality.recommended_doctors || 0)
              );

              return (
                <div key={day.date} className="rounded-lg border border-slate-200 bg-white p-2.5">
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{day.weekday}</div>
                      <div className="text-xs text-slate-500">{formatDateFullLabel(day.date)}</div>
                    </div>
                    <span
                      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-1 text-xs font-semibold ${
                        isCovered
                          ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
                          : 'bg-amber-50 text-amber-700 ring-1 ring-amber-100'
                      }`}
                    >
                      {isCovered ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
                      {scheduledCoveredCount}/{recommendations.totalNeed || day.min_doctors}
                    </span>
                  </div>

                  <div className="mb-2 flex flex-wrap gap-1.5">
                    {day.required_modalities.map((modality) => {
                      const needCount = modality.recommended_doctors || 0;
                      const selected = recommendations.byModality.get(modality.modality) || [];
                      const scheduledCount = scheduledCountFor(modality.modality);
                      const missingCount = Math.max(0, needCount - scheduledCount);

                      return (
                        <span
                          key={`${day.date}-${modality.modality}`}
                          className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs font-medium ${
                            missingCount === 0
                              ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
                              : selected.length > 0
                                ? 'bg-slate-100 text-slate-700'
                                : 'bg-amber-50 text-amber-800 ring-1 ring-amber-100'
                          }`}
                          title={`Нужно ${needCount}; выставлено ${scheduledCount}`}
                        >
                          {modality.modality}
                          <span className="font-semibold">{scheduledCount}/{needCount}</span>
                        </span>
                      );
                    })}
                  </div>

                  {recommendations.doctors.length > 0 ? (
                    <div className="space-y-1">
                      {recommendations.doctors.slice(0, 4).map((item) => {
                        const doctorId = getDoctorNumericId(item.doctor);
                        const capacity = getDoctorCapacity(item.doctor);
                        const canSchedule = Boolean(onScheduleDoctor && doctorId !== null);

                        return (
                        <button
                          type="button"
                          key={`${day.date}-${getDoctorStableId(item.doctor)}`}
                          disabled={!canSchedule}
                          onClick={() => {
                            if (doctorId !== null) {
                              onScheduleDoctor?.(doctorId, day.date, capacity);
                            }
                          }}
                          className={`flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition hover:bg-blue-50 hover:ring-1 hover:ring-blue-200 disabled:cursor-default disabled:hover:bg-slate-50 disabled:hover:ring-0 ${
                            item.isScheduled ? 'bg-blue-50 ring-1 ring-blue-100' : 'bg-slate-50'
                          }`}
                          title={canSchedule ? 'Добавить или изменить смену врача на этот день' : undefined}
                        >
                          <div className="min-w-0">
                            <div className="truncate font-medium text-slate-900">
                              {getDoctorName(item.doctor)}
                            </div>
                            <div className="truncate text-[11px] text-slate-500">
                              {item.modalities.join(', ')} · {formatMetric(item.monthlyLoad, 1)} УП/мес.
                            </div>
                          </div>
                          <div className="flex shrink-0 items-center gap-1">
                            {item.isScheduled && (
                              <span className="rounded-full bg-blue-600 px-2 py-0.5 text-[10px] font-semibold text-white">
                                выставлен
                              </span>
                            )}
                            {capacity > 0 && (
                              <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 ring-1 ring-slate-200">
                                {formatMetric(capacity, 1)} УП
                              </span>
                            )}
                          </div>
                        </button>
                        );
                      })}
                      {recommendations.doctors.length > 4 && (
                        <div className="px-2 text-[11px] text-slate-500">
                          +{recommendations.doctors.length - 4} врачей в альтернативах
                        </div>
                      )}
                    </div>
                  ) : recommendations.totalNeed === 0 ? (
                    <div className="rounded-lg bg-emerald-50 px-3 py-2 text-xs font-medium text-emerald-800">
                      По прогнозу дополнительная смена не требуется.
                    </div>
                  ) : (
                    <div className="rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                      Нет подходящих активных врачей под нужные модальности.
                    </div>
                  )}

                  {missingModalities.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5 border-t border-slate-100 pt-2">
                      {missingModalities.slice(0, 2).map((modality) => (
                        <button
                          type="button"
                          key={`${day.date}-missing-${modality.modality}`}
                          onClick={() =>
                            setMissingRequest({
                              date: day.date,
                              weekday: day.weekday,
                              modality: modality.modality,
                              candidates: buildCandidatesForModality(
                                day,
                                modality.modality,
                                doctors,
                                schedules,
                                doctorMonthlyCompletedLoad
                              ),
                            })
                          }
                          className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-100 transition hover:bg-amber-100"
                        >
                          Закрыть {modality.modality}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
      {missingRequest && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4">
          <div className="max-h-[95dvh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white shadow-lg sm:rounded-xl">
            <div className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-slate-200 bg-white p-5">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Закрыть модальность</h3>
                <p className="mt-1 text-sm text-slate-500">
                  {missingRequest.modality} · {missingRequest.weekday}, {formatDateFullLabel(missingRequest.date)}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setMissingRequest(null)}
                className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
              >
                <X size={22} />
              </button>
            </div>

            <div className="space-y-2 p-4">
              {missingRequest.candidates.length > 0 ? (
                missingRequest.candidates.map((item) => {
                  const doctorId = getDoctorNumericId(item.doctor);
                  const capacity = getDoctorCapacity(item.doctor);

                  return (
                    <button
                      key={`${missingRequest.date}-${missingRequest.modality}-${getDoctorStableId(item.doctor)}`}
                      type="button"
                      disabled={doctorId === null}
                      onClick={() => {
                        if (doctorId !== null) {
                          onScheduleDoctor?.(doctorId, missingRequest.date, capacity);
                          setMissingRequest(null);
                        }
                      }}
                      className="flex w-full items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-left transition hover:border-blue-200 hover:bg-blue-50 disabled:cursor-default disabled:opacity-60"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-slate-900">
                          {getDoctorName(item.doctor)}
                        </div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {getDoctorModalities(item.doctor).slice(0, 4).map((modality) => (
                            <span
                              key={`${getDoctorStableId(item.doctor)}-${modality}`}
                              className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                                modalityMatchesDoctor(missingRequest.modality, item.doctor) &&
                                modalityToKey(modality) === modalityToKey(missingRequest.modality)
                                  ? 'bg-blue-50 text-blue-700 ring-1 ring-blue-100'
                                  : 'bg-slate-100 text-slate-600'
                              }`}
                            >
                              {modality}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1 text-xs">
                        {item.isScheduled && (
                          <span className="rounded-full bg-blue-600 px-2 py-0.5 font-semibold text-white">
                            выставлен
                          </span>
                        )}
                        <span className="text-slate-600">{formatMetric(item.monthlyLoad, 1)} УП/мес.</span>
                        {capacity > 0 && <span className="text-slate-500">{formatMetric(capacity, 1)} УП/день</span>}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                  Нет активных врачей, которые покрывают выбранную модальность.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {!loading && !error && days.length === 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Для выбранного диапазона не удалось построить прогноз.
        </div>
      )}

      {!loading && !error && days.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 bg-slate-50/80 px-4 py-3">
            <div className="font-semibold text-slate-900">
              {formatDateFullLabel(forecast?.date_from)} — {formatDateFullLabel(forecast?.date_to)}
            </div>
            <div className="text-xs text-slate-600 mt-1">
              Исследований: {formatStudiesCount(summary?.total_expected_studies)} · УП: {formatMetric(summary?.total_expected_up, 2)}
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" style={{ minWidth: '920px' }}>
              <thead className="bg-white border-b border-slate-200">
                <tr className="text-slate-600">
                  <th className="px-4 py-3 font-medium">День</th>
                  <th className="px-4 py-3 font-medium">Ожидается</th>
                  <th className="px-4 py-3 font-medium">УП</th>
                  <th className="px-4 py-3 font-medium">Врачей в графике</th>
                  <th className="px-4 py-3 font-medium">Рекомендуется врачей</th>
                  <th className="px-4 py-3 font-medium">Разрыв</th>
                  <th className="px-4 py-3 font-medium">Модальности</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {days.map((day) => (
                  <tr key={day.date} className="hover:bg-slate-50">
                    <td className="px-4 py-3 align-top">
                      <div className="font-medium text-slate-900">{day.weekday}</div>
                      <div className="text-xs text-slate-500">{formatDateFullLabel(day.date)}</div>
                    </td>
                    <td className="px-4 py-3 align-top font-medium text-slate-900">{formatStudiesCount(day.expected_studies_total)}</td>
                    <td className="px-4 py-3 align-top text-slate-900">{formatMetric(day.expected_up_total, 2)}</td>
                    <td className="px-4 py-3 align-top text-slate-900">{day.scheduled_doctors}</td>
                    <td className="px-4 py-3 align-top font-semibold text-slate-900">{day.min_doctors}</td>
                    <td className="px-4 py-3 align-top">
                      <span className={`inline-flex px-2 py-1 rounded-full text-xs font-medium ${
                        day.gap_to_schedule > 0
                          ? 'bg-amber-100 text-amber-700'
                          : day.gap_to_schedule < 0
                            ? 'bg-blue-100 text-blue-700'
                            : 'bg-slate-100 text-slate-700'
                      }`}>
                        {day.gap_to_schedule > 0 ? `+${day.gap_to_schedule}` : day.gap_to_schedule}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top">
                      <div className="flex flex-wrap gap-1">
                        {day.required_modalities.length > 0 ? day.required_modalities.map((item) => (
                          <span
                            key={`${day.date}-${item.modality}`}
                            className="inline-flex px-2 py-1 rounded-full text-xs bg-slate-100 text-slate-700"
                            title={`Ожидается ${formatStudiesCount(item.expected_studies)} исследований / ${formatMetric(item.expected_up, 2)} УП`}
                          >
                            {item.modality}: {formatStudiesCount(item.expected_studies)}
                          </span>
                        )) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
        </div>
      )}
    </div>
  );
};
