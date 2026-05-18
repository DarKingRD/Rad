import React from 'react';
import { KPICardProps } from '../../types';

export const KPICard: React.FC<KPICardProps & { className?: string }> = ({ title, value, subtext, trend, className }) => (
  <div className={`rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 transition hover:-translate-y-0.5 hover:shadow-md md:p-5 ${className || ''}`}>
    <h3 className="mb-1.5 truncate text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
    <div className="flex min-w-0 items-baseline gap-2">
      <span className="truncate text-2xl font-bold tracking-tight text-slate-950 md:text-3xl">{value}</span>
      {trend ? (
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${trend > 0 ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700'}`}>
          {trend > 0 ? '+' : ''}{trend}%
        </span>
      ) : null}
    </div>
    <p className="mt-2 truncate text-xs text-slate-500">{subtext}</p>
  </div>
);
