import React from 'react';
import { Bell } from 'lucide-react';

interface HeaderProps {
  currentDate: string;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentDate, onRefresh }) => {
  return (
    <header className="h-16 bg-white border-b border-slate-200 flex justify-between items-center px-8">
      <div className="flex items-center text-slate-500 text-sm">
        <span>Сегодня:</span>
        <span className="ml-2 font-medium text-slate-900">{currentDate}</span>
      </div>
      <div className="flex items-center space-x-4">
        <button className="relative p-2 text-slate-400 hover:text-slate-600">
          <Bell size={20} />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border border-white"></span>
        </button>
        <button 
          onClick={onRefresh}
          className="px-4 py-2 bg-blue-600 text-white rounded-md text-sm font-medium hover:bg-blue-700 shadow-sm"
        >
          Обновить данные
        </button>
      </div>
    </header>
  );
};