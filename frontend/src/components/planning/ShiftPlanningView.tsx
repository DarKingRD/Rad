import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { schedulesApi, doctorsApi, studiesApi } from '../../services/api';
import { ChevronLeft, ChevronRight, X, CheckCircle2, AlertTriangle, AlertCircle, Copy, Printer, RefreshCw, Search, Download } from 'lucide-react';
import { Schedule, Doctor, Study } from '../../types';

interface ScheduleFormData {
  doctor_id: number;
  work_date: string;
  time_start: string;
  time_end: string;
  is_day_off: number;
  planned_up: number;
}

export const ShiftPlanningView: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [studies, setStudies] = useState<Study[]>([]);
  const [loading, setLoading] = useState(true);
  
  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [selectedDoctor, setSelectedDoctor] = useState<number | 'all'>('all');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [formData, setFormData] = useState<ScheduleFormData>({
    doctor_id: 0,
    work_date: '',
    time_start: '09:00',
    time_end: '18:00',
    is_day_off: 0,
    planned_up: 0,
  });

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

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [schedulesRes, studiesRes] = await Promise.all([
          schedulesApi.getAll({
            date_from: dates[0],
            date_to: dates[6],
            ...(selectedDoctor !== 'all' && { doctor_id: Number(selectedDoctor) })
          }),
          studiesApi.getAll({
            date_from: dates[0],
            date_to: dates[6],
          })
        ]);
        
        const schedulesData = schedulesRes.data.results || schedulesRes.data;
        const studiesData = studiesRes.data.results || studiesRes.data;
        
        setSchedules(Array.isArray(schedulesData) ? schedulesData : []);
        setStudies(Array.isArray(studiesData) ? studiesData : []);
      } catch (err) {
        console.error('Error loading data:', err);
      } finally {
        setLoading(false);
      }
    };
    
    loadData();
  }, [dates, selectedDoctor]);

  const loadSchedulesData = async () => {
    const [schedulesRes, studiesRes] = await Promise.all([
      schedulesApi.getAll({
        date_from: dates[0],
        date_to: dates[6],
        ...(selectedDoctor !== 'all' && { doctor_id: Number(selectedDoctor) })
      }),
      studiesApi.getAll({
        date_from: dates[0],
        date_to: dates[6],
      })
    ]);
    
    const schedulesData = schedulesRes.data.results || schedulesRes.data;
    const studiesData = studiesRes.data.results || studiesRes.data;
    
    setSchedules(Array.isArray(schedulesData) ? schedulesData : []);
    setStudies(Array.isArray(studiesData) ? studiesData : []);
  };

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

  const getDoctorIdFromSchedule = (schedule: Schedule, fallback: number): number => {
    if (typeof schedule.doctor === 'object' && schedule.doctor?.id) {
      return schedule.doctor.id;
    }
    return schedule.doctor_id || (typeof schedule.doctor === 'number' ? schedule.doctor : fallback);
  };

  const handleOpenModal = (doctorId: number, date: string, schedule?: Schedule) => {
    if (schedule) {
      setEditingSchedule(schedule);
      setFormData({
        doctor_id: getDoctorIdFromSchedule(schedule, doctorId),
        work_date: schedule.work_date?.split('T')[0] || date,
        time_start: schedule.time_start?.substring(0, 5) || '09:00',
        time_end: schedule.time_end?.substring(0, 5) || '18:00',
        is_day_off: schedule.is_day_off || 0,
        planned_up: schedule.planned_up || 0,
      });
    } else {
      setEditingSchedule(null);
      setFormData({
        doctor_id: doctorId,
        work_date: date,
        time_start: '09:00',
        time_end: '18:00',
        is_day_off: 0,
        planned_up: 0,
      });
    }
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingSchedule(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const submitData = {
        doctor: formData.doctor_id,
        work_date: formData.work_date,
        time_start: formData.time_start,
        time_end: formData.time_end,
        is_day_off: formData.is_day_off,
        planned_up: formData.planned_up,
      };
      
      if (editingSchedule) {
        await schedulesApi.update(editingSchedule.id, submitData);
      } else {
        await schedulesApi.create(submitData);
      }
      
      await loadSchedulesData();
      handleCloseModal();
    } catch (error: any) {
      console.error('Error saving schedule:', error);
      alert('Ошибка при сохранении смены: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDelete = async () => {
    if (!editingSchedule) return;
    if (!confirm('Вы уверены, что хотите удалить эту смену?')) return;
    
    try {
      await schedulesApi.delete(editingSchedule.id);
      await loadSchedulesData();
      handleCloseModal();
    } catch (error: any) {
      console.error('Error deleting schedule:', error);
      alert('Ошибка при удалении смены: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getScheduleForDoctor = useCallback((doctorId: number, date: string) => {
    return schedules.find(s => {
      const scheduleDoctorId = typeof s.doctor === 'object' && s.doctor?.id 
        ? s.doctor.id 
        : (s.doctor_id || (typeof s.doctor === 'number' ? s.doctor : null));
      if (scheduleDoctorId !== doctorId) return false;
      const scheduleDate = s.work_date?.split('T')[0];
      return scheduleDate === date;
    });
  }, [schedules]);

  const getLoadPercentage = (schedule: Schedule | undefined, doctor: Doctor): number => {
    if (!schedule || schedule.is_day_off !== 0) return 0;
    const maxUp = doctor.max_up_per_day || 120;
    const plannedUp = schedule.planned_up || 0;
    return maxUp > 0 ? (plannedUp / maxUp) * 100 : 0;
  };

  const getLoadStatus = (schedule: Schedule | undefined, doctor: Doctor): 'normal' | 'warning' | 'overload' | 'empty' => {
    if (!schedule || schedule.is_day_off !== 0) return 'empty';
    const percentage = getLoadPercentage(schedule, doctor);
    if (percentage > 95) return 'overload';
    if (percentage >= 80) return 'warning';
    return 'normal';
  };

  const getStudiesCountForSchedule = useCallback((schedule: Schedule | undefined, doctorId: number, date: string): number => {
    if (!schedule) return 0;
    
    const scheduleDoctorId = getDoctorIdFromSchedule(schedule, doctorId);
    const scheduleDate = schedule.work_date?.split('T')[0] || date;
    
    return studies.filter(study => {
      // Получаем ID врача из исследования
      const studyDoctorId = study.diagnostician_id || 
        (typeof study.diagnostician === 'object' && study.diagnostician?.id ? study.diagnostician.id : null);
      
      // Получаем дату создания исследования (только дата, без времени)
      const studyDate = study.created_at ? study.created_at.split('T')[0] : null;
      
      // Сравниваем врача и дату
      return studyDoctorId === scheduleDoctorId && studyDate === scheduleDate;
    }).length;
  }, [studies]);

  const getStatusColor = (schedule: Schedule | undefined, doctor: Doctor): string => {
    if (!schedule) return 'bg-slate-100 text-slate-400';
    if (schedule.is_day_off !== 0) return 'bg-slate-100 text-slate-400';
    
    const percentage = getLoadPercentage(schedule, doctor);
    
    if (percentage > 95) return 'bg-red-100 text-red-700 border border-red-300';
    if (percentage >= 80) return 'bg-amber-100 text-amber-700 border border-amber-300';
    return 'bg-green-100 text-green-700 border border-green-300';
  };

  const calculateStats = useMemo(() => {
    const totalDoctors = doctors.length;
    let filledShifts = 0;
    let warningShifts = 0;
    let overloadShifts = 0;
    const totalPossibleShifts = totalDoctors * 7;

    doctors.forEach(doctor => {
      dates.forEach(date => {
        const schedule = getScheduleForDoctor(doctor.id, date);
        if (schedule && schedule.is_day_off === 0) {
          filledShifts++;
          const status = getLoadStatus(schedule, doctor);
          if (status === 'warning') warningShifts++;
          if (status === 'overload') overloadShifts++;
        }
      });
    });

    return {
      totalDoctors,
      filledShifts,
      totalPossibleShifts,
      warningShifts,
      overloadShifts,
    };
  }, [doctors, schedules, dates]);

  if (loading && schedules.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка расписания...</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
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

      {/* Карточки статистики */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="text-sm text-slate-600 mb-1">Всего врачей</div>
          <div className="text-2xl font-bold text-slate-900">{calculateStats.totalDoctors}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-1">
            <div className="text-sm text-slate-600">Смен заполнено</div>
            <CheckCircle2 size={16} className="text-green-600" />
          </div>
          <div className="text-2xl font-bold text-slate-900">
            {calculateStats.filledShifts}/{calculateStats.totalPossibleShifts}
          </div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-1">
            <div className="text-sm text-slate-600">Близко к лимиту</div>
            <AlertTriangle size={16} className="text-amber-600" />
          </div>
          <div className="text-2xl font-bold text-amber-600">{calculateStats.warningShifts}</div>
        </div>
        <div className="bg-white rounded-lg border border-slate-200 p-4">
          <div className="flex items-center justify-between mb-1">
            <div className="text-sm text-slate-600">Перегрузки</div>
            <AlertCircle size={16} className="text-red-600" />
          </div>
          <div className="text-2xl font-bold text-red-600">{calculateStats.overloadShifts}</div>
        </div>
      </div>

      {/* Кнопки действий */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <button className="px-4 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <RefreshCw size={16} className="mr-2" />
            Очистить неделю
          </button>
          <button className="px-4 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <Search size={16} className="mr-2" />
            Балансировать нагрузку
          </button>
          <button className="px-4 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <Search size={16} className="mr-2" />
            Найти пробелы
          </button>
          <button className="px-4 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <Printer size={16} className="mr-2" />
            Печать
          </button>
        </div>
        <div className="flex items-center space-x-2">
          <button className="px-4 py-2 bg-white border border-slate-300 rounded-md text-sm hover:bg-slate-50 flex items-center">
            <Copy size={16} className="mr-2" />
            Копировать неделю
          </button>
          <button className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700 font-medium">
            Сгенерировать план
          </button>
        </div>
      </div>

      <div className="text-sm text-slate-600 bg-slate-50 px-4 py-2 rounded-md">
        <span className="font-medium">Неделя:</span> {new Date(dates[0]).toLocaleDateString('ru-RU')} — {new Date(dates[6]).toLocaleDateString('ru-RU')}
      </div>

      {/* Легенда */}
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="text-sm font-semibold text-slate-700 mb-2">Индикаторы нагрузки</div>
        <div className="flex items-center space-x-6 text-xs">
          <div className="flex items-center space-x-2">
            <div className="w-4 h-4 rounded bg-green-100 border border-green-300"></div>
            <span className="text-slate-600">Норма (&lt;80%)</span>
          </div>
          <div className="flex items-center space-x-2">
            <div className="w-4 h-4 rounded bg-amber-100 border border-amber-300"></div>
            <span className="text-slate-600">Близко к лимиту (80-95%)</span>
          </div>
          <div className="flex items-center space-x-2">
            <div className="w-4 h-4 rounded bg-red-100 border border-red-300"></div>
            <span className="text-slate-600">Перегруз (&gt;95%)</span>
          </div>
        </div>
      </div>

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
                    const studiesCount = getStudiesCountForSchedule(schedule, doc.id, date);
                    return (
                      <td 
                        key={date} 
                        className="px-6 py-4 text-center cursor-pointer hover:bg-blue-50 transition-colors"
                        onClick={() => handleOpenModal(doc.id, date, schedule)}
                      >
                        {schedule ? (
                          <div className="space-y-1">
                            <div className={`inline-flex flex-col items-center px-3 py-2 rounded-lg text-xs font-medium ${getStatusColor(schedule, doc)}`}>
                              <div className="font-semibold">
                                {schedule.time_start?.substring(0, 5) || '—'}–{schedule.time_end?.substring(0, 5) || '—'}
                              </div>
                              {schedule.planned_up > 0 && (
                                <div className="mt-1 font-bold">
                                  {schedule.planned_up} УП
                                </div>
                              )}
                            </div>
                            {studiesCount > 0 && (
                              <div className="text-xs text-slate-600 mt-1">
                                Исследований: {studiesCount}
                              </div>
                            )}
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

      {/* Информационная панель */}
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="text-sm font-semibold text-red-900 mb-2">Как работает планирование</div>
        <ul className="text-xs text-red-800 space-y-1">
          <li>• Кликните на ячейку со сменой, чтобы отредактировать время и план по УП.</li>
          <li>• Кнопка «Сгенерировать план» автоматически распределит смены с учётом максимальной нагрузки врачей и выходных дней.</li>
          <li>• Красным выделяются перегрузки (&gt;95% от максимума УП), жёлтым — близкие к лимиту (80-95%).</li>
        </ul>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full mx-4">
            <div className="flex justify-between items-center p-6 border-b border-slate-200">
              <h3 className="text-xl font-bold text-slate-900">
                {editingSchedule ? 'Редактировать смену' : 'Добавить смену'}
              </h3>
              <button
                onClick={handleCloseModal}
                className="text-slate-400 hover:text-slate-600"
              >
                <X size={24} />
              </button>
            </div>
            
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Врач
                </label>
                <select
                  value={formData.doctor_id}
                  onChange={(e) => setFormData({ ...formData, doctor_id: parseInt(e.target.value) })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                >
                  {doctors.map((doc) => (
                    <option key={doc.id} value={doc.id}>
                      {doc.fio_alias}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Дата
                </label>
                <input
                  type="date"
                  value={formData.work_date}
                  onChange={(e) => setFormData({ ...formData, work_date: e.target.value })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Время начала
                  </label>
                  <input
                    type="time"
                    value={formData.time_start}
                    onChange={(e) => setFormData({ ...formData, time_start: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Время окончания
                  </label>
                  <input
                    type="time"
                    value={formData.time_end}
                    onChange={(e) => setFormData({ ...formData, time_end: e.target.value })}
                    className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Планируемые УП
                </label>
                <input
                  type="number"
                  value={formData.planned_up}
                  onChange={(e) => setFormData({ ...formData, planned_up: parseInt(e.target.value) || 0 })}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  min="0"
                />
              </div>

              <div className="flex items-center">
                <input
                  type="checkbox"
                  id="is_day_off"
                  checked={formData.is_day_off === 1}
                  onChange={(e) => setFormData({ ...formData, is_day_off: e.target.checked ? 1 : 0 })}
                  className="w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500"
                />
                <label htmlFor="is_day_off" className="ml-2 text-sm font-medium text-slate-700">
                  Выходной день
                </label>
              </div>

              <div className="flex space-x-3 pt-4">
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700"
                >
                  {editingSchedule ? 'Сохранить' : 'Добавить'}
                </button>
                {editingSchedule && (
                  <button
                    type="button"
                    onClick={handleDelete}
                    className="px-4 py-2 bg-red-600 text-white rounded-md font-medium hover:bg-red-700"
                  >
                    Удалить
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCloseModal}
                  className="flex-1 px-4 py-2 bg-slate-200 text-slate-700 rounded-md font-medium hover:bg-slate-300"
                >
                  Отмена
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};