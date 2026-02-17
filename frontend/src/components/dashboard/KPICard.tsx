import React from 'react';
import { KPICardProps } from '../../types';

export const KPICard: React.FC<KPICardProps> = ({ title, value, subtext, trend }) => (
  <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
    <h3 className="text-slate-500 text-sm font-medium mb-2">{title}</h3>
    <div className="flex items-baseline space-x-2">
      <span className="text-3xl font-bold text-slate-900">{value}</span>
      {trend && (
        <span className={`text-sm ${trend > 0 ? 'text-green-600' : 'text-red-600'}`}>
          {trend > 0 ? '+' : ''}{trend}%
        </span>
      )}
    </div>
    <p className="text-slate-400 text-xs mt-2">{subtext}</p>
  </div>
);