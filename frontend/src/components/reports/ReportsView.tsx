import React, { useState, useEffect } from "react";
import { dashboardApi } from "../../services/api";
import { Filter, TrendingUp, CheckCircle2, Target, Clock } from "lucide-react";

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

interface KPIData {
  total_studies: number;
  completed_studies: number;
  pending_studies: number;
  active_doctors: number;
  avg_load_per_doctor: number;
  cito_studies: number;
  asap_studies: number;
}

interface DepartmentSummary {
  department: string;
  planUp: number;
  actualUp: number;
  fulfillment: number;
  studies: number;
}

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

  const [kpiData, setKpiData] = useState<KPIData | null>(null);
  const [chartData, setChartData] = useState<any[]>([]);
  const [pieData, setPieData] = useState<any[]>([]);
  const [departmentSummary, setDepartmentSummary] = useState<DepartmentSummary[]>([]);

  const COLORS = ["#3b82f6", "#22c55e", "#f97316"];

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

      setDepartmentSummary([
        {
          department: "Все исследования",
          planUp: stats.total_studies,
          actualUp: stats.completed_studies,
          fulfillment:
            stats.total_studies > 0
              ? Math.round((stats.completed_studies / stats.total_studies) * 100)
              : 0,
          studies: stats.total_studies,
        },
      ]);
    } catch (err) {
      console.error("Error loading reports:", err);
      setKpiData(null);
      setChartData([]);
      setPieData([]);
      setDepartmentSummary([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
        <div className="flex flex-col lg:flex-row gap-4 lg:items-end">
          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Период от
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
            />
          </div>

          <div className="flex-1">
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Период до
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2"
            />
          </div>

          <button
            onClick={handleApplyFilters}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700"
          >
            <Filter size={16} />
            Применить
          </button>
        </div>
      </div>

      {loading ? (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-10 flex items-center justify-center">
          <div className="text-slate-500">Загрузка отчётов...</div>
        </div>
      ) : !kpiData ? (
        <div className="bg-white rounded-2xl border border-red-200 shadow-sm p-10 text-center text-red-600">
          Не удалось загрузить отчёты
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600">
                  <Target size={22} />
                </div>
                <div>
                  <div className="text-sm text-slate-500">Всего исследований</div>
                  <div className="text-2xl font-bold text-slate-900">
                    {kpiData.total_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-green-50 flex items-center justify-center text-green-600">
                  <CheckCircle2 size={22} />
                </div>
                <div>
                  <div className="text-sm text-slate-500">Выполнено</div>
                  <div className="text-2xl font-bold text-slate-900">
                    {kpiData.completed_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600">
                  <Clock size={22} />
                </div>
                <div>
                  <div className="text-sm text-slate-500">Ожидают назначения</div>
                  <div className="text-2xl font-bold text-slate-900">
                    {kpiData.pending_studies}
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-purple-50 flex items-center justify-center text-purple-600">
                  <TrendingUp size={22} />
                </div>
                <div>
                  <div className="text-sm text-slate-500">Средняя нагрузка</div>
                  <div className="text-2xl font-bold text-slate-900">
                    {kpiData.avg_load_per_doctor}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">
                Динамика исследований
              </h3>
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="name" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="plan" name="План" fill="#3b82f6" />
                    <Bar dataKey="actual" name="Факт" fill="#22c55e" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
              <h3 className="text-lg font-semibold text-slate-900 mb-4">
                Распределение по приоритетам
              </h3>
              <div className="h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      outerRadius={120}
                      label
                    >
                      {pieData.map((_, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={COLORS[index % COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">
              Сводка по отделению
            </h3>

            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">
                      Отделение
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">
                      План
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">
                      Факт
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">
                      Выполнение
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-slate-600">
                      Исследований
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {departmentSummary.map((row) => (
                    <tr key={row.department} className="border-t border-slate-100">
                      <td className="px-4 py-3 text-slate-800 font-medium">
                        {row.department}
                      </td>
                      <td className="px-4 py-3 text-slate-600">{row.planUp}</td>
                      <td className="px-4 py-3 text-slate-600">{row.actualUp}</td>
                      <td className="px-4 py-3 text-slate-600">{row.fulfillment}%</td>
                      <td className="px-4 py-3 text-slate-600">{row.studies}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
};