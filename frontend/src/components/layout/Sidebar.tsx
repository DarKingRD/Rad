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
        className={`relative flex flex-1 flex-col items-center justify-center gap-0.5 rounded-2xl py-2 transition ${
          active ? 'bg-blue-50 text-blue-700' : 'text-slate-400 hover:bg-slate-50 hover:text-slate-600'
        }`}
      >
        <Icon size={20} />
        <span className="max-w-[58px] truncate text-center text-[10px] font-semibold leading-tight">{label}</span>
      </button>
    );
  }

  return (
    <button
      onClick={onClick}
      className={`group flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition ${
        active
          ? 'bg-blue-600 text-white shadow-sm shadow-blue-600/20'
          : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
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
      <div className="hidden w-[264px] shrink-0 flex-col border-r border-slate-200/80 bg-white/90 backdrop-blur md:flex">
        <div className="border-b border-slate-100 px-6 py-5">
          <div className="flex items-center gap-2 text-blue-600">
            <Activity size={28} />
            <span className="text-xl font-bold text-slate-900 tracking-tight">РадПлан</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Рентгенологическая служба</p>
        </div>

        <nav className="flex-1 space-y-1.5 p-3">
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

        <div className="border-t border-slate-100 p-4" ref={desktopMenuRef}>
          <button
            onClick={() => setIsAccountMenuOpen((prev) => !prev)}
            className="flex w-full items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50/80 p-2.5 transition hover:border-slate-300 hover:bg-white"
            >
            <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-blue-100 text-xs font-bold text-blue-700">
              {initials}
            </div>
            <div className="overflow-hidden flex-1 text-left">
              <p className="text-sm font-medium text-slate-900 truncate">{accountName}</p>
              <p className="text-xs text-slate-500 truncate">{accountRole}</p>
            </div>
            <ChevronUp size={16} className={`text-slate-400 transition-transform ${isAccountMenuOpen ? 'rotate-180' : ''}`} />
            </button>
            {isAccountMenuOpen ? (
            <div className="mt-2 overflow-hidden rounded-2xl border border-slate-200 bg-white py-1 shadow-lg shadow-slate-200/70">
              <button onClick={openProfileModal} className="w-full px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50">Параметры пользователя</button>
              <button onClick={openPasswordModal} className="w-full px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50">Сменить пароль</button>
              <hr className="my-1 border-slate-100" />
              <button onClick={onLogout} className="w-full px-3 py-2.5 text-left text-sm text-amber-600 hover:bg-amber-50">Выйти из аккаунта</button>
            </div>
          ) : null}
          </div>
        </div>

      <div className="fixed bottom-20 right-3 z-50 md:hidden" ref={mobileMenuRef}>
        <button
          onClick={() => setIsAccountMenuOpen((prev) => !prev)}
          className="flex h-11 w-11 items-center justify-center rounded-2xl border border-slate-200 bg-white text-blue-700 shadow-lg shadow-slate-200/70"
          aria-label="Меню пользователя"
        >
          <UserCircle2 size={24} />
        </button>
        {isAccountMenuOpen ? (
          <div className="absolute bottom-14 right-0 w-64 overflow-hidden rounded-2xl border border-slate-200 bg-white py-2 shadow-2xl shadow-slate-300/50">
            <div className="px-3 pb-2 border-b border-slate-100">
              <p className="text-sm font-medium text-slate-900 truncate">{accountName}</p>
              <p className="text-xs text-slate-500 truncate">{accountRole}</p>
            </div>
            <button onClick={openProfileModal} className="w-full px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50">Параметры пользователя</button>
            <button onClick={openPasswordModal} className="w-full px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-50">Сменить пароль</button>
            <hr className="my-1 border-slate-100" />
            <button onClick={onLogout} className="w-full px-3 py-2.5 text-left text-sm text-amber-600 hover:bg-amber-50">Выйти из аккаунта</button>
          </div>
        ) : null}
      </div>

      <nav className="safe-area-pb fixed bottom-0 left-0 right-0 z-40 flex h-16 items-stretch gap-1 border-t border-slate-200 bg-white/95 px-2 py-1.5 shadow-[0_-12px_30px_rgba(15,23,42,0.08)] backdrop-blur md:hidden">
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
        <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-900/45 p-0 sm:items-center sm:p-4">
          <div className="w-full max-w-md rounded-t-3xl bg-white p-5 shadow-2xl sm:rounded-3xl">
            <h3 className="text-lg font-semibold text-slate-900 mb-4">
              {isProfileModalOpen ? 'Параметры профиля' : 'Сменить пароль'}
            </h3>

            {isProfileModalOpen ? (
              <form onSubmit={handleProfileSubmit} className="space-y-3">
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Имя</label>
                  <input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100" />
                </div>
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Фамилия</label>
                  <input value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100" />
                </div>
                <button disabled={isSubmitting} className="w-full rounded-xl bg-blue-600 py-2.5 font-semibold text-white disabled:opacity-60">Сохранить</button>
              </form>
            ) : (
              <form onSubmit={handlePasswordSubmit} className="space-y-3">
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Старый пароль</label>
                  <input type="password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100" required />
                </div>
                <div>
                  <label className="block text-sm text-slate-600 mb-1">Новый пароль</label>
                  <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100" required />
                </div>
                <button disabled={isSubmitting} className="w-full rounded-xl bg-blue-600 py-2.5 font-semibold text-white disabled:opacity-60">Изменить пароль</button>
              </form>
            )}

            {formError ? <p className="mt-3 text-sm text-amber-600">{formError}</p> : null}
            {formMessage ? <p className="mt-3 text-sm text-blue-600">{formMessage}</p> : null}

            <button
              onClick={() => {
                setIsProfileModalOpen(false);
                setIsPasswordModalOpen(false);
                setFormError(null);
                setFormMessage(null);
              }}
              className="mt-4 w-full rounded-xl border border-slate-200 py-2.5 font-medium text-slate-700 hover:bg-slate-50"
            >
              Закрыть
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
};