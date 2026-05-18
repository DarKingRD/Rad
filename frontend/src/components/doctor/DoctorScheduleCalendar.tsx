import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import type { Schedule } from '../../types';
import { getCalendarDays, localDateString } from './doctorPortalUtils';

type DoctorScheduleCalendarProps = {
  calendarMonth: Date;
  selectedDate: string;
  schedulesByDate: Map<string, Schedule>;
  selectedSchedule: Schedule | null;
  onMonthChange: (delta: number) => void;
  onToday: () => void;
  onSelectDate: (date: string) => void;
};

export function DoctorScheduleCalendar({
  calendarMonth,
  selectedDate,
  schedulesByDate,
  selectedSchedule,
  onMonthChange,
  onToday,
  onSelectDate,
}: DoctorScheduleCalendarProps) {
  const currentMonthLabel = calendarMonth.toLocaleDateString('ru-RU', {
    month: 'long',
    year: 'numeric',
  });
  const calendarDays = getCalendarDays(calendarMonth);

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <CalendarDays size={20} className="text-blue-600" />
          <h3 className="text-base font-bold capitalize text-slate-950">{currentMonthLabel}</h3>
        </div>
        <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1">
          <button
            type="button"
            onClick={() => onMonthChange(-1)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100"
            title="Предыдущий месяц"
          >
            <ChevronLeft size={18} />
          </button>
          <button
            type="button"
            onClick={onToday}
            className="rounded-lg px-3 text-sm font-semibold text-slate-700 hover:bg-slate-100"
          >
            Сегодня
          </button>
          <button
            type="button"
            onClick={() => onMonthChange(1)}
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
          const isSelected = dateKey === selectedDate;
          const isToday = dateKey === localDateString(new Date());
          const isWorking = Boolean(schedule && !schedule.is_day_off);
          const isDayOff = Boolean(schedule && schedule.is_day_off);

          return (
            <button
              key={dateKey}
              type="button"
              onClick={() => onSelectDate(dateKey)}
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
          {new Date(selectedDate).toLocaleDateString('ru-RU', {
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
  );
}
