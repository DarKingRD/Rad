import React, { useState, useEffect } from 'react';
import { dashboardApi, distributionApi } from '../../services/api';
import { KPICard } from './KPICard';
import { CalendarClock, GitBranch, Users } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DashboardStats, ChartData, DistributionInfo } from '../../types';

interface DashboardViewProps {
  onNavigate?: (tab: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [distributionInfo, setDistributionInfo] = useState<DistributionInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      const [statsRes, chartRes] = await Promise.all([
        dashboardApi.getStats(),
        dashboardApi.getChartData(
          new Date(Date.now() - 13 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
          new Date().toISOString().split('T')[0]
        )
      ]);
      setStats(statsRes);
      setChartData(chartRes);
      const distributionRes = await distributionApi.getInfo();
      setDistributionInfo(distributionRes);
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

  const urgentTotal = (stats?.cito_studies || 0) + (stats?.asap_studies || 0);
  const pendingStudies = distributionInfo?.pending_studies ?? stats?.pending_studies ?? 0;

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950">Главная</h2>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-2 md:gap-4">
        <KPICard
          title="Очередь"
          value={pendingStudies}
          subtext="Ожидают назначения"
        />
        <KPICard
          title="Срочные"
          value={urgentTotal}
          subtext={`CITO ${stats?.cito_studies || 0} · Срочные ${stats?.asap_studies || 0}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 md:gap-5">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm lg:col-span-2 md:p-5">
          <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h3 className="text-base font-semibold text-slate-900">Динамика за 14 дней</h3>
            <div className="flex space-x-2 text-xs">
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-slate-400 mr-1"></span>Поступило</span>
              <span className="flex items-center"><span className="w-2 h-2 rounded-full bg-blue-500 mr-1"></span>Выполнено</span>
            </div>
          </div>
          <div className="h-56 md:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11 }} />
                <Tooltip cursor={{ fill: '#f1f5f9' }} />
                <Bar dataKey="plan" fill="#94a3b8" radius={[4, 4, 0, 0]} name="Поступило" />
                <Bar dataKey="actual" fill="#2563eb" radius={[4, 4, 0, 0]} name="Выполнено" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
          <h3 className="text-base font-semibold text-slate-900">Быстрые действия</h3>
          <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-blue-500 shrink-0">
              <GitBranch size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <button onClick={() => onNavigate?.('distribution')} className="text-left text-sm font-medium text-slate-800 hover:text-blue-700">
                Распределить очередь
              </button>
              <p className="text-xs text-slate-500 mt-0.5">{pendingStudies} исследований ожидают врача</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-amber-500 shrink-0">
              <CalendarClock size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <button onClick={() => onNavigate?.('planning')} className="text-left text-sm font-medium text-slate-800 hover:text-blue-700">
                Проверить смены
              </button>
              <p className="text-xs text-slate-500 mt-0.5">График и прогноз потребности</p>
            </div>
          </div>
          <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3">
            <div className="mt-0.5 text-blue-500 shrink-0">
              <Users size={18} />
            </div>
            <div className="min-w-0 flex-1">
              <button onClick={() => onNavigate?.('reports')} className="text-left text-sm font-medium text-slate-800 hover:text-blue-700">
                Открыть отчёт
              </button>
              <p className="text-xs text-slate-500 mt-0.5">Выполнение и нагрузка врачей</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
