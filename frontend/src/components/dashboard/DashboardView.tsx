import React, { useState, useEffect } from 'react';
import { dashboardApi, distributionApi, doctorsApi } from '../../services/api';
import { KPICard } from './KPICard';
import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, GitBranch, Users } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { DashboardStats, ChartData, DistributionInfo, DoctorWithLoad } from '../../types';

interface DashboardViewProps {
  onNavigate?: (tab: string) => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({ onNavigate }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [chartData, setChartData] = useState<ChartData[]>([]);
  const [distributionInfo, setDistributionInfo] = useState<DistributionInfo | null>(null);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
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
      const [distributionRes, doctorsRes] = await Promise.all([
        distributionApi.getInfo(),
        doctorsApi.getWithLoad(),
      ]);
      setDistributionInfo(distributionRes);
      setDoctors(doctorsRes || []);
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

  const completionRate = Math.round(((stats?.completed_studies || 0) / (stats?.total_studies || 1)) * 100);
  const urgentTotal = (stats?.cito_studies || 0) + (stats?.asap_studies || 0);
  const overloadedDoctors = doctors.filter((doctor) => doctor.load_percentage >= 80);
  const availableDoctors = distributionInfo?.available_doctors ?? stats?.active_doctors ?? 0;
  const pendingStudies = distributionInfo?.pending_studies ?? stats?.pending_studies ?? 0;
  const statusColor =
    pendingStudies > 0 || overloadedDoctors.length > 0
      ? 'border-amber-200 bg-amber-50 text-amber-800'
      : 'border-blue-200 bg-blue-50 text-blue-800';

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950">Пульт службы</h2>
          <p className="mt-1 text-sm text-slate-500">Состояние очереди, врачей и выполнения плана</p>
        </div>
      </div>

      <div className={`rounded-xl border px-4 py-3 shadow-sm ${statusColor}`}>
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div className="flex items-start gap-3">
            {pendingStudies > 0 || overloadedDoctors.length > 0 ? (
              <AlertTriangle size={20} className="mt-0.5 shrink-0" />
            ) : (
              <CheckCircle2 size={20} className="mt-0.5 shrink-0" />
            )}
            <div>
              <div className="font-semibold">
                {pendingStudies > 0 ? `В очереди ${pendingStudies} исследований` : 'Очередь распределена'}
              </div>
              <div className="text-sm opacity-80">
                Доступно врачей: {availableDoctors}. В зоне высокой нагрузки: {overloadedDoctors.length}.
              </div>
            </div>
          </div>
          <button
            onClick={() => onNavigate?.('distribution')}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-white/80 px-4 py-2 text-sm font-semibold text-slate-800 shadow-sm transition hover:bg-white"
          >
            Открыть распределение
            <ArrowRight size={16} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 md:gap-4">
        <KPICard
          title="Выполнение плана"
          value={`${completionRate}%`}
          subtext={`${stats?.completed_studies || 0} из ${stats?.total_studies || 0}`}
        />
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
