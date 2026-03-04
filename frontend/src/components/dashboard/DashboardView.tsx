import React, { useState, useEffect } from 'react';
import { dashboardApi } from '../../services/api';
import { KPICard } from './KPICard';
import { AlertCircle, Clock } from 'lucide-react';
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
      setStats(statsRes.data);
      setChartData(chartRes.data);
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
    <div className="space-y-4 md:space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl md:text-2xl font-bold text-slate-900">Обзор системы</h2>
        <button
          onClick={loadDashboardData}
          className="px-3 md:px-4 py-1.5 md:py-2 bg-blue-600 text-white rounded-md text-xs md:text-sm font-medium hover:bg-blue-700"
        >
          Обновить
        </button>
      </div>

      {/* KPI: 2 колонки на телефоне, 3 на десктопе */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 md:gap-6">
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
          className="col-span-2 md:col-span-1"
        />
      </div>

      {/* График + алерты: стек на мобиле, 2/3+1/3 на десктопе */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
        <div className="lg:col-span-2 bg-white p-4 md:p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-semibold text-slate-800 text-sm md:text-base">Выполнение плана по дням</h3>
            <div className="flex space-x-2 text-xs">
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-slate-400 mr-1"></span>План</span>
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span>Факт</span>
            </div>
          </div>
          <div className="h-48 md:h-64">
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

        <div className="space-y-3">
          <h3 className="font-semibold text-slate-800 text-sm md:text-base">Оповещения</h3>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-red-500 shrink-0">
              <AlertCircle size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">CITO: {stats?.cito_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Требуют срочного выполнения</p>
            </div>
          </div>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-amber-500 shrink-0">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">ASAP: {stats?.asap_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Требуют быстрого выполнения</p>
            </div>
          </div>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-blue-500 shrink-0">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">В плане: {stats?.pending_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-0.5">Ожидают назначения врача</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};