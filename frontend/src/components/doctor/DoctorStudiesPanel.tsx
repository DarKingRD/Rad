import { CheckCircle2, Clock3, XCircle } from 'lucide-react';
import type { Study } from '../../types';
import {
  getPriorityColor,
  getPriorityLabel,
  getStatusColor,
  getStatusLabel,
} from '../distribution/utils/distributionFormatters';
import { formatDateTime, statusTabs, StudyStatusFilter } from './doctorPortalUtils';

type DoctorStudiesPanelProps = {
  activeStatus: StudyStatusFilter;
  studies: Study[];
  isLoading: boolean;
  isUpdating: string | null;
  onStatusChange: (status: StudyStatusFilter) => void;
  onUpdateStatus: (study: Study, status: 'signed' | 'pending' | 'confirmed') => void;
};

export function DoctorStudiesPanel({
  activeStatus,
  studies,
  isLoading,
  isUpdating,
  onStatusChange,
  onUpdateStatus,
}: DoctorStudiesPanelProps) {
  return (
    <>
      <div className="border-b border-slate-100 px-4 py-3">
        <div className="inline-flex rounded-xl bg-slate-100 p-1">
          {statusTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => onStatusChange(tab.key)}
              className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${
                activeStatus === tab.key
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'text-slate-600 hover:text-slate-950'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="divide-y divide-slate-100">
        {isLoading ? (
          <div className="p-6 text-sm text-slate-500">Загрузка...</div>
        ) : studies.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">Нет исследований в этом статусе</div>
        ) : (
          studies.map((study) => (
            <div key={study.research_number} className="grid gap-3 p-4 md:grid-cols-[1fr_auto] md:items-center">
              <div className="min-w-0">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-950">{study.research_number}</span>
                  <span className={`rounded-lg border px-2 py-1 text-xs font-semibold ${getPriorityColor(study.priority)}`}>
                    {getPriorityLabel(study.priority)}
                  </span>
                  <span className={`rounded-lg px-2 py-1 text-xs font-semibold ${getStatusColor(study.status)}`}>
                    {getStatusLabel(study.status)}
                  </span>
                </div>
                <p className="truncate text-sm text-slate-600">{study.study_type?.name || 'Тип исследования не указан'}</p>
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <Clock3 size={14} />
                    {formatDateTime(study.created_at)}
                  </span>
                  <span>УП: {Number(study.study_type?.up_value || 0).toFixed(2)}</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 md:justify-end">
                {study.status !== 'signed' ? (
                  <button
                    type="button"
                    disabled={isUpdating === study.research_number}
                    onClick={() => onUpdateStatus(study, 'signed')}
                    className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
                  >
                    <CheckCircle2 size={17} />
                    Выполнено
                  </button>
                ) : null}
                {study.status === 'confirmed' ? (
                  <button
                    type="button"
                    disabled={isUpdating === study.research_number}
                    onClick={() => onUpdateStatus(study, 'pending')}
                    className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                  >
                    <XCircle size={17} />
                    Отказаться
                  </button>
                ) : null}
                {study.status !== 'confirmed' ? (
                  <button
                    type="button"
                    disabled={isUpdating === study.research_number}
                    onClick={() => onUpdateStatus(study, 'confirmed')}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                  >
                    Вернуть
                  </button>
                ) : null}
              </div>
            </div>
          ))
        )}
      </div>
    </>
  );
}
