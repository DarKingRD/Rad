import React, { useState, useEffect, useMemo } from 'react';
import { dashboardApi, studiesApi, doctorsApi, studyTypesApi } from '../../services/api';
import { Download, Calendar, Filter, TrendingUp, CheckCircle2, Target, Clock, BarChart3, Users, PieChart } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart as RechartsPieChart, Pie, Cell } from 'recharts';

interface DepartmentSummary {
  department: string;
  planUp: number;
  actualUp: number;
  fulfillment: number;
  studies: number;
  avgTime: string;
}

export const ReportsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'doctors' | 'studies' | 'efficiency'>('doctors');
  const [dateFrom, setDateFrom] = useState<string>(() => {
    const date = new Date();
    date.setDate(1);
    return date.toISOString().split('T')[0];
  });
  const [dateTo, setDateTo] = useState<string>(() => {
    const date = new Date();
    return date.toISOString().split('T')[0];
  });
  const [selectedDepartment, setSelectedDepartment] = useState<string>('all');
  const [selectedDoctor, setSelectedDoctor] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [chartData, setChartData] = useState<any[]>([]);
  const [pieData, setPieData] = useState<any[]>([]);
  const [departmentSummary, setDepartmentSummary] = useState<DepartmentSummary[]>([]);

  // KPI данные (пока моковые, потом заменим на реальные)
  const kpiData = useMemo(() => ({
    totalUp: 3847,
    totalUpChange: 12.5,
    completedStudies: 1284,
    completedStudiesChange: 8.3,
    planFulfillment: 94.2,
    planFulfillmentChange: -2.1,
    avgWaitTime: 18,
    avgWaitTimeChange: -5,
  }), []);

  const COLORS = ['#f97316', '#a855f7', '#3b82f6', '#22c55e'];

  useEffect(() => {
    loadReportsData();
  }, [dateFrom, dateTo]);

  const loadReportsData = async () => {
    try {
      setLoading(true);
      const [chartRes] = await Promise.all([
        dashboardApi.getChartData(dateFrom, dateTo),
      ]);
      
      setChartData(chartRes.data || []);
      
      // Моковые данные для pie chart и таблицы
      setPieData([
        { name: 'Рентген', value: 45 },
        { name: 'КТ', value: 30 },
        { name: 'МРТ', value: 15 },
        { name: 'Флюорография', value: 10 },
      ]);
      
      setDepartmentSummary([
        { department: 'Рентген', planUp: 2100, actualUp: 2015, fulfillment: 96, studies: 724, avgTime: '12 мин' },
        { department: 'КТ', planUp: 1200, actualUp: 1098, fulfillment: 91, studies: 312, avgTime: '25 мин' },
        { department: 'МРТ', planUp: 800, actualUp: 734, fulfillment: 92, studies: 248, avgTime: '35 мин' },
      ]);
    } catch (error) {
      console.error('Error loading reports:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = () => {
    loadReportsData();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка отчётов...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-slate-900">Отчёты и аналитика</h2>
        <button className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-md text-sm font-medium hover:bg-slate-50 flex items-center">
          <Download size={16} className="mr-2" /> Экспорт
        </button>
      </div>

      {/* Вкладки */}
      <div className="flex space-x-1 border-b border-slate-200">
        {[
          { id: 'doctors', label: 'По врачам' },
          { id: 'studies', label: 'По исследованиям' },
          { id: 'efficiency', label: 'Эффективность' },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Фильтры */}
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="text-sm text-slate-700 font-medium">Период:</span>
            <div className="flex items-center space-x-2">
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="px-3 py-1.5 border border-slate-300 rounded-md text-sm"
              />
              <span className="text-slate-500">—</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="px-3 py-1.5 border border-slate-300 rounded-md text-sm"
              />
            </div>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-sm text-slate-700 font-medium">Отделение:</span>
            <select
              value={selectedDepartment}
              onChange={(e) => setSelectedDepartment(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 rounded-md text-sm"
            >
              <option value="all">Все отделения</option>
              <option value="xray">Рентген</option>
              <option value="ct">КТ</option>
              <option value="mri">МРТ</option>
            </select>
          </div>
          <div className="flex items-center space-x-2">
            <span className="text-sm text-slate-700 font-medium">Врач:</span>
            <select
              value={selectedDoctor}
              onChange={(e) => setSelectedDoctor(e.target.value)}
              className="px-3 py-1.5 border border-slate-300 rounded-md text-sm"
            >
              <option value="all">Все врачи</option>
            </select>
          </div>
          <button
            onClick={handleApplyFilters}
            className="px-4 py-1.5 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 flex items-center"
          >
            <Filter size={16} className="mr-2" />
            Применить
          </button>
        </div>
      </div>

      {/* KPI карточки */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm text-slate-600">Всего УП</div>
            <TrendingUp size={16} className="text-blue-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mb-1">{kpiData.totalUp.toLocaleString()}</div>
          <div className="text-xs text-green-600">+{kpiData.totalUpChange}% к прошлому месяцу</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm text-slate-600">Выполнено исследований</div>
            <CheckCircle2 size={16} className="text-green-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mb-1">{kpiData.completedStudies.toLocaleString()}</div>
          <div className="text-xs text-green-600">+{kpiData.completedStudiesChange}% к прошлому месяцу</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm text-slate-600">% выполнения плана</div>
            <Target size={16} className="text-blue-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mb-1">{kpiData.planFulfillment}%</div>
          <div className="text-xs text-red-600">{kpiData.planFulfillmentChange}% к прошлому месяцу</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm text-slate-600">Среднее время ожидания</div>
            <Clock size={16} className="text-slate-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900 mb-1">{kpiData.avgWaitTime} мин</div>
          <div className="text-xs text-green-600">{kpiData.avgWaitTimeChange} мин к прошлому месяцу</div>
        </div>
      </div>

      {/* Виджеты */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-2">
            <BarChart3 size={20} className="text-blue-600" />
          </div>
          <div className="font-semibold text-slate-900 mb-1">Загрузка по дням</div>
          <div className="text-xs text-slate-500">Детальная статистика по дням</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-2">
            <Users size={20} className="text-green-600" />
          </div>
          <div className="font-semibold text-slate-900 mb-1">Эффективность врачей</div>
          <div className="text-xs text-slate-500">Выполнение плана по каждому врачу</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4 cursor-pointer hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between mb-2">
            <PieChart size={20} className="text-purple-600" />
          </div>
          <div className="font-semibold text-slate-900 mb-1">По типам исследований</div>
          <div className="text-xs text-slate-500">Распределение по модальностям</div>
        </div>
      </div>

      {/* Графики */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-800">Выполнение плана по дням</h3>
            <div className="flex space-x-2">
              <button className="px-2 py-1 text-xs bg-blue-100 text-blue-700 rounded">План/Факт</button>
              <button className="px-2 py-1 text-xs bg-slate-100 text-slate-600 rounded">Тренд</button>
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
                <Bar dataKey="actual" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Факт" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-semibold text-slate-800">Распределение по типам исследований</h3>
            <button className="p-1 hover:bg-slate-100 rounded">
              <Download size={16} className="text-slate-600" />
            </button>
          </div>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsPieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend 
                  verticalAlign="middle" 
                  align="right"
                  layout="vertical"
                  iconType="circle"
                />
              </RechartsPieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Таблица сводки по отделению */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between p-4 border-b border-slate-200">
          <h3 className="font-semibold text-slate-800">Сводка по отделению</h3>
          <button className="px-3 py-1.5 bg-white border border-slate-300 text-slate-700 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <Download size={14} className="mr-2" /> Экспорт
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-3 text-left font-semibold text-slate-700">ОТДЕЛЕНИЕ</th>
                <th className="px-6 py-3 text-right font-semibold text-slate-700">ПЛАН УП</th>
                <th className="px-6 py-3 text-right font-semibold text-slate-700">ФАКТ УП</th>
                <th className="px-6 py-3 text-center font-semibold text-slate-700">ВЫПОЛНЕНИЕ</th>
                <th className="px-6 py-3 text-right font-semibold text-slate-700">ИССЛЕДОВАНИЙ</th>
                <th className="px-6 py-3 text-right font-semibold text-slate-700">СРЕДНЕЕ ВРЕМЯ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {departmentSummary.map((dept, index) => (
                <tr key={index} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-900">{dept.department}</td>
                  <td className="px-6 py-4 text-right text-slate-600">{dept.planUp.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right text-slate-600">{dept.actualUp.toLocaleString()}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center space-x-2">
                      <div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden">
                        <div 
                          className={`h-full ${dept.fulfillment >= 95 ? 'bg-green-500' : dept.fulfillment >= 80 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${dept.fulfillment}%` }}
                        ></div>
                      </div>
                      <span className="text-sm font-medium text-slate-700 w-12 text-right">{dept.fulfillment}%</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right text-slate-600">{dept.studies.toLocaleString()}</td>
                  <td className="px-6 py-4 text-right text-slate-600">{dept.avgTime}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};