export type StudyStatusFilter = 'confirmed' | 'signed';
export type DoctorPortalTab = 'studies' | 'schedules';

export const statusTabs: Array<{ key: StudyStatusFilter; label: string }> = [
  { key: 'confirmed', label: 'Назначено' },
  { key: 'signed', label: 'Выполнено' },
];

export function monthStartString(date = new Date()) {
  return new Date(date.getFullYear(), date.getMonth(), 1).toISOString().split('T')[0];
}

export function todayString(date = new Date()) {
  return date.toISOString().split('T')[0];
}

export function localDateString(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function getMonthBounds(date: Date) {
  const start = new Date(date.getFullYear(), date.getMonth(), 1);
  const end = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  return {
    date_from: localDateString(start),
    date_to: localDateString(end),
  };
}

export function getCalendarDays(date: Date) {
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

export function formatDateTime(value?: string | null) {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}
