import React from 'react';
import { CHART_DATA } from '../../data/mockData';
import { Download } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';

export const ReportsView: React.FC = () => {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-slate-900">Отчёты и аналитика</h2>
        <button className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-md text-sm font-medium hover:bg-slate-50 flex items-center">
          <Download size={16} className="mr-2" /> Экспорт CSV
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="font-semibold text-slate-800 mb-6">Выполнение плана по дням</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={CHART_DATA}>
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

        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <h3 className="font-semibold text-slate-800 mb-6">Динамика загрузки</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={CHART_DATA}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip />
                <Line type="monotone" dataKey="actual" stroke="#0ea5e9" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};