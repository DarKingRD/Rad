import { useEffect, useMemo, useState } from 'react';
import { LogOut, RotateCcw, Settings } from 'lucide-react';
import { ApiClientError, authApi, doctorPortalApi } from '../../services/api';
import type { DoctorPortalProfile, Schedule, Study } from '../../types';
import { DoctorScheduleCalendar } from './DoctorScheduleCalendar';
import { DoctorSettingsPanel } from './DoctorSettingsPanel';
import { DoctorStatsCard } from './DoctorStatsCard';
import { DoctorStudiesPanel } from './DoctorStudiesPanel';
import {
  getMonthBounds,
  localDateString,
  monthStartString,
  todayString,
} from './doctorPortalUtils';
import type { DoctorPortalTab, StudyStatusFilter } from './doctorPortalUtils';

type DoctorPortalViewProps = {
  onLogout: () => void;
};

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

  const selectedSchedule = schedulesByDate.get(selectedScheduleDate) || null;

  const changeCalendarMonth = (delta: number) => {
    setCalendarMonth((current) => {
      const next = new Date(current.getFullYear(), current.getMonth() + delta, 1);
      setSelectedScheduleDate(localDateString(next));
      return next;
    });
  };

  const goToCurrentMonth = () => {
    const now = new Date();
    setCalendarMonth(now);
    setSelectedScheduleDate(localDateString(now));
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
          <DoctorSettingsPanel
            availableModalities={profile?.available_modalities || []}
            selectedModalities={selectedModalities}
            isSaving={isSavingModalities}
            onToggleModality={toggleModality}
            onSave={saveModalities}
          />
        ) : null}

        {error ? (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {error}
          </div>
        ) : null}

        <section className="grid gap-4">
          <DoctorStatsCard title="Текущий месяц" stats={profile?.stats.current_month || { assigned: 0, completed: 0, pending: 0, completed_up: 0 }} />
        </section>

        <section className="mt-5 rounded-xl border border-slate-200 bg-white shadow-sm">
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
            <DoctorStudiesPanel
              activeStatus={activeStatus}
              studies={studies}
              isLoading={isLoading}
              isUpdating={isUpdating}
              onStatusChange={setActiveStatus}
              onUpdateStatus={updateStatus}
            />
          ) : null}

          {activeTab === 'schedules' ? (
            <DoctorScheduleCalendar
              calendarMonth={calendarMonth}
              selectedDate={selectedScheduleDate}
              schedulesByDate={schedulesByDate}
              selectedSchedule={selectedSchedule}
              onMonthChange={changeCalendarMonth}
              onToday={goToCurrentMonth}
              onSelectDate={setSelectedScheduleDate}
            />
          ) : null}

        </section>
      </main>
    </div>
  );
}
