import React, { useState, useEffect } from "react";
import { dashboardApi } from "../../services/api";
import type { DashboardStats } from "../../types";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Download,
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

const COLORS = ["#2563eb", "#64748b", "#d97706"];

const metricCardClass =
  "rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 transition hover:-translate-y-0.5 hover:shadow-md hover:shadow-slate-200/70 sm:p-5";

export const ReportsView: React.FC = () => {
  const [loading, setLoading] = useState(true);

  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");

  const [appliedDateFrom, setAppliedDateFrom] = useState<string>("");
  const [appliedDateTo, setAppliedDateTo] = useState<string>("");
  const [allDates, setAllDates] = useState(true);

  const [kpiData, setKpiData] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [pieData, setPieData] = useState<any[]>([]);

  const dailyUpStats = kpiData?.doctor_daily_up_stats ?? { median: 0, min: 0, max: 0 };
  const reportPeriodLabel = allDates
    ? "Все даты"
    : `${appliedDateFrom || "—"} — ${appliedDateTo || "—"}`;

  const formatUp = (value?: number | null) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "—";
    }
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
  };

  useEffect(() => {
    loadReportsData();
  }, [appliedDateFrom, appliedDateTo, allDates]);

  const handleApplyFilters = () => {
    const hasRange = Boolean(dateFrom && dateTo);
    setAllDates(!hasRange);
    setAppliedDateFrom(hasRange ? dateFrom : "");
    setAppliedDateTo(hasRange ? dateTo : "");
  };

  const handleResetToAllDates = () => {
    setDateFrom("");
    setDateTo("");
    setAppliedDateFrom("");
    setAppliedDateTo("");
    setAllDates(true);
  };

  const loadReportsData = async () => {
    try {
      setLoading(true);

      const [stats, chart] = await Promise.all([
        dashboardApi.getStats(appliedDateFrom, appliedDateTo, allDates),
        dashboardApi.getChartData(appliedDateFrom, appliedDateTo, allDates),
      ]);

      setKpiData(stats);
      setChartData(chart || []);

      const normalStudies = Math.max(
        0,
        stats.total_studies - stats.cito_studies - stats.asap_studies
      );

      setPieData([
        { name: "CITO", value: stats.cito_studies },
        { name: "Срочные", value: stats.asap_studies },
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

  const escapeCsvCell = (value: unknown) => {
    const text = String(value ?? "");
    return `"${text.replace(/"/g, '""')}"`;
  };

  const handleExportCsv = () => {
    if (!kpiData) return;

    const rows = [
      ["Отчёт РадПлан", reportPeriodLabel],
      [],
      ["Показатель", "Значение"],
      ["Всего исследований", kpiData.total_studies],
      ["Выполнено", kpiData.completed_studies],
      ["Ожидают назначения", kpiData.pending_studies],
      ["CITO", kpiData.cito_studies],
      ["Срочные", kpiData.asap_studies],
      ["Средняя нагрузка, УП", kpiData.avg_load_per_doctor],
      ["Медиана УП в день", dailyUpStats.median],
      ["Минимум УП в день", dailyUpStats.min],
      ["Максимум УП в день", dailyUpStats.max],
      [],
      ["Врач", "Выполнено исследований", "Выполнено УП", "Дней с выполнением", "Среднее УП/день", "Медиана УП/день", "Мин. УП/день", "Макс. УП/день"],
      ...kpiData.doctor_performance.map((row) => [
        row.doctor_name,
        row.completed_studies,
        row.completed_up,
        row.completed_days,
        row.avg_up_per_day,
        row.median_up_per_day,
        row.min_daily_completed_up,
        row.max_daily_completed_up,
      ]),
    ];

    const csv = `\uFEFF${rows.map((row) => row.map(escapeCsvCell).join(";")).join("\r\n")}`;
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `radplan-report-${allDates ? "all-dates" : `${appliedDateFrom}-${appliedDateTo}`}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-2">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950 md:text-3xl">
            Аналитика работы службы
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">Период: {reportPeriodLabel}</p>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr_auto_auto_auto] lg:items-end">
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
          <button
            onClick={handleResetToAllDates}
            className="inline-flex w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 lg:w-auto"
          >
            Все даты
          </button>
          <button
            onClick={handleExportCsv}
            disabled={!kpiData}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-semibold text-blue-700 transition hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 lg:w-auto"
          >
            <Download size={16} />
            Excel
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center rounded-2xl border border-slate-200/80 bg-white/95 p-10 shadow-sm shadow-slate-100/70">
          <div className="text-sm text-slate-500">Загрузка отчётов...</div>
        </div>
      ) : !kpiData ? (
        <div className="rounded-2xl border border-amber-200 bg-white p-10 text-center text-sm font-medium text-amber-600 shadow-sm">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-50 text-slate-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-50 text-slate-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-50 text-slate-600">
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
                    <Bar dataKey="plan" name="План" fill="#94a3b8" />
                    <Bar dataKey="actual" name="Факт" fill="#2563eb" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200/80 bg-white/95 p-4 shadow-sm shadow-slate-100/70 sm:p-5">
              <div className="mb-4">
                <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                  Распределение по приоритетам
                </h3>
                <p className="text-sm text-slate-500">Доля CITO, срочных и обычных исследований.</p>
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
            </div>

            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <div className="max-h-[420px] min-w-[920px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-10 bg-slate-50">
                    <tr>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Врач</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Исследований</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">УП</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Дней</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Среднее УП/день</th>
                      <th className="px-4 py-3 text-left font-semibold text-slate-600">Медиана</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {kpiData.doctor_performance.map((row) => (
                      <tr key={row.doctor_id} className="transition hover:bg-slate-50">
                        <td className="px-4 py-3 font-medium text-slate-900">{row.doctor_name}</td>
                        <td className="px-4 py-3 text-slate-600">{row.completed_studies}</td>
                        <td className="px-4 py-3 text-slate-600">{formatUp(row.completed_up)}</td>
                        <td className="px-4 py-3 text-slate-600">{row.completed_days}</td>
                        <td className="px-4 py-3 text-slate-600">{formatUp(row.avg_up_per_day)}</td>
                        <td className="px-4 py-3 text-slate-600">{formatUp(row.median_up_per_day)}</td>
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
