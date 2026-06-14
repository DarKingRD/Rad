import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Bell, Folder, RefreshCw, UserRound } from 'lucide-react';
import { AdminNotification, notificationsApi } from '../../services/api';

interface HeaderProps {
  currentDate: string;
  onRefresh: () => void;
}

export const Header: React.FC<HeaderProps> = ({ currentDate, onRefresh }) => {
  const [notifications, setNotifications] = useState<AdminNotification[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeFolderKey, setActiveFolderKey] = useState<string | null>(null);

  const notificationFolders = useMemo(() => {
    const folders = new Map<string, { key: string; doctorName: string; items: AdminNotification[] }>();

    notifications.forEach((item) => {
      const doctorId = item.payload?.doctor_id;
      const doctorName =
        typeof item.payload?.doctor_name === 'string'
          ? item.payload.doctor_name
          : 'Врач';
      const key = doctorId === undefined || doctorId === null ? doctorName : String(doctorId);

      const folder = folders.get(key) || { key, doctorName, items: [] };
      folder.items.push(item);
      folders.set(key, folder);
    });

    return Array.from(folders.values());
  }, [notifications]);

  const activeFolder =
    notificationFolders.find((folder) => folder.key === activeFolderKey) ||
    notificationFolders[0] ||
    null;

  const loadNotifications = async () => {
    try {
      const data = await notificationsApi.getAll();
      setNotifications(data.notifications);
    } catch (error) {
      console.error('Не удалось загрузить уведомления', error);
    }
  };

  useEffect(() => {
    loadNotifications();
    const timer = window.setInterval(loadNotifications, 15000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (notificationFolders.length === 0) {
      setActiveFolderKey(null);
      return;
    }
    if (!activeFolderKey || !notificationFolders.some((folder) => folder.key === activeFolderKey)) {
      setActiveFolderKey(notificationFolders[0].key);
    }
  }, [activeFolderKey, notificationFolders]);

  const clearNotifications = async () => {
    try {
      const data = await notificationsApi.clear();
      setNotifications(data.notifications);
      setIsOpen(false);
    } catch (error) {
      console.error('Не удалось очистить уведомления', error);
    }
  };

  const formatNotificationTime = (value: string) =>
    new Date(value).toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    });

  const getNotificationClasses = (type: string) =>
    type === 'study_refused'
      ? 'border-l-4 border-l-amber-500 bg-amber-50/70'
      : 'border-l-4 border-l-blue-500 bg-blue-50/70';

  const getNotificationText = (type: string) =>
    type === 'study_refused'
      ? 'text-amber-800'
      : 'text-blue-800';

  return (
    <header className="sticky top-0 z-30 h-14 shrink-0 border-b border-slate-200 bg-white px-4 md:h-16 md:px-6 xl:px-8">
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
          <div className="relative">
            <button
              type="button"
              onClick={() => setIsOpen((value) => !value)}
              className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 transition hover:bg-slate-50"
              title="Уведомления"
            >
              <Bell size={18} />
              {notifications.length > 0 ? (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-amber-500 px-1 text-[11px] font-bold text-white">
                  {notifications.length > 9 ? '9+' : notifications.length}
                </span>
              ) : null}
            </button>

            {isOpen ? (
              <div className="fixed left-3 right-3 top-16 flex h-[min(620px,calc(100dvh-76px))] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-md md:left-auto md:right-6 md:top-16 md:w-[620px] xl:right-8">
                <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                  <div>
                    <p className="text-sm font-bold text-slate-950">Уведомления</p>
                    <p className="text-xs text-slate-500">
                      {notifications.length} событий · {notificationFolders.length} врачей
                    </p>
                  </div>
                  {notifications.length > 0 ? (
                    <button
                      type="button"
                      onClick={clearNotifications}
                      className="rounded-lg px-2 py-1 text-xs font-semibold text-blue-700 hover:bg-blue-50"
                    >
                      Очистить
                    </button>
                  ) : null}
                </div>
                <div className={`min-h-0 flex-1 overflow-hidden ${notifications.length > 0 ? 'grid md:grid-cols-[210px_1fr]' : 'block'}`}>
                  {notifications.length === 0 ? (
                    <div className="px-4 py-5 text-sm text-slate-500">Новых событий нет</div>
                  ) : (
                    <>
                      <div className="flex gap-2 overflow-x-auto border-b border-slate-100 bg-slate-50 p-3 md:block md:min-h-0 md:overflow-y-auto md:border-b-0 md:border-r">
                        {notificationFolders.map((folder) => {
                          const isActive = activeFolder?.key === folder.key;
                          return (
                            <button
                              key={folder.key}
                              type="button"
                              onClick={() => setActiveFolderKey(folder.key)}
                              className={`flex min-w-44 items-center gap-2 rounded-xl px-3 py-2 text-left transition md:mb-1 md:w-full md:min-w-0 ${
                                isActive
                                  ? 'bg-blue-600 text-white shadow-sm'
                                  : 'bg-white text-slate-700 hover:bg-slate-100 md:bg-transparent'
                              }`}
                            >
                              <Folder size={17} className={isActive ? 'text-white' : 'text-blue-600'} />
                              <span className="min-w-0 flex-1">
                                <span className="block truncate text-sm font-semibold">{folder.doctorName}</span>
                                <span className={`block text-xs ${isActive ? 'text-blue-100' : 'text-slate-500'}`}>
                                  {folder.items.length} событий
                                </span>
                              </span>
                            </button>
                          );
                        })}
                      </div>

                      <div className="min-h-0 overflow-y-auto">
                        <div className="sticky top-0 z-10 flex items-center gap-2 border-b border-slate-100 bg-white px-4 py-3">
                          <UserRound size={17} className="text-blue-600" />
                          <p className="truncate text-sm font-bold text-slate-950">
                            {activeFolder?.doctorName || 'Врач'}
                          </p>
                        </div>

                        {(activeFolder?.items || []).map((item) => (
                          <div
                            key={item.id}
                            className={`border-b border-slate-100 px-4 py-3 last:border-b-0 ${getNotificationClasses(item.type)}`}
                          >
                            <p className={`text-sm font-semibold leading-snug ${getNotificationText(item.type)}`}>
                              {item.message}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">{formatNotificationTime(item.created_at)}</p>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : null}
          </div>
          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-blue-700 md:px-4 md:text-sm"
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
