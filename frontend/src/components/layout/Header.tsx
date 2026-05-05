import React from 'react';
import { Bell, RefreshCw, Activity } from 'lucide-react';

interface HeaderProps {
  currentDate: string;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentDate, onRefresh }) => {
  return (
    <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-slate-200/80 bg-white/85 px-4 backdrop-blur md:h-16 md:px-6 xl:px-8">
      <div className="flex h-full items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex items-center gap-2 text-blue-600 md:hidden">
            <Activity size={22} />
            <span className="text-base font-bold tracking-tight text-slate-900">РадПлан</span>
          </div>

          <div className="hidden min-w-0 items-center text-sm text-slate-500 md:flex">
            <span>Сегодня:</span>
            <span className="ml-2 truncate font-medium text-slate-900">{currentDate}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 md:gap-3">
          <button
            className="relative rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
            aria-label="Уведомления"
          >
            <Bell size={20} />
            <span className="absolute right-2 top-2 h-2 w-2 rounded-full border border-white bg-rose-500" />
          </button>
          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700 md:px-4 md:text-sm"
          >
            <RefreshCw size={16} />
            <span className="hidden sm:inline">Обновить данные</span>
            <span className="sm:hidden">Обновить</span>
          </button>
        </div>
      </div>
    </header>
  );
};
