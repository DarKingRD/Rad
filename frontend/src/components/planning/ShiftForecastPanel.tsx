import React, { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, BarChart, Bar, LineChart, Line } from 'recharts';

import { schedulesApi } from '../../services/api';
import type { Doctor, ShiftForecastResponse } from '../../types';

interface ShiftForecastPanelProps {
  refreshKey?: number;
  doctors?: Doctor[];
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

const buildDayDoctorRecommendations = (day: ForecastDay, doctors: Doctor[]) => {
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

  const usedDoctors = new Set<string>();
  const recommendations = new Map<string, Doctor[]>();

  sortedModalities.forEach((modality) => {
    const needCount = modality.recommended_doctors || 0;
    const selected = (availableByModality.get(modality.modality) || [])
      .filter((doctor) => !usedDoctors.has(getDoctorStableId(doctor)))
      .slice(0, needCount);

    selected.forEach((doctor) => usedDoctors.add(getDoctorStableId(doctor)));
    recommendations.set(modality.modality, selected);
  });

  return recommendations;
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

export const ShiftForecastPanel: React.FC<ShiftForecastPanelProps> = ({ refreshKey = 0, doctors = []}) => {
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

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Ожидается исследований</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : formatMetric(summary?.total_expected_studies, 1)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Ожидаемый объём, УП</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : formatMetric(summary?.total_expected_up, 2)}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Пиковая потребность во врачах</div>
          <div className="text-xl font-bold tracking-tight text-slate-950">{loading ? '…' : summary?.max_min_doctors_per_shift ?? 0}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-3">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Основные модальности</div>
          <div className="text-sm font-medium text-slate-900 leading-6">
            {loading ? '…' : summary?.modalities?.join(', ') || '—'}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-xs text-slate-600 md:text-sm">
        {forecast?.message || 'Прогноз будет загружен после выбора диапазона.'}
      </div>

      {forecast?.history_start_date && forecast?.history_end_date && (
        <div className="text-xs text-slate-500">
          Исторический диапазон для обучения прогноза: {formatDateFullLabel(forecast.history_start_date)} — {formatDateFullLabel(forecast.history_end_date)}.
        </div>
      )}

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
                  <Tooltip formatter={(value: number) => [formatMetric(value, 1), 'Исследований']} />
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
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="font-semibold text-slate-900 mb-1">Кого поставить в смену</div>
          <div className="text-xs text-slate-500 mb-3">
            Подбор учитывает активных врачей и их модальности.
          </div>
          <div className="space-y-3">
            {days.map((day) => {
              const recommendations = buildDayDoctorRecommendations(day, doctors);

              return (
                <div key={day.date} className="border border-slate-200 rounded-lg p-3">
                  <div className="text-sm font-medium text-slate-900 mb-2">{day.weekday}, {day.label}</div>
                  <div className="space-y-2">
                    {day.required_modalities.map((modality) => {
                      const needCount = modality.recommended_doctors || 0;
                      const selected = recommendations.get(modality.modality) || [];
                      const missingCount = Math.max(0, needCount - selected.length);

                      return (
                        <div key={`${day.date}-${modality.modality}`} className="rounded-xl bg-white px-3 py-2 text-sm">
                          <span className="font-medium text-slate-800">{modality.modality}</span>: нужно <span className="font-semibold">{needCount}</span>
                          {selected.length > 0 ? (
                            <span className="text-slate-600"> · желательно вызвать: {selected.map(getDoctorName).join(', ')}</span>
                          ) : (
                            <span className="text-amber-700"> · нет подходящих активных врачей</span>
                          )}
                          {missingCount > 0 && selected.length > 0 && (
                            <span className="text-amber-700"> · не хватает: {missingCount}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
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
              Исследований: {formatMetric(summary?.total_expected_studies, 1)} · УП: {formatMetric(summary?.total_expected_up, 2)}
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
                    <td className="px-4 py-3 align-top font-medium text-slate-900">{formatMetric(day.expected_studies_total, 1)}</td>
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
                            title={`Ожидается ${formatMetric(item.expected_studies, 1)} исследований / ${formatMetric(item.expected_up, 2)} УП`}
                          >
                            {item.modality}: {formatMetric(item.expected_studies, 1)}
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
