import { useEffect, useMemo, useState } from 'react';
import { Activity, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, Clock3, LogOut, RotateCcw, Settings, Stethoscope, XCircle } from 'lucide-react';
import { ApiClientError, authApi, doctorPortalApi } from '../../services/api';
import type { DoctorPeriodStats, DoctorPortalProfile, Schedule, Study } from '../../types';
import { getPriorityColor, getPriorityLabel, getStatusColor, getStatusLabel } from '../distribution/utils/distributionFormatters';

type DoctorPortalViewProps = {
  onLogout: () => void;
};

type StudyStatusFilter = 'confirmed' | 'signed';
type DoctorPortalTab = 'studies' | 'schedules';

const statusTabs: Array<{ key: StudyStatusFilter; label: string }> = [
  { key: 'confirmed', label: 'Назначено' },
  { key: 'signed', label: 'Выполнено' },
];

function monthStartString(date = new Date()) {
  return new Date(date.getFullYear(), date.getMonth(), 1).toISOString().split('T')[0];
}

function todayString(date = new Date()) {
  return date.toISOString().split('T')[0];
}

function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getMonthBounds(date: Date) {
  const start = new Date(date.getFullYear(), date.getMonth(), 1);
  const end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return {
    date_from: localDateString(start),
    date_to: localDateString(end),
  };
}

