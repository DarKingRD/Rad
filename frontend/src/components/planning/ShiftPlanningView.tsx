import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { schedulesApi, doctorsApi } from '../../services/api';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Schedule, Doctor } from '../../types';

export const ShiftPlanningView: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [loading, setLoading] = useState(true);
  
  // ✅ ТЕКУЩАЯ ДАТА (как ты хочешь)
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [selectedDoctor, setSelectedDoctor] = useState<number | 'all'>('all');

  // ✅ Генерация дат
  const dates = useMemo(() => {
    const result = [];
    const startOfWeek = new Date(currentDate);
    const day = startOfWeek.getDay();
    const diff = startOfWeek.getDate() - day + (day === 0 ? -6 : 1);
    startOfWeek.setDate(diff);
    startOfWeek.setHours(0, 0, 0, 0);
    
    for (let i = 0; i < 7; i++) {
      const date = new Date(startOfWeek);
      date.setDate(date.getDate() + i);
      result.push(date.toISOString().split('T')[0]);
    }
    return result;
  }, [currentDate]);

  // ✅ Загрузка врачей (1 раз)
  useEffect(() => {
    const loadDoctors = async () => {
      try {
        const res = await doctorsApi.getAll();
        const doctorsData = res.data.results || res.data;
        setDoctors(Array.isArray(doctorsData) ? doctorsData : []);
      } catch (err) {
        console.error('Error loading doctors:', err);
      }
    };
    
    loadDoctors();
  }, []);

  // ✅ Загрузка смен (при изменении даты)
  useEffect(() => {
    const loadSchedules = async () => {
      try {
        setLoading(true);
        console.log('🔍 Загрузка смен:', { 
          date_from: dates[0], 
          date_to: dates[6],
          doctor_id: selectedDoctor 
        });
        
        const res = await schedulesApi.getAll({
          date_from: dates[0],
          date_to: dates[6],
          ...(selectedDoctor !== 'all' && { doctor_id: Number(selectedDoctor) })
        });
        
        const schedulesData = res.data.results || res.data;
        console.log('✅ Получено смен:', schedulesData.length);
        if (schedulesData.length > 0) {
          console.log('📋 Пример смены:', schedulesData[0]);
        }
        setSchedules(Array.isArray(schedulesData) ? schedulesData : []);
      } catch (err) {
        console.error('❌ Ошибка загрузки смен:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadSchedules();
  }, [dates, selectedDoctor]);

  // ✅ Навигация
  const handlePrevWeek = () => {
    setCurrentDate(prev => {
      const newDate = new Date(prev);
      newDate.setDate(newDate.getDate() - 7);
      return newDate;
    });
  };

  const handleNextWeek = () => {
    setCurrentDate(prev => {
      const newDate = new Date(prev);
      newDate.setDate(newDate.getDate() + 7);
      return newDate;
    });
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  // ✅ ИСПРАВЛЕНО: doctor вместо doctor_id!
  const getScheduleForDoctor = useCallback((doctorId: number, date: string) => {
    return schedules.find(s => {
      // ✅ API возвращает 'doctor', не 'doctor_id'
      if (s.doctor !== doctorId && s.doctor_id !== doctorId) return false;
      
      // ✅ Сравниваем даты (берём только часть до T)
      const scheduleDate = s.work_date?.split('T')[0];
      return scheduleDate === date;
    });
  }, [schedules]);

  // ✅ Цвет статуса
  const getStatusColor = (schedule?: Schedule) => {
    if (!schedule) return 'bg-slate-100 text-slate-400';
    if (schedule.is_day_off !== 0) return 'bg-slate-100 text-slate-400';
    return 'bg-green-100 text-green-700 border border-green-200';
  };

  if (loading && schedules.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка расписания...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-slate-900">Планирование смен</h2>
        <div className="flex items-center space-x-3">
          <select 
            value={selectedDoctor}
            onChange={(e) => setSelectedDoctor(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm bg-white"
          >
            <option value="all">Все врачи</option>
            {doctors.map((doc) => (
              <option key={doc.id} value={doc.id}>
                {doc.fio_alias}
              </option>
            ))}
          </select>

          <div className="flex items-center space-x-2">
            <button onClick={handlePrevWeek} className="p-2 bg-white border border-slate-300 rounded-md hover:bg-slate-50">
              <ChevronLeft size={16} />
            </button>
            <button onClick={handleToday} className="px-3 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50">
              Сегодня
            </button>
            <button onClick={handleNextWeek} className="p-2 bg-white border border-slate-300 rounded-md hover:bg-slate-50">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Диапазон дат */}
      <div className="text-sm text-slate-600 bg-slate-50 px-4 py-2 rounded-md">
        <span className="font-medium">Неделя:</span> {new Date(dates[0]).toLocaleDateString('ru-RU')} — {new Date(dates[6]).toLocaleDateString('ru-RU')}
      </div>

      {/* Таблица */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-6 py-4 font-semibold text-slate-700">Врач</th>
                {dates.map(date => {
                  const d = new Date(date);
                  const dayName = d.toLocaleDateString('ru-RU', { weekday: 'short' });
                  const dayNum = d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
                  return (
                    <th key={date} className="px-6 py-4 font-semibold text-center">
                      <div className="text-xs text-slate-500">{dayName}</div>
                      <div>{dayNum}</div>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {doctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-6 py-4 font-medium text-slate-900">
                    <div>{doc.fio_alias}</div>
                    <div className="text-xs text-slate-500">{doc.specialty}</div>
                  </td>
                  {dates.map(date => {
                    const schedule = getScheduleForDoctor(doc.id, date);
                    return (
                      <td key={date} className="px-6 py-4 text-center">
                        {schedule ? (
                          <div className={`inline-flex items-center px-3 py-1.5 rounded-full text-xs font-medium ${getStatusColor(schedule)}`}>
                            {schedule.time_start?.substring(0, 5) || '—'}–{schedule.time_end?.substring(0, 5) || '—'}
                          </div>
                        ) : (
                          <span className="text-slate-400 text-xs">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};