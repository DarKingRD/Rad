import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { schedulesApi, doctorsApi, studiesApi } from '../../services/api';
import {
  ChevronLeft,
  ChevronRight,
  X,
  CheckCircle2,
  AlertCircle,
  Search,
  CalendarDays,
  SlidersHorizontal,
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

type DoctorRecord = Doctor & Record<string, unknown>;

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

const parseLocalDate = (value: string) => {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
};

const getStartOfWeek = (date: Date) => {
  const startOfWeek = new Date(date);
  const day = startOfWeek.getDay();
  const diff = startOfWeek.getDate() - day + (day === 0 ? -6 : 1);

  startOfWeek.setDate(diff);
  startOfWeek.setHours(0, 0, 0, 0);

  return startOfWeek;
};

const getDayStatusLabel = (schedule?: Schedule | null) => {
  if (!schedule) return '—';
  return schedule.day_status_label || DAY_STATUS_OPTIONS.find((item) => item.value === schedule.day_status)?.label || '—';
};

const getBooleanLike = (value: unknown, defaultValue = true): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') {
    return !['false', '0', 'no', 'нет', 'ложь', 'inactive', 'архив', 'уволен'].includes(value.toLowerCase().trim());
  }
  return defaultValue;
};

const getErrorMessage = (error: unknown) => {
  const responseDetail =
    typeof error === 'object' && error !== null
      ? (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
      : null;

  if (responseDetail) return String(responseDetail);
  if (error instanceof Error) return error.message;
  return 'неизвестная ошибка';
};

const isDoctorActive = (doctor: Doctor): boolean => {
  const doctorRecord = doctor as DoctorRecord;
  const activeFlag = doctorRecord.is_active ?? doctorRecord.active ?? true;
  if (!getBooleanLike(activeFlag, true)) return false;

  const endDateRaw =
    doctorRecord.work_end_date ??
    doctorRecord.end_work_date ??
    doctorRecord.employment_end_date ??
    doctorRecord.date_end ??
    doctorRecord.end_date ??
    doctorRecord.fired_at ??
    doctorRecord.dismissal_date ??
    doctorRecord.end_work;

  if (!endDateRaw) return true;

  const endDateText = String(endDateRaw).trim();
  if (!endDateText || ['31.12.9999', '9999-12-31', '2999-12-31'].includes(endDateText)) return true;

  const normalized = endDateText.includes('.')
    ? endDateText.split('.').reverse().join('-')
    : endDateText.split('T')[0];
  const endDate = new Date(`${normalized}T23:59:59`);

  return Number.isNaN(endDate.getTime()) || endDate >= new Date();
};

const normalizeText = (value?: string | null) =>
  (value || '').toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();

const isDisplayableModality = (value?: string | null) => {
  const normalized = normalizeText(value);
  if (!normalized) return false;

  // Должности/статусы не выводим в строке врача и не используем как модальности.
  if (normalized.includes('диагност')) return false;
  if (normalized.includes('врач')) return false;
  if (['рентгенолог', 'radiologist', 'doctor'].includes(normalized)) return false;

  return true;
};

const getDoctorModalities = (doctor: Doctor): string[] => {
  const doctorRecord = doctor as DoctorRecord;
  const raw = [
    doctorRecord.modality,
    doctorRecord.modalities,
    doctorRecord.modality_names,
    doctorRecord.available_modalities,
    doctorRecord.specializations,
  ];

  const values = raw
    .flatMap((item) => (Array.isArray(item) ? item : item ? [item] : []))
    .map((item) => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object') {
        const obj = item as Record<string, unknown>;
        return String(obj.name ?? obj.title ?? obj.label ?? obj.modality ?? obj.modality_name ?? '');
      }
      return '';
    })
    .map((item) => item.trim())
    .filter(isDisplayableModality);

  return Array.from(new Set(values));
};

