import React from 'react';
import { Bell, Activity } from 'lucide-react';

interface HeaderProps {
  currentDate: string;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentDate, onRefresh }) => {
  return (
    <header className="h-14 md:h-16 bg-white border-b border-slate-200 flex justify-between items-center px-4 md:px-8 shrink-0 relative">
      {/* Mobile: логотип слева */}
      <div className="flex items-center gap-2 md:hidden text-blue-600">
        <Activity size={22} />
        <span className="font-bold text-slate-900 text-base tracking-tight">РадПлан</span>
      </div>

      {/* Desktop: дата слева */}
      <div className="hidden md:flex items-center text-slate-500 text-sm">
        <span>Сегодня:</span>
        <span className="ml-2 font-medium text-slate-900">{currentDate}</span>
      </div>

      {/* Mobile: дата по центру */}
      <div className="md:hidden absolute left-1/2 -translate-x-1/2 text-xs text-slate-500 pointer-events-none">
        <span className="font-medium text-slate-700">{currentDate}</span>
      </div>

      <div className="flex items-center space-x-2 md:space-x-4">
        <button className="relative p-2 text-slate-400 hover:text-slate-600">
          <Bell size={20} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border border-white"></span>
        </button>
        <button
          onClick={onRefresh}
          className="px-3 md:px-4 py-1.5 md:py-2 bg-blue-600 text-white rounded-md text-xs md:text-sm font-medium hover:bg-blue-700 shadow-sm"
        >
          <span className="hidden md:inline">Обновить данные</span>
          <span className="md:hidden">Обновить</span>
        </button>
      </div>
    </header>
  );
};