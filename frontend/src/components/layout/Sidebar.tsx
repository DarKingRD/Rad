import React from 'react';
import { Activity, LayoutDashboard, CalendarDays, GitBranch, Users, BarChart2 } from 'lucide-react';

interface SidebarItemProps {
  icon: React.ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
  mobile?: boolean;
}

const SidebarItem: React.FC<SidebarItemProps> = ({ icon: Icon, label, active, onClick, mobile }) => {
  if (mobile) {
    return (
      <button
        onClick={onClick}
        className={`flex flex-col items-center justify-center flex-1 py-2 gap-0.5 transition-colors ${
          active ? 'text-blue-600' : 'text-slate-400 hover:text-slate-600'
        }`}
      >
        <Icon size={20} />
        <span className="text-[10px] font-medium leading-tight truncate max-w-[56px] text-center">{label}</span>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors text-left ${
        active
          ? 'bg-blue-50 text-blue-700 font-medium'
          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
      }`}
    >
      <Icon size={20} />
      <span>{label}</span>
    </button>
  );
};

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, setActiveTab }) => {
  const menuItems = [
    { id: 'dashboard', label: 'Главная', icon: LayoutDashboard },
    { id: 'planning', label: 'Смены', icon: CalendarDays },
    { id: 'distribution', label: 'Распределение', icon: GitBranch },
    { id: 'doctors', label: 'Врачи', icon: Users },
    { id: 'reports', label: 'Отчёты', icon: BarChart2 },
  ];

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden md:flex w-64 bg-white border-r border-slate-200 flex-col">
        <div className="p-6 border-b border-slate-100">
          <div className="flex items-center space-x-2 text-blue-600">
            <Activity size={28} />
            <span className="text-xl font-bold text-slate-900 tracking-tight">РадПлан</span>
          </div>
          <p className="text-xs text-slate-500 mt-1">Система планирования</p>
        </div>

        <nav className="flex-1 p-2 space-y-1">
          {menuItems.map((item) => (
            <SidebarItem
              key={item.id}
              icon={item.icon}
              label={item.label}
              active={activeTab === item.id}
              onClick={() => setActiveTab(item.id)}
            />
          ))}
        </nav>

        <div className="p-4 border-t border-slate-100">
          <div className="flex items-center space-x-3 p-2 rounded-lg bg-slate-50 border border-slate-100">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-xs">
              АД
            </div>
            <div className="overflow-hidden">
              <p className="text-sm font-medium text-slate-900 truncate">Администратор</p>
              <p className="text-xs text-slate-500 truncate">Зав. отделением</p>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-slate-200 flex items-stretch h-16 safe-area-pb">
        {menuItems.map((item) => (
          <SidebarItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            active={activeTab === item.id}
            onClick={() => setActiveTab(item.id)}
            mobile
          />
        ))}
      </nav>
    </>
  );
};