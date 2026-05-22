import React, { useMemo, useState, useEffect } from "react";
import { dashboardApi } from "../../services/api";
import type { ChartPoint, DashboardStats } from "../../types";
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

const PRIORITY_COLORS: Record<string, string> = {
  "Обычные": "#94a3b8",
  "Срочные": "#2563eb",
  "CITO": "#d97706",
};

const MODALITY_COLORS = ["#2563eb", "#0f766e", "#7c3aed", "#d97706", "#475569", "#db2777", "#16a34a"];

type PieSegment = {
  name: string;
  value: number;
};

const metricCardClass =
  "rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5";

export const ReportsView: React.FC = () => {
  const [loading, setLoading] = useState(true);

  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");

  const [appliedDateFrom, setAppliedDateFrom] = useState<string>("");
  const [appliedDateTo, setAppliedDateTo] = useState<string>("");
  const [allDates, setAllDates] = useState(true);

  const [kpiData, setKpiData] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [pieData, setPieData] = useState<PieSegment[]>([]);

  const dailyUpStats = kpiData?.doctor_daily_up_stats ?? { median: 0, min: 0, max: 0 };
  const modalityBreakdown = kpiData?.modality_breakdown ?? [];
  const modalityChartData = useMemo(
    () =>
      modalityBreakdown.map((item, index) => ({
        ...item,
        color: MODALITY_COLORS[index % MODALITY_COLORS.length],
      })),
    [modalityBreakdown]
  );
  const completionRate = kpiData?.total_studies
    ? Math.round((kpiData.completed_studies / kpiData.total_studies) * 100)
    : 0;
  const reportPeriodLabel = allDates
    ? "Все даты"
    : `${appliedDateFrom || "—"} — ${appliedDateTo || "—"}`;

  const formatUp = (value?: number | null) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "—";
    }
    return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
  };

  const formatCount = (value?: number | null) =>
    new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value || 0);

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

  const formatCsvNumber = (value?: number | null, fractionDigits = 3) => {
    if (value === null || value === undefined || Number.isNaN(value)) {
      return "";
    }

    if (Number.isInteger(value)) {
      return String(value);
    }

    return value
      .toFixed(fractionDigits)
      .replace(/0+$/, "")
      .replace(/\.$/, "")
      .replace(".", ",");
  };

  const formatCsvPercent = (value?: number | null) => {
    const formatted = formatCsvNumber(value, 2);
    return formatted ? `${formatted}%` : "";
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
      ["Средняя нагрузка, УП", formatCsvNumber(kpiData.avg_load_per_doctor)],
      ["Медиана УП в день", formatCsvNumber(dailyUpStats.median)],
      ["Минимум УП в день", formatCsvNumber(dailyUpStats.min)],
      ["Максимум УП в день", formatCsvNumber(dailyUpStats.max)],
      ["Процент выполнения", `${completionRate}%`],
      [],
      ["Модальность", "Исследований", "Доля", "Выполнено", "Ожидает назначения", "УП всего", "УП выполнено", "Процент выполнения"],
      ...modalityBreakdown.map((row) => [
        row.modality,
        row.studies_count,
        formatCsvPercent(row.share_percent),
        row.completed_studies,
        row.pending_studies,
        formatCsvNumber(row.total_up),
        formatCsvNumber(row.completed_up),
        formatCsvPercent(row.completion_rate_percent),
      ]),
      [],
      ["Врач", "Выполнено исследований", "Выполнено УП", "Дней с выполнением", "Среднее УП/день", "Медиана УП/день", "Мин. УП/день", "Макс. УП/день"],
      ...kpiData.doctor_performance.map((row) => [
        row.doctor_name,
        row.completed_studies,
        formatCsvNumber(row.completed_up),
        row.completed_days,
        formatCsvNumber(row.avg_up_per_day),
        formatCsvNumber(row.median_up_per_day),
        formatCsvNumber(row.min_daily_completed_up),
        formatCsvNumber(row.max_daily_completed_up),
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
            Отчёты службы
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">Период: {reportPeriodLabel}</p>
        </div>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
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
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 lg:w-auto"
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
        <div className="flex items-center justify-center rounded-xl border border-slate-200 bg-white p-10 shadow-sm">
          <div className="text-sm text-slate-500">Загрузка отчётов...</div>
        </div>
      ) : !kpiData ? (
        <div className="rounded-xl border border-amber-200 bg-white p-10 text-center text-sm font-medium text-amber-600 shadow-sm">
          Не удалось загрузить отчёты
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  <TrendingUp size={22} />
                </div>
                <div className="min-w-0">
                  <div className="text-sm text-slate-500">Выполнение потока</div>
                  <div className="truncate text-2xl font-bold text-slate-950">
                    {completionRate}%
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div className={metricCardClass}>
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
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
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
              <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                    Динамика исследований
                  </h3>
                  <p className="text-sm text-slate-500">Поступившие и выполненные исследования по дням.</p>
                </div>
                <div className="flex space-x-2 text-xs">
                  <span className="flex items-center"><span className="mr-1 h-2 w-2 rounded-full bg-slate-400"></span>Поступило</span>
                  <span className="flex items-center"><span className="mr-1 h-2 w-2 rounded-full bg-blue-500"></span>Выполнено</span>
                </div>
              </div>
              <div className="h-64 sm:h-[340px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ left: -16, right: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="plan" name="Поступило" fill="#94a3b8" />
                    <Bar dataKey="actual" name="Выполнено" fill="#2563eb" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
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
                      {pieData.map((entry) => (
                        <Cell key={`cell-${entry.name}`} fill={PRIORITY_COLORS[entry.name]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
            <div className="mb-4">
              <div>
                <h3 className="text-base font-semibold text-slate-950 sm:text-lg">
                  Распределение по основным модальностям
                </h3>
                <p className="text-sm text-slate-500">
                  Объём потока, очередь и УП по типам исследований.
                </p>
              </div>
            </div>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(520px,0.9fr)]">
              <div className="h-72 sm:h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={modalityChartData}
                    layout="vertical"
                    margin={{ left: 8, right: 28, top: 8, bottom: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="modality"
                      width={150}
                      tick={{ fontSize: 12 }}
                    />
                    <Tooltip
                      formatter={(value: number, name: string) => [
                        name === "УП" ? formatUp(value) : formatCount(value),
                        name,
                      ]}
                    />
                    <Bar dataKey="studies_count" name="Исследований" radius={[0, 6, 6, 0]}>
                      {modalityChartData.map((entry) => (
                        <Cell key={`modality-${entry.modality}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="overflow-x-auto rounded-xl border border-slate-200">
                <table className="w-full min-w-[520px] text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-3 py-3 text-left font-semibold text-slate-600">Модальность</th>
                      <th className="px-3 py-3 text-right font-semibold text-slate-600">Доля</th>
                      <th className="px-3 py-3 text-right font-semibold text-slate-600">Иссл.</th>
                      <th className="px-3 py-3 text-right font-semibold text-slate-600">УП</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {modalityBreakdown.map((row) => (
                      <tr key={row.modality} className="hover:bg-slate-50">
                        <td className="px-3 py-3 font-medium text-slate-900">{row.modality}</td>
                        <td className="px-3 py-3 text-right text-slate-600">{formatUp(row.share_percent)}%</td>
                        <td className="px-3 py-3 text-right text-slate-600">{formatCount(row.studies_count)}</td>
                        <td className="px-3 py-3 text-right text-slate-600">{formatUp(row.total_up)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
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
