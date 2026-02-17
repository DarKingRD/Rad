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
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-slate-900">Обзор системы</h2>
        <button 
          onClick={loadDashboardData}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700"
        >
          Обновить
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <KPICard 
          title="Выполнение плана" 
          value={stats ? `${Math.round((stats.completed_studies / (stats.total_studies || 1)) * 100)}%` : '0%'} 
          subtext={`${stats?.completed_studies || 0} из ${stats?.total_studies || 0} исследований`} 
          trend={2.4} 
        />
        <KPICard 
          title="Средняя нагрузка" 
          value={`${stats?.avg_load_per_doctor || 0} УП`} 
          subtext="На врача сегодня" 
          trend={-1.2} 
        />
        <KPICard 
          title="Хвост очереди" 
          value={stats?.pending_studies || 0} 
          subtext="Исследований не назначено" 
          trend={-5} 
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-semibold text-slate-800">Выполнение плана по дням</h3>
            <div className="flex space-x-2 text-xs">
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-slate-400 mr-1"></span> План</span>
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span> Факт</span>
            </div>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip cursor={{fill: '#f1f5f9'}} />
                <Legend />
                <Bar dataKey="plan" fill="#94a3b8" radius={[4, 4, 0, 0]} name="План" />
                <Bar dataKey="actual" fill="#0ea5e9" radius={[4, 4, 0, 0]} name="Факт" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="font-semibold text-slate-800">Оповещения</h3>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-red-500">
              <AlertCircle size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">CITO исследований: {stats?.cito_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-1">Требуют срочного выполнения</p>
            </div>
          </div>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-amber-500">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">ASAP исследований: {stats?.asap_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-1">Требуют быстрого выполнения</p>
            </div>
          </div>
          <div className="flex items-start space-x-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
            <div className="mt-0.5 text-blue-500">
              <Clock size={18} />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-800">В плане: {stats?.pending_studies || 0}</p>
              <p className="text-xs text-slate-500 mt-1">Ожидают назначения врача</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};