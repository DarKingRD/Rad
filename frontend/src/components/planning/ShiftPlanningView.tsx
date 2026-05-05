import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { schedulesApi, doctorsApi, studiesApi } from '../../services/api';
import {
  ChevronLeft,
  ChevronRight,
  X,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Copy,
  Printer,
  RefreshCw,
  Search,
} from 'lucide-react';
import { Schedule, Doctor, Study } from '../../types';
import { ShiftForecastPanel } from './ShiftForecastPanel';

interface ScheduleFormData {
  doctor_id: number;
  work_date: string;
  time_start: string;
  time_end: string;
  break_start: string;
  break_end: string;
  day_status: number;
  planned_up: number;
}

const DAY_STATUS_OPTIONS = [
  { value: 0, label: 'Рабочий день' },
  { value: 1, label: 'Выходной' },
  { value: 2, label: 'Отпуск / плановое отсутствие' },
  { value: 3, label: 'Больничный / иное отсутствие' },
  { value: 4, label: 'Неизвестный статус' },
  { value: 5, label: 'До начала работы' },
  { value: 6, label: 'После окончания работы' },
];

const formatLocalDate = (d: Date) => {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getDayStatusLabel = (schedule?: Schedule | null) => {
  if (!schedule) return '—';
  return schedule.day_status_label || DAY_STATUS_OPTIONS.find((item) => item.value === schedule.day_status)?.label || '—';
};

export const ShiftPlanningView: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [studies, setStudies] = useState<Study[]>([]);
  const [loading, setLoading] = useState(true);

  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [selectedDoctor, setSelectedDoctor] = useState<number | 'all'>('all');
  const [forecastRefreshKey, setForecastRefreshKey] = useState(0);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [formData, setFormData] = useState<ScheduleFormData>({
    doctor_id: 0,
    work_date: '',
    time_start: '09:00',
    time_end: '18:00',
    break_start: '12:00',
    break_end: '13:00',
    day_status: 0,
    planned_up: 0,
  });

  const dates = useMemo(() => {
    const result: string[] = [];
    const startOfWeek = new Date(currentDate);
    const day = startOfWeek.getDay();
    const diff = startOfWeek.getDate() - day + (day === 0 ? -6 : 1);

    startOfWeek.setDate(diff);
    startOfWeek.setHours(0, 0, 0, 0);

    for (let i = 0; i < 7; i++) {
      const date = new Date(startOfWeek);
      date.setDate(date.getDate() + i);
      result.push(formatLocalDate(date));
    }

    return result;
  }, [currentDate]);

  const getDoctorIdFromSchedule = (schedule: Schedule, fallback: number): number => {
    if (typeof schedule.doctor === 'object' && schedule.doctor?.id) {
      return schedule.doctor.id;
    }
    return schedule.doctor_id || (typeof schedule.doctor === 'number' ? schedule.doctor : fallback);
  };

  const isWorkingSchedule = (schedule?: Schedule | null) => !!schedule && schedule.day_status === 0;

  const loadDoctors = useCallback(async () => {
    try {
      const doctorsData = await doctorsApi.getAll();
      setDoctors(doctorsData);
    } catch (err) {
      console.error('Error loading doctors:', err);
    }
  }, []);

  const loadSchedulesData = useCallback(async () => {
    const [schedulesData, studiesData] = await Promise.all([
      schedulesApi.getAll({
        date_from: dates[0],
        date_to: dates[6],
        ...(selectedDoctor !== 'all' && { doctor_id: Number(selectedDoctor) }),
      }),
      studiesApi.getAll({
        date_from: dates[0],
        date_to: dates[6],
      }),
    ]);
    setSchedules(schedulesData);
    setStudies(studiesData);
  }, [dates, selectedDoctor]);

  useEffect(() => {
    loadDoctors();
  }, [loadDoctors]);

  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        await loadSchedulesData();
      } catch (err) {
        console.error('Error loading data:', err);
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, [loadSchedulesData]);

  const handlePrevWeek = () => {
    setCurrentDate((prev) => {
      const newDate = new Date(prev);
      newDate.setDate(newDate.getDate() - 7);
      return newDate;
    });
  };

  const handleNextWeek = () => {
    setCurrentDate((prev) => {
      const newDate = new Date(prev);
      newDate.setDate(newDate.getDate() + 7);
      return newDate;
    });
  };

  const handleToday = () => {
    setCurrentDate(new Date());
  };

  const handleOpenModal = (doctorId: number, date: string, schedule?: Schedule) => {
    if (schedule) {
      setEditingSchedule(schedule);
      setFormData({
        doctor_id: getDoctorIdFromSchedule(schedule, doctorId),
        work_date: schedule.work_date?.split('T')[0] || date,
        time_start: schedule.time_start?.substring(0, 5) || '09:00',
        time_end: schedule.time_end?.substring(0, 5) || '18:00',
        break_start: schedule.break_start?.substring(0, 5) || '12:00',
        break_end: schedule.break_end?.substring(0, 5) || '13:00',
        day_status: typeof schedule.day_status === 'number' ? schedule.day_status : (schedule.is_day_off ? 1 : 0),
        planned_up: schedule.planned_up || 0,
      });
    } else {
      setEditingSchedule(null);
      setFormData({
        doctor_id: doctorId,
        work_date: date,
        time_start: '09:00',
        time_end: '18:00',
        break_start: '12:00',
        break_end: '13:00',
        day_status: 0,
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
      const isWorking = formData.day_status === 0;
      const submitData = {
        doctor_id: formData.doctor_id,
        work_date: formData.work_date,
        time_start: isWorking ? formData.time_start : null,
        time_end: isWorking ? formData.time_end : null,
        break_start: isWorking ? (formData.break_start || null) : null,
        break_end: isWorking ? (formData.break_end || null) : null,
        day_status: formData.day_status,
        planned_up: isWorking ? formData.planned_up : 0,
      };

      if (editingSchedule) {
        await schedulesApi.update(editingSchedule.id, submitData);
      } else {
        await schedulesApi.create(submitData);
      }

      await loadSchedulesData();
      setForecastRefreshKey((prev) => prev + 1);
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
      setForecastRefreshKey((prev) => prev + 1);
      handleCloseModal();
    } catch (error: any) {
      console.error('Error deleting schedule:', error);
      alert('Ошибка при удалении смены: ' + (error.response?.data?.detail || error.message));
    }
  };

  const getScheduleForDoctor = useCallback((doctorId: number, date: string) => {
    return schedules.find((s) => {
      const scheduleDoctorId = typeof s.doctor === 'object' && s.doctor?.id
        ? s.doctor.id
        : (s.doctor_id || (typeof s.doctor === 'number' ? s.doctor : null));
      if (scheduleDoctorId !== doctorId) return false;
      const scheduleDate = s.work_date?.split('T')[0];
      return scheduleDate === date;
    });
  }, [schedules]);

  const getLoadPercentage = (schedule: Schedule | undefined, doctor: Doctor): number => {
    if (!isWorkingSchedule(schedule)) return 0;
    const maxUp = doctor.max_up_per_day || 8;
    const plannedUp = schedule?.planned_up || 0;
    return maxUp > 0 ? (plannedUp / maxUp) * 100 : 0;
  };

  const getLoadStatus = (schedule: Schedule | undefined, doctor: Doctor): 'normal' | 'warning' | 'overload' | 'empty' => {
    if (!isWorkingSchedule(schedule)) return 'empty';
    const percentage = getLoadPercentage(schedule, doctor);
    if (percentage > 95) return 'overload';
    if (percentage >= 80) return 'warning';
    return 'normal';
  };

  const getStudiesCountForSchedule = useCallback((schedule: Schedule | undefined, doctorId: number, date: string): number => {
    if (!isWorkingSchedule(schedule)) return 0;

    const scheduleDoctorId = getDoctorIdFromSchedule(schedule!, doctorId);
    const scheduleDate = schedule!.work_date?.split('T')[0] || date;

    return studies.filter((study) => {
      const studyDoctorId = study.diagnostician_id ||
        (typeof study.diagnostician === 'object' && study.diagnostician?.id ? study.diagnostician.id : null);
      const studyDate = study.created_at ? study.created_at.split('T')[0] : null;
      return studyDoctorId === scheduleDoctorId && studyDate === scheduleDate;
    }).length;
  }, [studies]);

  const getStatusColor = (schedule: Schedule | undefined, doctor: Doctor): string => {
    if (!schedule) return 'bg-slate-100 text-slate-400';
    if (!isWorkingSchedule(schedule)) return 'bg-slate-100 text-slate-700 border border-slate-300';

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

    doctors.forEach((doctor) => {
      dates.forEach((date) => {
        const schedule = getScheduleForDoctor(doctor.id, date);
        if (isWorkingSchedule(schedule)) {
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
  }, [doctors, dates, getScheduleForDoctor]);

  if (loading && schedules.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка расписания...</div>
      </div>
    );
  }

  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950">Планирование смен</h2>
          <p className="mt-1 text-sm text-slate-500">График врачей, статусы дней и прогноз потребности</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <select
            value={selectedDoctor}
            onChange={(e) => setSelectedDoctor(e.target.value === 'all' ? 'all' : Number(e.target.value))}
            className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm sm:flex-none sm:min-w-[240px]"
          >
            <option value="all">Все врачи</option>
            {doctors.map((doc) => (
              <option key={doc.id} value={doc.id}>{doc.fio_alias}</option>
            ))}
          </select>

          <div className="flex items-center gap-1 rounded-2xl border border-slate-200 bg-white p-1 shadow-sm">
            <button onClick={handlePrevWeek} className="rounded-xl p-2 text-slate-700 hover:bg-slate-100">
              <ChevronLeft size={16} />
            </button>
            <button onClick={handleToday} className="rounded-xl px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 whitespace-nowrap">
              Сегодня
            </button>
            <button onClick={handleNextWeek} className="rounded-xl p-2 text-slate-700 hover:bg-slate-100">
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Всего врачей</div>
          <div className="text-2xl font-bold tracking-tight text-slate-950">{calculateStats.totalDoctors}</div>
        </div>
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Рабочих смен</div>
            <CheckCircle2 size={14} className="text-green-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-slate-950">
            {calculateStats.filledShifts}/{calculateStats.totalPossibleShifts}
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Близко к лимиту</div>
            <AlertTriangle size={14} className="text-amber-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-amber-600">{calculateStats.warningShifts}</div>
        </div>
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Перегрузки</div>
            <AlertCircle size={14} className="text-red-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-red-600">{calculateStats.overloadShifts}</div>
        </div>
      </div>

      <ShiftForecastPanel refreshKey={forecastRefreshKey} doctors={doctors}/>

      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <button className="hidden items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 md:flex">
            <RefreshCw size={16} />Очистить неделю
          </button>
          <button className="hidden items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 md:flex">
            <Search size={16} />Балансировать нагрузку
          </button>
          <button className="hidden items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 md:flex">
            <Printer size={16} />Печать
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button className="hidden items-center gap-1.5 rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 md:flex">
            <Copy size={16} />Копировать неделю
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white/80 px-4 py-3 text-xs text-slate-600 shadow-sm md:text-sm">
        <span className="font-medium">Неделя:</span> {new Date(dates[0]).toLocaleDateString('ru-RU')} — {new Date(dates[6]).toLocaleDateString('ru-RU')}
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm shadow-slate-200/60">
        <div className="overflow-x-auto">
          <div className="min-w-max">
          <table className="w-full text-left text-sm" style={{ minWidth: '840px' }}>
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 md:px-6 py-4 font-semibold text-slate-700 sticky left-0 bg-slate-50 z-10">Врач</th>
                {dates.map((date) => {
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
                  <td className="px-4 md:px-6 py-4 font-medium text-slate-900 sticky left-0 bg-white z-10 shadow-sm">
                    <div className="text-sm">{doc.fio_alias}</div>
                    <div className="text-xs text-slate-500">{doc.specialty}</div>
                  </td>
                  {dates.map((date) => {
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
                            {isWorkingSchedule(schedule) ? (
                              <>
                                <div className={`inline-flex flex-col items-center px-3 py-2 rounded-lg text-xs font-medium ${getStatusColor(schedule, doc)}`}>
                                  <div className="font-semibold">
                                    {schedule.time_start?.substring(0, 5) || '—'}–{schedule.time_end?.substring(0, 5) || '—'}
                                  </div>
                                  {schedule.break_start && schedule.break_end && (
                                    <div className="mt-0.5 text-[10px] opacity-75">
                                      ☕ {schedule.break_start.substring(0, 5)}–{schedule.break_end.substring(0, 5)}
                                    </div>
                                  )}
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
                              </>
                            ) : (
                              <div className={`inline-flex flex-col items-center px-3 py-2 rounded-lg text-xs font-medium ${getStatusColor(schedule, doc)}`}>
                                <div className="font-semibold">{getDayStatusLabel(schedule)}</div>
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
      </div>

      <div className="rounded-2xl border border-blue-200 bg-blue-50/80 p-4">
        <div className="mb-2 text-sm font-semibold text-blue-900">Подсказка по day_status</div>
        <ul className="grid gap-1 text-xs text-blue-800 sm:grid-cols-2 lg:grid-cols-3">
          <li>• 0 — рабочий день.</li>
          <li>• 1 — выходной.</li>
          <li>• 2 — отпуск / плановое отсутствие.</li>
          <li>• 3 — больничный / иное отсутствие.</li>
          <li>• 5 — до начала работы, 6 — после окончания работы.</li>
        </ul>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4">
          <div className="max-h-[95dvh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-white shadow-2xl sm:rounded-3xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/95 p-5 backdrop-blur">
              <h3 className="text-lg font-bold text-slate-900">
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
                  className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
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
                  className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Статус дня
                </label>
                <select
                  value={formData.day_status}
                  onChange={(e) => setFormData({ ...formData, day_status: Number(e.target.value) })}
                  className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                >
                  {DAY_STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
              </div>

              {formData.day_status === 0 && (
                <>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">
                        Время начала
                      </label>
                      <input
                        type="time"
                        value={formData.time_start}
                        onChange={(e) => setFormData({ ...formData, time_start: e.target.value })}
                        className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
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
                        className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                        required
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">
                      ☕ Перерыв (обед)
                    </label>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-slate-500 mb-1">Начало</label>
                        <input
                          type="time"
                          value={formData.break_start}
                          onChange={(e) => setFormData({ ...formData, break_start: e.target.value })}
                          className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-slate-500 mb-1">Конец</label>
                        <input
                          type="time"
                          value={formData.break_end}
                          onChange={(e) => setFormData({ ...formData, break_end: e.target.value })}
                          className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                        />
                      </div>
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
                      className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
                      min="0"
                    />
                  </div>
                </>
              )}

              {formData.day_status !== 0 && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
                  Для нерабочих статусов время смены и УП при сохранении будут сброшены.
                </div>
              )}

              <div className="flex flex-col gap-3 pt-4 sm:flex-row">
                <button
                  type="submit"
                  className="flex-1 rounded-xl bg-blue-600 px-4 py-2.5 font-semibold text-white hover:bg-blue-700"
                >
                  {editingSchedule ? 'Сохранить' : 'Добавить'}
                </button>
                {editingSchedule && (
                  <button
                    type="button"
                    onClick={handleDelete}
                    className="rounded-xl bg-red-600 px-4 py-2.5 font-semibold text-white hover:bg-red-700"
                  >
                    Удалить
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleCloseModal}
                  className="flex-1 rounded-xl bg-slate-100 px-4 py-2.5 font-semibold text-slate-700 hover:bg-slate-200"
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
