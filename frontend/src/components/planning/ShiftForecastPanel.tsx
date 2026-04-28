import React, { useEffect, useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { ResponsiveContainer, CartesianGrid, Tooltip, XAxis, YAxis, BarChart, Bar, LineChart, Line } from 'recharts';

import { forecastApi, schedulesApi } from '../../services/api';
import type { ForecastCompareResponse, ForecastCompareResult, ShiftForecastResponse } from '../../types';

interface ShiftForecastPanelProps {
  refreshKey?: number;
}

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

export const ShiftForecastPanel: React.FC<ShiftForecastPanelProps> = ({ refreshKey = 0 }) => {
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
  const [comparison, setComparison] = useState<ForecastCompareResponse | null>(null);
  const [selectedCompareMethod, setSelectedCompareMethod] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [compareLoading, setCompareLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [compareError, setCompareError] = useState<string | null>(null);

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
    } catch (err: any) {
      console.error('Error loading shift forecast:', err);
      setError(err?.message || 'Не удалось загрузить прогноз.');
      setForecast(null);
    } finally {
      setLoading(false);
    }
  };

  const loadComparison = async () => {
    try {
      setCompareLoading(true);
      setCompareError(null);
      const data = await forecastApi.compareMethods({ evaluation_days: 7 });
      setComparison(data);
      setSelectedCompareMethod(data.results[0]?.method || null);
    } catch (err: any) {
      console.error('Error loading forecast comparison:', err);
      setCompareError(err?.message || 'Не удалось загрузить сравнение моделей.');
      setComparison(null);
      setSelectedCompareMethod(null);
    } finally {
      setCompareLoading(false);
    }
  };

  useEffect(() => {
    loadForecast(appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate);
  }, [appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate, refreshKey]);

  useEffect(() => {
    loadComparison();
  }, [refreshKey]);

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
  const compareRows = comparison?.results || [];
  const selectedCompareResult: ForecastCompareResult | undefined =
    compareRows.find((item) => item.method === selectedCompareMethod) || compareRows[0];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 md:p-5 space-y-4">
      <div className="flex flex-col lg:flex-row lg:justify-between lg:items-end gap-4">
        <div>
          <div className="text-lg font-semibold text-slate-900">Прогноз потребности в специалистах</div>
          <div className="text-sm text-slate-600 mt-1">
            Выберите диапазон дат прогноза. Расчёт строится по всем доступным исследованиям в БД и показывает ожидаемое число исследований,
            рекомендуемое количество врачей и ключевые модальности по дням.
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-2">
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              Прогноз от
              <input
                type="date"
                value={inputDateFrom}
                onChange={(e) => setInputDateFrom(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm bg-white font-normal text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              Прогноз до
              <input
                type="date"
                value={inputDateTo}
                onChange={(e) => setInputDateTo(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm bg-white font-normal text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              История от
              <input
                type="date"
                value={inputHistoryStartDate}
                onChange={(e) => setInputHistoryStartDate(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm bg-white font-normal text-slate-900"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
              История до
              <input
                type="date"
                value={inputHistoryEndDate}
                onChange={(e) => setInputHistoryEndDate(e.target.value)}
                className="px-3 py-2 border border-slate-300 rounded-md text-sm bg-white font-normal text-slate-900"
              />
            </label>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
            <button
              onClick={handleApply}
              className="px-3 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700"
            >
              Построить прогноз
            </button>
            <button
              onClick={() => loadForecast(appliedDateFrom, appliedDateTo, appliedHistoryStartDate, appliedHistoryEndDate)}
              className="px-3 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 inline-flex items-center justify-center gap-1.5"
            >
              <RefreshCw size={16} />
              Обновить
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <div className="bg-slate-50 rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500 mb-1">Ожидается исследований</div>
          <div className="text-xl font-bold text-slate-900">{loading ? '…' : formatMetric(summary?.total_expected_studies, 1)}</div>
        </div>
        <div className="bg-slate-50 rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500 mb-1">Ожидаемый объём, УП</div>
          <div className="text-xl font-bold text-slate-900">{loading ? '…' : formatMetric(summary?.total_expected_up, 2)}</div>
        </div>
        <div className="bg-slate-50 rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500 mb-1">Пиковая потребность во врачах</div>
          <div className="text-xl font-bold text-slate-900">{loading ? '…' : summary?.max_min_doctors_per_shift ?? 0}</div>
        </div>
        <div className="bg-slate-50 rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500 mb-1">Основные модальности</div>
          <div className="text-sm font-medium text-slate-900 leading-6">
            {loading ? '…' : summary?.modalities?.join(', ') || '—'}
          </div>
        </div>
      </div>

      <div className="text-xs md:text-sm text-slate-600 bg-slate-50 px-4 py-2 rounded-md">
        {forecast?.message || 'Прогноз будет загружен после выбора диапазона.'}
      </div>

      {forecast?.history_start_date && forecast?.history_end_date && (
        <div className="text-xs text-slate-500">
          Исторический диапазон для обучения прогноза: {formatDateFullLabel(forecast.history_start_date)} — {formatDateFullLabel(forecast.history_end_date)}.
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && !error && chartData.length > 0 && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="rounded-xl border border-slate-200 p-4">
            <div className="font-semibold text-slate-900 mb-1">График ожидаемого числа исследований</div>
            <div className="text-xs text-slate-500 mb-4">Сколько исследований прогнозируется на каждый день выбранного диапазона.</div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip formatter={(value: number) => [formatMetric(value, 1), 'Исследований']} />
                  <Bar dataKey="expected_studies_total" name="Исследований" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4">
            <div className="font-semibold text-slate-900 mb-1">График рекомендуемого числа врачей</div>
            <div className="text-xs text-slate-500 mb-4">Сколько врачей рекомендуется на каждый день выбранного диапазона.</div>
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" />
                  <YAxis allowDecimals={false} />
                  <Tooltip formatter={(value: number) => [value, 'Врачей']} />
                  <Line type="monotone" dataKey="min_doctors" name="Врачей" stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}

      {!loading && !error && days.length === 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
          Для выбранного диапазона не удалось построить прогноз.
        </div>
      )}

      {!loading && !error && days.length > 0 && (
        <div className="border border-slate-200 rounded-xl overflow-hidden">
          <div className="bg-slate-50 px-4 py-3 border-b border-slate-200">
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
                          ? 'bg-red-100 text-red-700'
                          : day.gap_to_schedule < 0
                            ? 'bg-green-100 text-green-700'
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

      <div className="border border-slate-200 rounded-xl overflow-hidden">
        <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-semibold text-slate-900">Сравнение моделей прогноза</div>
            <div className="text-xs text-slate-600 mt-1">
              Holdout: {formatDateFullLabel(comparison?.evaluation_start_date)} — {formatDateFullLabel(comparison?.evaluation_end_date)} · обучение: {formatDateFullLabel(comparison?.training_start_date)} — {formatDateFullLabel(comparison?.training_end_date)}
            </div>
          </div>
          <button
            onClick={loadComparison}
            className="px-3 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 inline-flex items-center gap-1.5 self-start md:self-auto"
          >
            <RefreshCw size={16} />
            Обновить
          </button>
        </div>

        {compareError && (
          <div className="m-4 bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">
            {compareError}
          </div>
        )}

        {!compareError && (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" style={{ minWidth: '860px' }}>
                <thead className="bg-white border-b border-slate-200">
                  <tr className="text-slate-600">
                    <th className="px-4 py-3 font-medium">Место</th>
                    <th className="px-4 py-3 font-medium">Модель</th>
                    <th className="px-4 py-3 font-medium text-right">MAE, УП</th>
                    <th className="px-4 py-3 font-medium text-right">MAE, исследований</th>
                    <th className="px-4 py-3 font-medium text-right">MAPE, УП</th>
                    <th className="px-4 py-3 font-medium text-right">MAPE, исследований</th>
                    <th className="px-4 py-3 font-medium text-right">Дней</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {compareLoading && (
                    <tr>
                      <td className="px-4 py-6 text-slate-500" colSpan={7}>Загрузка сравнения...</td>
                    </tr>
                  )}
                  {!compareLoading && compareRows.length === 0 && (
                    <tr>
                      <td className="px-4 py-6 text-slate-500" colSpan={7}>Нет данных для сравнения моделей.</td>
                    </tr>
                  )}
                  {!compareLoading && compareRows.map((row, index) => {
                    const isSelected = selectedCompareResult?.method === row.method;
                    return (
                      <tr
                        key={row.method}
                        onClick={() => setSelectedCompareMethod(row.method)}
                        className={`cursor-pointer hover:bg-blue-50 ${isSelected ? 'bg-blue-50' : 'bg-white'}`}
                      >
                        <td className="px-4 py-3 align-top">
                          <span className={`inline-flex h-6 min-w-6 items-center justify-center rounded-full px-2 text-xs font-semibold ${
                            index === 0 ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-700'
                          }`}>
                            {index + 1}
                          </span>
                        </td>
                        <td className="px-4 py-3 align-top">
                          <div className="font-medium text-slate-900">{row.method_label}</div>
                          <div className="text-xs text-slate-500">{row.method}</div>
                        </td>
                        <td className="px-4 py-3 align-top text-right font-semibold text-slate-900">{formatMetric(row.mae_up, 2)}</td>
                        <td className="px-4 py-3 align-top text-right text-slate-900">{formatMetric(row.mae_studies, 2)}</td>
                        <td className="px-4 py-3 align-top text-right text-slate-900">
                          {row.mape_up_pct === null ? '—' : `${formatMetric(row.mape_up_pct, 2)}%`}
                        </td>
                        <td className="px-4 py-3 align-top text-right text-slate-900">
                          {row.mape_studies_pct === null ? '—' : `${formatMetric(row.mape_studies_pct, 2)}%`}
                        </td>
                        <td className="px-4 py-3 align-top text-right text-slate-900">{row.days_evaluated}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {selectedCompareResult && (
              <div className="border-t border-slate-200">
                <div className="px-4 py-3 bg-slate-50 border-b border-slate-200">
                  <div className="font-semibold text-slate-900">Детализация по дням: {selectedCompareResult.method_label}</div>
                  <div className="text-xs text-slate-600 mt-1">
                    Прогноз против факта на последней неделе, без обучения на этой неделе.
                  </div>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm" style={{ minWidth: '920px' }}>
                    <thead className="bg-white border-b border-slate-200">
                      <tr className="text-slate-600">
                        <th className="px-4 py-3 font-medium">Дата</th>
                        <th className="px-4 py-3 font-medium text-right">Прогноз, исслед.</th>
                        <th className="px-4 py-3 font-medium text-right">Факт, исслед.</th>
                        <th className="px-4 py-3 font-medium text-right">Ошибка, исслед.</th>
                        <th className="px-4 py-3 font-medium text-right">Прогноз, УП</th>
                        <th className="px-4 py-3 font-medium text-right">Факт, УП</th>
                        <th className="px-4 py-3 font-medium text-right">Ошибка, УП</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {selectedCompareResult.day_details.map((day) => (
                        <tr key={day.date} className="hover:bg-slate-50">
                          <td className="px-4 py-3 font-medium text-slate-900">{formatDateFullLabel(day.date)}</td>
                          <td className="px-4 py-3 text-right text-slate-900">{formatMetric(day.forecast_studies, 1)}</td>
                          <td className="px-4 py-3 text-right text-slate-900">{formatMetric(day.actual_studies, 1)}</td>
                          <td className="px-4 py-3 text-right font-medium text-slate-900">{formatMetric(day.abs_error_studies, 1)}</td>
                          <td className="px-4 py-3 text-right text-slate-900">{formatMetric(day.forecast_up, 2)}</td>
                          <td className="px-4 py-3 text-right text-slate-900">{formatMetric(day.actual_up, 2)}</td>
                          <td className="px-4 py-3 text-right font-medium text-slate-900">{formatMetric(day.abs_error_up, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