export const ShiftPlanningView: React.FC = () => {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [studies, setStudies] = useState<Study[]>([]);
  const [initialLoading, setInitialLoading] = useState(true);
  const [scheduleLoading, setScheduleLoading] = useState(false);

  const [currentDate, setCurrentDate] = useState<Date>(new Date());
  const [doctorSearch, setDoctorSearch] = useState('');
  const [selectedModality, setSelectedModality] = useState<string>('all');
  const [forecastRefreshKey, setForecastRefreshKey] = useState(0);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<Schedule | null>(null);
  const [modalError, setModalError] = useState<string | null>(null);
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
    const startOfWeek = getStartOfWeek(currentDate);

    for (let i = 0; i < 7; i++) {
      const date = new Date(startOfWeek);
      date.setDate(date.getDate() + i);
      result.push(formatLocalDate(date));
    }

    return result;
  }, [currentDate]);

  const weekRangeLabel = useMemo(() => {
    const start = parseLocalDate(dates[0]).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long' });
    const end = parseLocalDate(dates[6]).toLocaleDateString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric' });
    return `${start} — ${end}`;
  }, [dates]);

  const weekTitle = useMemo(() => {
    const selectedWeekStart = dates[0];
    const todayWeekStart = formatLocalDate(getStartOfWeek(new Date()));
    return selectedWeekStart === todayWeekStart ? 'Текущая неделя' : 'Выбранная неделя';
  }, [dates]);

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
      }),
      studiesApi.getAll({
        date_from: dates[0],
        date_to: dates[6],
      }),
    ]);
    setSchedules(schedulesData);
    setStudies(studiesData);
  }, [dates]);

  useEffect(() => {
    loadDoctors();
  }, [loadDoctors]);

  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      try {
        setScheduleLoading(true);
        await loadSchedulesData();
      } catch (err) {
        console.error('Error loading data:', err);
      } finally {
        if (isMounted) {
          setScheduleLoading(false);
          setInitialLoading(false);
        }
      }
    };

    loadData();

    return () => {
      isMounted = false;
    };
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

  const handleWeekPickerChange = (value: string) => {
    if (!value) return;
    setCurrentDate(parseLocalDate(value));
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
    setModalError(null);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingSchedule(null);
    setModalError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);
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
    } catch (error) {
      console.error('Error saving schedule:', error);
      setModalError(`Не удалось сохранить смену: ${getErrorMessage(error)}`);
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
    } catch (error) {
      console.error('Error deleting schedule:', error);
      setModalError(`Не удалось удалить смену: ${getErrorMessage(error)}`);
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

    if (percentage > 95) return 'bg-blue-100 text-blue-700 border border-blue-300';
    if (percentage >= 80) return 'bg-blue-100 text-blue-700 border border-blue-300';
    return 'bg-blue-100 text-blue-700 border border-blue-300';
  };

  const activeDoctors = useMemo(() => doctors.filter(isDoctorActive), [doctors]);

  const modalityOptions = useMemo(() => {
    const options = new Set<string>();

    activeDoctors.forEach((doctor) => {
      getDoctorModalities(doctor).forEach((item) => options.add(item));
    });

    return Array.from(options).sort((a, b) => a.localeCompare(b, 'ru'));
  }, [activeDoctors]);

  const visibleDoctors = useMemo(() => {
    const normalizedSearch = normalizeText(doctorSearch);

    return activeDoctors.filter((doctor) => {
      const doctorModalities = getDoctorModalities(doctor);
      const matchesSearch = !normalizedSearch ||
        normalizeText(doctor.fio_alias).includes(normalizedSearch) ||
        doctorModalities.some((item) => normalizeText(item).includes(normalizedSearch));
      const matchesModality = selectedModality === 'all' || doctorModalities.includes(selectedModality);

      return matchesSearch && matchesModality;
    });
  }, [activeDoctors, doctorSearch, selectedModality]);

  const resetFilters = () => {
    setDoctorSearch('');
    setSelectedModality('all');
  };

  const hasActiveFilters = doctorSearch.trim() !== '' || selectedModality !== 'all';

  const calculateStats = useMemo(() => {
    const totalDoctors = visibleDoctors.length;
    let filledShifts = 0;
    let warningShifts = 0;
    let overloadShifts = 0;
    const totalPossibleShifts = totalDoctors * 7;

    visibleDoctors.forEach((doctor) => {
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
  }, [visibleDoctors, dates, getScheduleForDoctor]);

  if (initialLoading && schedules.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-slate-500">Загрузка расписания...</div>
      </div>
    );
  }

  return (
    <div className="space-y-5 md:space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight text-slate-950">Планирование смен</h2>
        <p className="mt-1 text-sm text-slate-500">График врачей и прогноз потребности в специалистах</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:gap-4">
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Врачей в выборке</div>
          <div className="text-2xl font-bold tracking-tight text-slate-950">{calculateStats.totalDoctors}</div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Рабочих смен</div>
            <CheckCircle2 size={14} className="text-blue-600" />
          </div>
          <div className="text-2xl font-bold tracking-tight text-slate-950">
            {calculateStats.filledShifts}/{calculateStats.totalPossibleShifts}
          </div>
        </div>
      </div>

      <ShiftForecastPanel refreshKey={forecastRefreshKey} doctors={activeDoctors} />

      <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:p-4">
        <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-center">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(240px,320px)]">
            <label className="relative block">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                value={doctorSearch}
                onChange={(e) => setDoctorSearch(e.target.value)}
                placeholder="Поиск врача по ФИО"
                className="h-11 w-full rounded-xl border border-slate-200 bg-slate-50/80 pl-10 pr-3 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:bg-white focus:ring-4 focus:ring-blue-100"
              />
            </label>

            <label className="relative block">
              <SlidersHorizontal size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <select
                value={selectedModality}
                onChange={(e) => setSelectedModality(e.target.value)}
                className="unstyled-select h-11 w-full appearance-none rounded-xl border border-slate-200 bg-slate-50/80 pl-12 pr-9 text-sm text-slate-900 outline-none transition focus:border-blue-300 focus:bg-white focus:ring-4 focus:ring-blue-100"
              >
                <option value="all">Все модальности</option>
                {modalityOptions.map((modality) => (
                  <option key={modality} value={modality}>{modality}</option>
                ))}
              </select>
            </label>
          </div>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={resetFilters}
              className="h-11 rounded-xl border border-slate-200 px-4 text-sm font-semibold text-slate-600 transition hover:bg-slate-50"
            >
              Сбросить фильтры
            </button>
          )}
        </div>

        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50/70 p-2">
          <div className="grid gap-2 lg:grid-cols-[auto_minmax(240px,1fr)_auto] lg:items-center">
            <button
              type="button"
              onClick={handlePrevWeek}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-700 transition hover:bg-white hover:shadow-sm"
            >
              <ChevronLeft size={17} />
              <span className="hidden sm:inline">Предыдущая</span>
            </button>

            <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center sm:justify-center">
              <div className="rounded-xl bg-white px-4 py-2 text-center shadow-sm ring-1 ring-slate-200">
                <div className="text-sm font-bold text-slate-950">{weekTitle}</div>
                <div className="text-xs text-slate-500">{weekRangeLabel}</div>
              </div>

              <label className="inline-flex h-11 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700">
                <CalendarDays size={16} />
                <span>Выбрать дату</span>
                <input
                  type="date"
                  value={formatLocalDate(currentDate)}
                  onChange={(e) => handleWeekPickerChange(e.target.value)}
                  className="h-8 w-[8.8rem] rounded-xl border border-slate-200 bg-slate-50 px-2 text-xs text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
              </label>

              <button
                type="button"
                onClick={handleToday}
                className="h-11 rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-blue-200 hover:text-blue-700"
              >
                Сегодня
              </button>
            </div>

            <button
              type="button"
              onClick={handleNextWeek}
              className="inline-flex h-11 items-center justify-center gap-2 rounded-xl px-3 text-sm font-semibold text-slate-700 transition hover:bg-white hover:shadow-sm"
            >
              <span className="hidden sm:inline">Следующая</span>
              <ChevronRight size={17} />
            </button>
          </div>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {scheduleLoading && (
          <div className="absolute inset-x-0 top-0 z-20 flex items-center justify-center border-b border-blue-100 bg-blue-50/90 px-4 py-2 text-xs font-semibold text-blue-700">
            Обновляем расписание выбранной недели…
          </div>
        )}
        <div className="overflow-x-auto">
          <div className="min-w-max">
          <table className="w-full text-left text-sm" style={{ minWidth: '840px' }}>
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="px-4 md:px-6 py-4 font-semibold text-slate-700 sticky left-0 bg-slate-50 z-10">Врач</th>
                {dates.map((date) => {
                  const d = parseLocalDate(date);
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
              {visibleDoctors.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-50">
                  <td className="px-4 md:px-6 py-4 font-medium text-slate-900 sticky left-0 bg-white z-10 shadow-sm">
                    <div className="text-sm">{doc.fio_alias}</div>
                    {getDoctorModalities(doc).length > 0 && (
                      <div className="mt-2 flex max-w-[240px] flex-wrap gap-1">
                        {getDoctorModalities(doc).slice(0, 2).map((modality) => (
                          <span
                            key={`${doc.id}-${modality}`}
                            className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium leading-none text-slate-600"
                          >
                            {modality}
                          </span>
                        ))}
                        {getDoctorModalities(doc).length > 2 && (
                          <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium leading-none text-slate-500">
                            +{getDoctorModalities(doc).length - 2}
                          </span>
                        )}
                      </div>
                    )}
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
              {visibleDoctors.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-6 py-10 text-center text-sm text-slate-500">
                    По выбранным фильтрам врачи не найдены.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          </div>
        </div>
      </div>

      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-950/50 sm:items-center sm:p-4">
          <div className="max-h-[95dvh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white shadow-lg sm:rounded-xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white p-5">
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
              {modalError && (
                <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-700">
                  <AlertCircle size={17} className="mt-0.5 shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

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
                  {activeDoctors.map((doc) => (
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
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
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
                    className="rounded-xl bg-amber-600 px-4 py-2.5 font-semibold text-white hover:bg-amber-700"
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
