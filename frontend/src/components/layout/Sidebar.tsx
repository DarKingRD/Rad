import { Activity, LayoutDashboard, CalendarDays, GitBranch, Users, BarChart2, ChevronUp, UserCircle2 } from 'lucide-react';
import React, { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { ApiClientError, authApi } from '../../services/api';
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
  accountName: string;
  accountRole: string;
  onLogout: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  accountName,
  accountRole,
  onLogout,
}) => {
  const [isAccountMenuOpen, setIsAccountMenuOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [formMessage, setFormMessage] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const desktopMenuRef = useRef<HTMLDivElement | null>(null);
  const mobileMenuRef = useRef<HTMLDivElement | null>(null);

  const menuItems = [
    { id: 'dashboard', label: 'Главная', icon: LayoutDashboard },
    { id: 'planning', label: 'Смены', icon: CalendarDays },
    { id: 'distribution', label: 'Распределение', icon: GitBranch },
    { id: 'doctors', label: 'Врачи', icon: Users },
    { id: 'reports', label: 'Отчёты', icon: BarChart2 },
  ];

    const initials = useMemo(() => {
    const words = accountName.trim().split(/\s+/).filter(Boolean);
    if (!words.length) return 'РС';
    return words.slice(0, 2).map((w) => w[0]?.toUpperCase() || '').join('');
  }, [accountName]);

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target as Node;
      const isDesktopHit = desktopMenuRef.current?.contains(target);
      const isMobileHit = mobileMenuRef.current?.contains(target);
      if (!isDesktopHit && !isMobileHit) {
        setIsAccountMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

   const openProfileModal = async () => {
    setFormError(null);
    setFormMessage(null);
    setIsAccountMenuOpen(false);
    setIsProfileModalOpen(true);
    try {
      const profile = await authApi.getProfile();
      setFirstName(profile.first_name || '');
      setLastName(profile.last_name || '');
    } catch (error) {
      const message = error instanceof ApiClientError ? error.message : 'Не удалось загрузить профиль';
      setFormError(message);
    }
  };

  const openPasswordModal = () => {
    setFormError(null);
    setFormMessage(null);
    setOldPassword('');
    setNewPassword('');
    setIsAccountMenuOpen(false);
    setIsPasswordModalOpen(true);
  };

  const handleProfileSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setFormError(null);
    setFormMessage(null);
    try {
      await authApi.updateProfile({ first_name: firstName, last_name: lastName });
      setFormMessage('Профиль успешно обновлён.');
    } catch (error) {
      const message = error instanceof ApiClientError ? error.message : 'Не удалось сохранить профиль';
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setFormError(null);
    setFormMessage(null);
    try {
      await authApi.changePassword(oldPassword, newPassword);
      setFormMessage('Пароль успешно изменён.');
      setOldPassword('');
      setNewPassword('');
    } catch (error) {
      const message = error instanceof ApiClientError ? error.message : 'Не удалось сменить пароль';
      setFormError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
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

        <div className="p-4 border-t border-slate-100" ref={desktopMenuRef}>
          <button
            onClick={() => setIsAccountMenuOpen((prev) => !prev)}
            className="w-full flex items-center space-x-3 p-2 rounded-lg bg-slate-50 border border-slate-100 hover:border-slate-200"
            >
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-xs">
              {initials}
            </div>
            <div className="overflow-hidden flex-1 text-left">
              <p className="text-sm font-medium text-slate-900 truncate">{accountName}</p>
              <p className="text-xs text-slate-500 truncate">{accountRole}</p>
            </div>
            <ChevronUp size={16} className={`text-slate-400 transition-transform ${isAccountMenuOpen ? 'rotate-180' : ''}`} />
            </button>
            {isAccountMenuOpen ? (
            <div className="mt-2 rounded-lg border border-slate-200 bg-white shadow-sm py-1">
              <button onClick={openProfileModal} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Параметры пользователя</button>
              <button onClick={openPasswordModal} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Сменить пароль</button>
              <hr className="my-1 border-slate-100" />
              <button onClick={onLogout} className="w-full px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50">Выйти из аккаунта</button>
            </div>
          ) : null}
          </div>
        </div>

      <div className="md:hidden fixed right-3 bottom-20 z-50" ref={mobileMenuRef}>
        <button
          onClick={() => setIsAccountMenuOpen((prev) => !prev)}
          className="w-11 h-11 rounded-full bg-white border border-slate-200 shadow flex items-center justify-center text-blue-700"
          aria-label="Меню пользователя"
        >
          <UserCircle2 size={24} />
        </button>
        {isAccountMenuOpen ? (
          <div className="absolute right-0 bottom-14 w-64 rounded-lg border border-slate-200 bg-white shadow-lg py-2">
            <div className="px-3 pb-2 border-b border-slate-100">
              <p className="text-sm font-medium text-slate-900 truncate">{accountName}</p>
              <p className="text-xs text-slate-500 truncate">{accountRole}</p>
            </div>
            <button onClick={openProfileModal} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Параметры пользователя</button>
            <button onClick={openPasswordModal} className="w-full px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-50">Сменить пароль</button>
            <hr className="my-1 border-slate-100" />
            <button onClick={onLogout} className="w-full px-3 py-2 text-left text-sm text-rose-600 hover:bg-rose-50">Выйти из аккаунта</button>
          </div>
        ) : null}
      </div>

      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200 flex items-stretch h-16 safe-area-pb">
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

      {(isProfileModalOpen || isPasswordModalOpen) ? (
        <div className="fixed inset-0 z-[70] bg-slate-900/40 p-4 flex items-center justify-center">
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl p-5">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">
              {isProfileModalOpen ? 'Параметры профиля' : 'Сменить пароль'}
            </h3>

            {isProfileModalOpen ? (
              <form onSubmit={handleProfileSubmit} className="space-y-3">
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Имя</label>
                  <input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full border rounded-lg px-3 py-2" />
                </div>
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Фамилия</label>
                  <input value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full border rounded-lg px-3 py-2" />
                </div>
                <button disabled={isSubmitting} className="w-full rounded-lg bg-blue-600 text-white py-2.5 disabled:opacity-60">Сохранить</button>
              </form>
            ) : (
              <form onSubmit={handlePasswordSubmit} className="space-y-3">
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Старый пароль</label>
                  <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className="w-full border rounded-lg px-3 py-2" required />
                </div>
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Новый пароль</label>
                  <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="w-full border rounded-lg px-3 py-2" required />
                </div>
                <button disabled={isSubmitting} className="w-full rounded-lg bg-blue-600 text-white py-2.5 disabled:opacity-60">Изменить пароль</button>
              </form>
            )}

            {formError ? <p className="mt-3 text-sm text-rose-600">{formError}</p> : null}
            {formMessage ? <p className="mt-3 text-sm text-emerald-600">{formMessage}</p> : null}

            <button
              onClick={() => {
                setIsProfileModalOpen(false);
                setIsPasswordModalOpen(false);
                setFormError(null);
                setFormMessage(null);
              }}
              className="mt-4 w-full rounded-lg border border-slate-200 py-2 text-slate-700"
            >
              Закрыть
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
};