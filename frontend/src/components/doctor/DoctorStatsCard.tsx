import { Activity } from 'lucide-react';
import type { DoctorPeriodStats } from '../../types';

type DoctorStatsCardProps = {
  title: string;
  stats: DoctorPeriodStats;
};

export function DoctorStatsCard({ title, stats }: DoctorStatsCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        <Activity size={18} className="text-blue-600" />
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <div>
          <p className="text-slate-500">Назначено</p>
          <p className="text-xl font-bold text-slate-950">{stats.assigned}</p>
        </div>
        <div>
          <p className="text-slate-500">Выполнено</p>
          <p className="text-xl font-bold text-blue-700">{stats.completed}</p>
        </div>
        <div>
          <p className="text-slate-500">Осталось</p>
          <p className="text-xl font-bold text-amber-700">{stats.pending}</p>
        </div>
        <div>
          <p className="text-slate-500">УП</p>
          <p className="text-xl font-bold text-slate-950">{stats.completed_up.toFixed(2)}</p>
        </div>
      </div>
    </div>
  );
}
