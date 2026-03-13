export const getPriorityColor = (priority: string) => {
  if (priority === 'cito') return 'bg-red-100 text-red-700 border-red-200';
  if (priority === 'asap') return 'bg-amber-100 text-amber-700 border-amber-200';
  return 'bg-slate-100 text-slate-600 border-slate-200';
};

export const getPriorityLabel = (priority: string) => {
  if (priority === 'cito') return 'CITO';
  if (priority === 'asap') return 'ASAP';
  return 'План';
};

export const getStatusColor = (status: string) => {
  if (status === 'confirmed' || status === 'Подтверждено') {
    return 'bg-green-100 text-green-700';
  }
  if (status === 'signed' || status === 'Подписано') {
    return 'bg-blue-100 text-blue-700';
  }
  return 'bg-slate-100 text-slate-600';
};

export const formatDate = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
      })
    : '—';

export const formatTime = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

export const getTodayString = () => new Date().toISOString().split('T')[0];