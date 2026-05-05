import React, { useState, useEffect } from "react";
import { dashboardApi } from "../../services/api";
import type { DashboardStats } from "../../types";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Filter,
  Target,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";

const COLORS = ["#3b82f6", "#22c55e", "#f97316"];

const metricCardClass =
  "rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 transition hover:-translate-y-0.5 hover:shadow-md hover:shadow-slate-200/70 sm:p-5";

export const ReportsView: React.FC = () => {
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

  const formatInputDate = (d: Date) => d.toISOString().split("T")[0];

  const initialDateFrom = formatInputDate(firstDay);
  const initialDateTo = formatInputDate(today);

  const [loading, setLoading] = useState(true);

  const [dateFrom, setDateFrom] = useState<string>(initialDateFrom);
  const [dateTo, setDateTo] = useState<string>(initialDateTo);

  const [appliedDateFrom, setAppliedDateFrom] = useState<string>(initialDateFrom);
  const [appliedDateTo, setAppliedDateTo] = useState<string>(initialDateTo);

  const [kpiData, setKpiData] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [pieData, setPieData] = useState<any[]>([]);

  const dailyUpStats = kpiData?.doctor_daily_up_stats ?? { median: 0, min: 0, max: 0 };

  const formatUp = (value?: number | null) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "—";
    }
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
  };

  useEffect(() => {
    if (appliedDateFrom && appliedDateTo) {
      loadReportsData();
    }
  }, [appliedDateFrom, appliedDateTo]);

  const handleApplyFilters = () => {
    setAppliedDateFrom(dateFrom);
    setAppliedDateTo(dateTo);
  };

  const loadReportsData = async () => {
    try {
      setLoading(true);

      const [stats, chart] = await Promise.all([
        dashboardApi.getStats(appliedDateFrom, appliedDateTo),
        dashboardApi.getChartData(appliedDateFrom, appliedDateTo),
      ]);

      setKpiData(stats);
      setChartData(chart || []);

      const normalStudies = Math.max(
        0,
        stats.total_studies - stats.cito_studies - stats.asap_studies
      );

      setPieData([
        { name: "CITO", value: stats.cito_studies },
        { name: "ASAP", value: stats.asap_studies },
        { name: "Обычные", value: normalStudies },
      ]);
    } catch (err) {
      console.error("Error loading reports:", err);
      setKpiData(null);
      setChartData([]);
      setPieData([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-2">
        <div className="inline-flex w-fit items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-blue-700">
          Отчёты
        </div>
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950 md:text-3xl">
            Аналитика работы службы
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">
            Сводные показатели, динамика исследований и нагрузка врачей за выбранный период.
          </p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto] lg:items-end">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Период от
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-slate-700">
              Период до
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
            />
          </div>

          <button
            onClick={handleApplyFilters}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-blue-200 transition hover:bg-blue-700 lg:w-auto"
          >
            <Filter size={16} />
            Применить
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-2xl border border-slate-200/80 bg-white/95 p-10 shadow-sm shadow-slate-100/70">
          <div className="text-sm text-slate-500">Загрузка отчётов...</div>
        </div>
      ) : !kpiData ? (
        <div className="rounded-2xl border border-red-200 bg-white p-10 text-center text-sm font-medium text-red-600 shadow-sm">
          Не удалось загрузить отчёты
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
                  <Target size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Всего исследований</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {kpiData.total_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-green-50 text-green-600">
                  <CheckCircle2 size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Выполнено</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {kpiData.completed_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
                  <Clock size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Ожидают назначения</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {kpiData.pending_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-purple-50 text-purple-600">
                  <TrendingUp size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Средняя нагрузка</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {kpiData.avg_load_per_doctor}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-cyan-50 text-cyan-600">
                  <BarChart3 size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Медиана УП в день</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {formatUp(dailyUpStats.median)}
                  </div>
                </div>
              </div>
            </div>

            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-rose-50 text-rose-600">
                  <TrendingDown size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Минимум УП в день</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {formatUp(dailyUpStats.min)}
                  </div>
                </div>
              </div>
            </div>

            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                  <Activity size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Максимум УП в день</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {formatUp(dailyUpStats.max)}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
              <div className="mb-4">
                <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                  Динамика исследований
                </h3>
                <p className="text-sm text-slate-500">План и фактические значения по дням.</p>
              </div>
              <div className="h-64 sm:h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ left: -16, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="plan" name="План" fill="#3b82f6" />
                    <Bar dataKey="actual" name="Факт" fill="#22c55e" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
              <div className="mb-4">
                <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                  Распределение по приоритетам
                </h3>
                <p className="text-sm text-slate-500">Доля CITO, ASAP и обычных исследований.</p>
              </div>
              <div className="h-64 sm:h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" outerRadius="72%" label>
                      {pieData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
            <div className="mb-4">
              <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                Выполненные исследования по врачам
              </h3>
              <p className="text-sm text-slate-500">
                Таблица сохранена полностью, на телефоне доступна горизонтальная прокрутка.
              </p>
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <div className="max-h-[420px] min-w-[720px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Врач</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Исследований</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">УП</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Среднее УП/день</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {kpiData.doctor_performance.map((row) => (
                      <tr key={row.doctor_id} className="transition hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-900">{row.doctor_name}</td>
                        <td className="px-4 py-3 text-slate-600">{row.completed_studies}</td>
                        <td className="px-4 py-3 text-slate-600">{formatUp(row.completed_up)}</td>
                        <td className="px-4 py-3 text-slate-600">{formatUp(row.avg_up_per_day)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