function getCalendarDays(date: Date) {
  const monthStart = new Date(date.getFullYear(), date.getMonth(), 1);
  const monthEnd = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const startOffset = (monthStart.getDay() + 6) % 7;
  const endOffset = 6 - ((monthEnd.getDay() + 6) % 7);
  const firstCell = new Date(monthStart);
  firstCell.setDate(monthStart.getDate() - startOffset);
  const lastCell = new Date(monthEnd);
  lastCell.setDate(monthEnd.getDate() + endOffset);

  const days: Date[] = [];
  const cursor = new Date(firstCell);
  while (cursor <= lastCell) {
    days.push(new Date(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

function formatDateTime(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function StatCard({
  title,
  stats,
}: {
  title: string;
  stats: DoctorPeriodStats;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
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

export function DoctorPortalView({ onLogout }: DoctorPortalViewProps) {
  const [profile, setProfile] = useState<DoctorPortalProfile | null>(null);
  const [studies, setStudies] = useState<Study[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [activeStatus, setActiveStatus] = useState<StudyStatusFilter>('confirmed');
  const [activeTab, setActiveTab] = useState<DoctorPortalTab>('studies');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date());
  const [selectedScheduleDate, setSelectedScheduleDate] = useState(() => localDateString(new Date()));
  const [selectedModalities, setSelectedModalities] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isUpdating, setIsUpdating] = useState<string | null>(null);
  const [isSavingModalities, setIsSavingModalities] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentUser = authApi.getCurrentUser();

  const listParams = useMemo(
    () => ({
      status: activeStatus,
      date_from: monthStartString(),
      date_to: todayString(),
    }),
    [activeStatus]
  );

  const loadData = async () => {
    setError(null);
    setIsLoading(true);
    try {
      const [nextProfile, nextStudies] = await Promise.all([
        doctorPortalApi.getMe(),
        doctorPortalApi.getStudies(listParams),
      ]);
      setProfile(nextProfile);
      setSelectedModalities(nextProfile.doctor.modality || []);
      setStudies(nextStudies);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Не удалось загрузить кабинет врача';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [listParams]);

  useEffect(() => {
    const params = getMonthBounds(calendarMonth);
    doctorPortalApi.getSchedules(params).then(setSchedules).catch(() => setSchedules([]));
  }, [calendarMonth]);

  const schedulesByDate = useMemo(() => {
    const map = new Map<string, Schedule>();
    schedules.forEach((schedule) => {
      map.set(schedule.work_date, schedule);
    });
    return map;
  }, [schedules]);

  const calendarDays = useMemo(() => getCalendarDays(calendarMonth), [calendarMonth]);
  const selectedSchedule = schedulesByDate.get(selectedScheduleDate) || null;
  const currentMonthLabel = calendarMonth.toLocaleDateString('ru-RU', {
    month: 'long',
    year: 'numeric',
  });

  const changeCalendarMonth = (delta: number) => {
    setCalendarMonth((current) => {
      const next = new Date(current.getFullYear(), current.getMonth() + delta, 1);
      setSelectedScheduleDate(localDateString(next));
      return next;
    });
  };

  const updateStatus = async (study: Study, status: 'signed' | 'pending' | 'confirmed') => {
    setIsUpdating(study.research_number);
    setError(null);
    try {
      await doctorPortalApi.updateStudyStatus(study.research_number, status);
      const [nextProfile, nextStudies] = await Promise.all([
        doctorPortalApi.getMe(),
        doctorPortalApi.getStudies(listParams),
      ]);
      setProfile(nextProfile);
      setStudies(nextStudies);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Не удалось обновить статус';
      setError(message);
    } finally {
      setIsUpdating(null);
    }
  };

  const toggleModality = (modality: string) => {
    setSelectedModalities((current) =>
      current.includes(modality)
        ? current.filter((item) => item !== modality)
        : [...current, modality]
    );
  };

  const saveModalities = async () => {
    setIsSavingModalities(true);
    setError(null);
    try {
      const nextProfile = await doctorPortalApi.updateModalities(selectedModalities);
      setProfile(nextProfile);
      setSelectedModalities(nextProfile.doctor.modality || []);
    } catch (err) {
      const message = err instanceof ApiClientError ? err.message : 'Не удалось сохранить специализации';
      setError(message);
    } finally {
      setIsSavingModalities(false);
    }
  };

  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 md:px-6">
          <div>
            <p className="text-sm text-slate-500">Кабинет врача</p>
            <h1 className="text-xl font-bold text-slate-950 md:text-2xl">
              {profile?.doctor.fio_alias || currentUser?.doctor_name || currentUser?.full_name || 'Врач'}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsSettingsOpen((value) => !value)}
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              title="Настройки"
            >
              <Settings size={18} />
            </button>
            <button
              type="button"
              onClick={loadData}
              className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              title="Обновить"
            >
              <RotateCcw size={18} />
            </button>
            <button
              type="button"
              onClick={onLogout}
              className="inline-flex h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              <LogOut size={17} />
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-5 md:px-6">
        {isSettingsOpen ? (
          <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-950">Настройки</h2>
                <p className="text-sm text-slate-500">Специализации врача</p>
              </div>
              <button
                type="button"
                onClick={saveModalities}
                disabled={isSavingModalities}
                className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
              >
                {isSavingModalities ? 'Сохраняем...' : 'Сохранить'}
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {(profile?.available_modalities || []).map((modality) => {
                const checked = selectedModalities.includes(modality);
                return (
                  <label
                    key={modality}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-3 text-sm font-semibold transition ${
                      checked
                        ? 'border-blue-200 bg-blue-50 text-blue-800'
                        : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleModality(modality)}
                      className="h-4 w-4 accent-blue-600"
                    />
                    <Stethoscope size={17} className={checked ? 'text-blue-600' : 'text-slate-400'} />
                    <span>{modality}</span>
                  </label>
                );
              })}
            </div>
          </section>
        ) : null}

        {error ? (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4">
          <StatCard title="Текущий месяц" stats={profile?.stats.current_month || { assigned: 0, completed: 0, pending: 0, completed_up: 0 }} />
        </section>

        <section className="mt-5 rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-950">
                {activeTab === 'studies' ? 'Исследования' : 'Смены'}
              </h2>
              <p className="text-sm text-slate-500">
                {activeTab === 'studies' ? 'Текущий месяц' : 'Ближайшие смены'}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {[
                { key: 'studies', label: 'Исследования' },
                { key: 'schedules', label: 'Смены' },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key as DoctorPortalTab)}
                  className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
                    activeTab === tab.key
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'text-slate-600 hover:text-slate-950'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {activeTab === 'studies' ? (
            <div className="border-b border-slate-100 px-4 py-3">
              <div className="inline-flex rounded-xl bg-slate-100 p-1">
                {statusTabs.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setActiveStatus(tab.key)}
                    className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
                      activeStatus === tab.key
                        ? 'bg-blue-600 text-white shadow-sm'
                        : 'text-slate-600 hover:text-slate-950'
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {activeTab === 'studies' ? (
          <div className="divide-y divide-slate-100">
            {isLoading ? (
              <div className="p-6 text-sm text-slate-500">Загрузка...</div>
            ) : studies.length === 0 ? (
              <div className="p-6 text-sm text-slate-500">Нет исследований в этом статусе</div>
            ) : (
              studies.map((study) => (
                <div key={study.research_number} className="grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
                  <div className="min-w-0">
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-950">{study.research_number}</span>
                      <span className={`rounded-lg border px-2 py-1 text-xs font-semibold ${getPriorityColor(study.priority)}`}>
                        {getPriorityLabel(study.priority)}
                      </span>
                      <span className={`rounded-lg px-2 py-1 text-xs font-semibold ${getStatusColor(study.status)}`}>
                        {getStatusLabel(study.status)}
                      </span>
                    </div>
                    <p className="truncate text-sm text-slate-600">{study.study_type?.name || 'Тип исследования не указан'}</p>
                    <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
                      <span className="inline-flex items-center gap-1">
                        <Clock3 size={14} />
                        {formatDateTime(study.created_at)}
                      </span>
                      <span>УП: {Number(study.study_type?.up_value || 0).toFixed(2)}</span>
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-2 md:justify-end">
                    {study.status !== 'signed' ? (
                      <button
                        type="button"
                        disabled={isUpdating === study.research_number}
                        onClick={() => updateStatus(study, 'signed')}
                        className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
                      >
                        <CheckCircle2 size={17} />
                        Выполнено
                      </button>
                    ) : null}
                    {study.status === 'confirmed' ? (
                      <button
                        type="button"
                        disabled={isUpdating === study.research_number}
                        onClick={() => updateStatus(study, 'pending')}
                        className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                      >
                        <XCircle size={17} />
                        Отказаться
                      </button>
                    ) : null}
                    {study.status !== 'confirmed' ? (
                      <button
                        type="button"
                        disabled={isUpdating === study.research_number}
                        onClick={() => updateStatus(study, 'confirmed')}
                        className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                      >
                        Вернуть
                      </button>
                    ) : null}
                  </div>
                </div>
              ))
            )}
          </div>
          ) : null}

          {activeTab === 'schedules' ? (
            <div className="p-4">
              <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-2">
                  <CalendarDays size={20} className="text-blue-600" />
                  <h3 className="text-base font-bold capitalize text-slate-950">{currentMonthLabel}</h3>
                </div>
                <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1">
                  <button
                    type="button"
                    onClick={() => changeCalendarMonth(-1)}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100"
                    title="Предыдущий месяц"
                  >
                    <ChevronLeft size={18} />
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const now = new Date();
                      setCalendarMonth(now);
                      setSelectedScheduleDate(localDateString(now));
                    }}
                    className="rounded-lg px-3 text-sm font-semibold text-slate-700 hover:bg-slate-100"
                  >
                    Сегодня
                  </button>
                  <button
                    type="button"
                    onClick={() => changeCalendarMonth(1)}
                    className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100"
                    title="Следующий месяц"
                  >
                    <ChevronRight size={18} />
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-7 gap-1 text-center text-xs font-semibold uppercase text-slate-500">
                {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => (
                  <div key={day} className="py-2">
                    {day}
                  </div>
                ))}
              </div>

              <div className="grid grid-cols-7 gap-1 md:gap-2">
                {calendarDays.map((day) => {
                  const dateKey = localDateString(day);
                  const schedule = schedulesByDate.get(dateKey);
                  const isCurrentMonth = day.getMonth() === calendarMonth.getMonth();
                  const isSelected = dateKey === selectedScheduleDate;
                  const isToday = dateKey === localDateString(new Date());
                  const isWorking = Boolean(schedule && !schedule.is_day_off);
                  const isDayOff = Boolean(schedule && schedule.is_day_off);

                  return (
                    <button
                      key={dateKey}
                      type="button"
                      onClick={() => setSelectedScheduleDate(dateKey)}
                      className={`min-h-20 rounded-xl border p-1.5 text-left transition md:min-h-24 md:p-2 ${
                        isSelected
                          ? 'border-blue-500 bg-blue-600 text-white shadow-sm'
                          : isWorking
                            ? 'border-blue-200 bg-blue-50 text-blue-900 hover:bg-blue-100'
                            : isDayOff
                              ? 'border-slate-200 bg-slate-100 text-slate-500'
                              : 'border-slate-100 bg-white text-slate-500 hover:bg-slate-50'
                      } ${!isCurrentMonth ? 'opacity-45' : ''}`}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className={`text-sm font-bold ${isToday && !isSelected ? 'text-blue-700' : ''}`}>
                          {day.getDate()}
                        </span>
                        {isWorking ? (
                          <span className={`h-2 w-2 rounded-full ${isSelected ? 'bg-white' : 'bg-blue-600'}`} />
                        ) : null}
                      </div>
                      <div className="mt-2 text-[11px] leading-snug md:mt-3 md:text-xs">
                        {isWorking ? (
                          <>
                            <p className="font-semibold md:hidden">Смена</p>
                            <p className="hidden font-semibold md:block">{schedule?.time_start || '—'} - {schedule?.time_end || '—'}</p>
                            <p className={isSelected ? 'text-blue-100' : 'text-blue-700'}>{schedule?.planned_up || 0} УП</p>
                          </>
                        ) : isDayOff ? (
                          <p>Выходной</p>
                        ) : (
                          <>
                            <p className="md:hidden">Нет</p>
                            <p className="hidden md:block">Нет смены</p>
                          </>
                        )}
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-sm font-bold text-slate-950">
                  {new Date(selectedScheduleDate).toLocaleDateString('ru-RU', {
                    day: '2-digit',
                    month: 'long',
                    year: 'numeric',
                    weekday: 'long',
                  })}
                </p>
                {selectedSchedule ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-sm">
                    <span className="rounded-lg bg-white px-3 py-2 font-semibold text-slate-700">
                      {selectedSchedule.is_day_off ? 'Выходной' : `${selectedSchedule.time_start || '—'} - ${selectedSchedule.time_end || '—'}`}
                    </span>
                    <span className="rounded-lg bg-white px-3 py-2 font-semibold text-slate-700">
                      План: {selectedSchedule.planned_up || 0} УП
                    </span>
                    {selectedSchedule.break_start && selectedSchedule.break_end ? (
                      <span className="rounded-lg bg-blue-50 px-3 py-2 font-semibold text-blue-700">
                        Перерыв: {selectedSchedule.break_start} - {selectedSchedule.break_end}
                      </span>
                    ) : null}
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-slate-500">На эту дату смена не запланирована</p>
                )}
              </div>
            </div>
          ) : null}

        </section>
      </main>
    </div>
  );
}
