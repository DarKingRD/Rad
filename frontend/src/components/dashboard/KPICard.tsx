import React from 'react';
import { KPICardProps } from '../../types';

export const KPICard: React.FC<KPICardProps & { className?: string }> = ({ title, value, subtext, trend, className }) => (
  <div className={`bg-white p-4 md:p-6 rounded-xl border border-slate-200 shadow-sm ${className || ''}`}>
    <h3 className="text-slate-500 text-xs md:text-sm font-medium mb-1 md:mb-2 truncate">{title}</h3>
    <div className="flex items-baseline space-x-2">
      <span className="text-2xl md:text-3xl font-bold text-slate-900 truncate">{value}</span>
      {trend && (
        <span className={`text-xs md:text-sm shrink-0 ${trend > 0 ? 'text-green-600' : 'text-red-600'}`}>
          {trend > 0 ? '+' : ''}{trend}%
        </span>
      )}
    </div>
    <p className="text-slate-400 text-xs mt-1 md:mt-2 truncate">{subtext}</p>
  </div>
);