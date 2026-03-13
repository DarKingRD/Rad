import React, { useState, useEffect } from "react"
import { dashboardApi } from "../../services/api"
import { Filter, TrendingUp, CheckCircle2, Target, Clock } from "lucide-react"

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
} from "recharts"

interface KPIData {
  total_studies: number
  completed_studies: number
  pending_studies: number
  active_doctors: number
  avg_load_per_doctor: number
  cito_studies: number
  asap_studies: number
}

interface DepartmentSummary {
  department: string
  planUp: number
  actualUp: number
  fulfillment: number
  studies: number
}

export const ReportsView: React.FC = () => {
  const today = new Date()
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)

  const formatInputDate = (d: Date) => d.toISOString().split("T")[0]

  const initialDateFrom = formatInputDate(firstDay)
  const initialDateTo = formatInputDate(today)

  const [loading, setLoading] = useState(true)

  const [dateFrom, setDateFrom] = useState<string>(initialDateFrom)
  const [dateTo, setDateTo] = useState<string>(initialDateTo)

  const [appliedDateFrom, setAppliedDateFrom] = useState<string>(initialDateFrom)
  const [appliedDateTo, setAppliedDateTo] = useState<string>(initialDateTo)

  const [kpiData, setKpiData] = useState<KPIData | null>(null)
  const [chartData, setChartData] = useState<any[]>([])
  const [pieData, setPieData] = useState<any[]>([])
  const [departmentSummary, setDepartmentSummary] = useState<DepartmentSummary[]>([])

  const COLORS = ["#3b82f6", "#22c55e", "#f97316"]

  useEffect(() => {
    if (appliedDateFrom && appliedDateTo) {
      loadReportsData()
    }
  }, [appliedDateFrom, appliedDateTo])

  const handleApplyFilters = () => {
    setAppliedDateFrom(dateFrom)
    setAppliedDateTo(dateTo)
  }

  const loadReportsData = async () => {
    try {
      setLoading(true)

      const [stats, chart] = await Promise.all([
        dashboardApi.getStats(appliedDateFrom, appliedDateTo),
        dashboardApi.getChartData(appliedDateFrom, appliedDateTo),
      ])

      setKpiData(stats)
      setChartData(chart || [])

      const normalStudies = Math.max(
        0,
        stats.total_studies - stats.cito_studies - stats.asap_studies
      )

      setPieData([
        { name: "CITO", value: stats.cito_studies },
        { name: "ASAP", value: stats.asap_studies },
        { name: "Обычные", value: normalStudies },
      ])

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
      ])
    } catch (err) {
      console.error("Error loading reports:", err)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-slate-500">
        Загрузка отчётов...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Отчёты</h2>
      </div>

      <div className="bg-white border rounded-lg p-4 flex gap-3 flex-wrap">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="border px-3 py-1 rounded"
        />

        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="border px-3 py-1 rounded"
        />

        <button
          onClick={handleApplyFilters}
          className="bg-blue-600 text-white px-4 py-1 rounded flex items-center gap-1"
        >
          <Filter size={15} />
          Применить
        </button>
      </div>

      {kpiData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KPI
            title="Всего исследований"
            value={kpiData.total_studies}
            icon={<TrendingUp size={16} />}
          />

          <KPI
            title="Выполнено"
            value={kpiData.completed_studies}
            icon={<CheckCircle2 size={16} />}
          />

          <KPI
            title="В очереди"
            value={kpiData.pending_studies}
            icon={<Target size={16} />}
          />

          <KPI
            title="Средняя загрузка врача"
            value={kpiData.avg_load_per_doctor}
            icon={<Clock size={16} />}
          />
        </div>
      )}

      <div className="bg-white p-4 rounded-xl border">
        <h3 className="font-semibold mb-4">План / Факт по дням</h3>

        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="plan" fill="#94a3b8" name="План" />
            <Bar dataKey="actual" fill="#3b82f6" name="Факт" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white p-4 rounded-xl border">
        <h3 className="font-semibold mb-4">Типы исследований</h3>

        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={pieData}
              dataKey="value"
              nameKey="name"
              outerRadius={110}
              label
            >
              {pieData.map((_, index) => (
                <Cell key={index} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white rounded-xl border overflow-hidden">
        <div className="p-4 border-b font-semibold">
          Сводка по данным
        </div>

        <table className="w-full text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-2 text-left">Раздел</th>
              <th className="px-4 py-2 text-right">План</th>
              <th className="px-4 py-2 text-right">Факт</th>
              <th className="px-4 py-2 text-right">Выполнение</th>
              <th className="px-4 py-2 text-right">Исследований</th>
            </tr>
          </thead>

          <tbody>
            {departmentSummary.map((d, i) => (
              <tr key={i} className="border-t">
                <td className="px-4 py-2">{d.department}</td>
                <td className="px-4 py-2 text-right">{d.planUp}</td>
                <td className="px-4 py-2 text-right">{d.actualUp}</td>
                <td className="px-4 py-2 text-right">{d.fulfillment}%</td>
                <td className="px-4 py-2 text-right">{d.studies}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const KPI = ({ title, value, icon }: any) => (
  <div className="bg-white border rounded-lg p-4">
    <div className="flex justify-between text-sm text-slate-600 mb-1">
      {title}
      {icon}
    </div>

    <div className="text-2xl font-bold">
      {value?.toLocaleString()}
    </div>
  </div>
)