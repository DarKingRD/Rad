import React, { useState, useEffect } from 'react';
import { dashboardApi } from '../../services/api';
import { KPICard } from './KPICard';
import { CalendarClock, Clock } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { DashboardStats, ChartData } from '../../types';

export const DashboardView: React.FC = () => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      const [statsRes, chartRes] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getChartData(
          new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          new Date().toISOString().split('T')[0]
        )
      ]);
      setStats(statsRes);
      setChartData(chartRes);
    } catch (error) {
      console.error('Error loading dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка данных...</div>
      </div>
    );
  }

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950">Обзор системы</h2>
          <p className="mt-1 text-sm text-slate-500">Ключевые показатели работы и текущие риски очереди</p>
        </div>
        <button
          onClick={loadDashboardData}
          className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700"
        >
          Обновить
        </button>
      </div>

      {/* KPI: 2 колонки на телефоне, 3 на десктопе */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 md:gap-4">
        <KPICard
          title="Выполнение плана"
          value={stats ? `${Math.round((stats.completed_studies / (stats.total_studies || 1)) * 100)}%` : '0%'}
          subtext={`${stats?.completed_studies || 0} из ${stats?.total_studies || 0}`}
          trend={2.4}
        />
        <KPICard
          title="Ср. нагрузка"
          value={`${stats?.avg_load_per_doctor || 0} УП`}
          subtext="На врача"
          trend={-1.2}
        />
        <KPICard
          title="Очередь"
          value={stats?.pending_studies || 0}
          subtext="Не назначено"
          trend={-5}
          className=""
        />
      </div>

      {/* График + алерты: стек на мобиле, 2/3+1/3 на десктопе */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 md:gap-5">
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 lg:col-span-2 md:p-5">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-base font-semibold text-slate-900">Выполнение плана по дням</h3>
            <div className="flex space-x-2 text-xs">
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-slate-400 mr-1"></span>План</span>
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span>Факт</span>
            </div>
          </div>
          <div className="h-56 md:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                <Tooltip cursor={{ fill: '#f1f5f9' }} />
                <Legend />
                <Bar dataKey="plan" fill="#94a3b8" radius={[4, 4, 0, 0]} name="План" />
                <Bar dataKey="actual" fill="#0ea5e9" radius={[4, 4, 0, 0]} name="Факт" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="space-y-3 rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 md:p-5">
          <h3 className="text-base font-semibold text-slate-900">Фокус на сегодня</h3>
          <div className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-blue-500 shrink-0">
              <CalendarClock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">План/факт: {stats?.completed_studies || 0} / {stats?.total_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Ориентир выполнения на текущий период</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-amber-500 shrink-0">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">ASAP: {stats?.asap_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Требуют быстрого выполнения</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-blue-500 shrink-0">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">CITO: {stats?.cito_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Срочные исследования в очереди</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};