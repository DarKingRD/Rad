import React from 'react';
import { ChevronDown, ChevronUp, Clock, Loader2, UserCheck } from 'lucide-react';
import type { DoctorDistStat, DoctorWithLoad, Study } from '../../../types';
import type { DoctorStudiesState } from '../hooks/useDoctorStudies';
import { getPriorityColor, getPriorityLabel, getStatusColor, getStatusLabel } from '../utils/distributionFormatters';

interface DoctorCardProps {
  doc: DoctorWithLoad;
  distStat?: DoctorDistStat;
  completedUp: number;
  loadMonthLabel: string;
  isSelectedForAssign: boolean;
  isExpanded: boolean;
  studiesState?: DoctorStudiesState;
  hasSelectedStudy: boolean;
  onToggleExpand: (id: number) => void;
  onSelectForAssign: (id: number) => void;
}

const DoctorCard: React.FC<DoctorCardProps> = ({
  doc,
  distStat,
  completedUp,
  loadMonthLabel,
  isSelectedForAssign,
  isExpanded,
  studiesState,
  hasSelectedStudy,
  onToggleExpand,
  onSelectForAssign,
}) => {
  const previewAssignedCount = distStat?.assigned_studies ?? 0;
  const assignedCount = doc.active_studies ?? 0;
  const totalUp = completedUp;
  const maxUp = doc.max_load ?? 50;
  const loadPct = maxUp > 0 ? Math.min((totalUp / maxUp) * 100, 100) : 0;
  const isOverloaded = loadPct > 80;
  const assignedStudies = studiesState?.assignedStudies ?? [];
  const completedStudies = studiesState?.completedStudies ?? [];
  const hasDoctorStudies = assignedStudies.length > 0 || completedStudies.length > 0;

  const formatUp = (value?: number | null) => {
    const numericValue = Number(value || 0);
    return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(numericValue);
  };

  const renderStudyRow = (study: Study) => (
    <div
      key={study.research_number}
      className="flex items-start justify-between gap-3 border-t border-slate-100 px-4 py-3"
    >
      <div className="min-w-0">
        <div className="font-medium text-sm text-slate-800 truncate">
          {study.research_number}
        </div>
        <div className="text-xs text-slate-500 truncate">
          {study.study_type?.name || 'Тип не указан'}
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${getPriorityColor(
            study.priority
          )}`}
        >
          {getPriorityLabel(study.priority)}
        </span>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium ${getStatusColor(
            study.status
          )}`}
        >
          {getStatusLabel(study.status) || '—'}
        </span>
      </div>
    </div>
  );

  return (
    <div
      className={`overflow-hidden rounded-xl border bg-white transition-all ${
        isSelectedForAssign && hasSelectedStudy
          ? 'border-blue-500 ring-2 ring-blue-100 shadow-sm'
          : 'border-slate-200 shadow-sm'
      }`}
    >
      <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-sm font-semibold text-white shadow-sm">
          {doc.fio_alias?.charAt(0) || 'В'}
        </div>

        <div className="min-w-0 flex-1">
          <div className="font-medium text-slate-900 truncate">
            {doc.fio_alias || `Врач ${doc.id}`}
          </div>
          <div className="text-xs text-slate-500">{doc.specialty || doc.position_type}</div>

          {doc.today_shift_start && (
            <div className="text-[10px] text-slate-500 mt-0.5 flex items-center gap-1 flex-wrap">
              <Clock size={10} className="shrink-0" />
              <span>
                {doc.today_shift_start}–{doc.today_shift_end}
              </span>
              {doc.today_break_start && (
                <span className="text-amber-600">
                  · ☕ {doc.today_break_start}–{doc.today_break_end}
                  {doc.today_break_minutes > 0 && ` (${doc.today_break_minutes}м)`}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="w-full shrink-0 text-left sm:w-auto sm:min-w-[150px] sm:text-right">
          <div className="text-xs font-semibold text-blue-700">
            Факт за {loadMonthLabel}: {formatUp(typeof totalUp === 'number' ? totalUp : Number(totalUp))}
            <span className="font-normal text-slate-400"> / {maxUp} УП</span>
          </div>

          <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-100 sm:w-32">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isOverloaded
                  ? 'bg-amber-500'
                  : loadPct > 50
                  ? 'bg-amber-400'
                  : 'bg-blue-500'
              }`}
              style={{ width: `${loadPct}%` }}
            />
          </div>

          <div className="mt-1 flex items-center gap-1 text-xs sm:justify-end">
            <UserCheck
              size={11}
              className={assignedCount > 0 ? 'text-blue-500' : 'text-slate-300'}
            />
            <span
              className={
                assignedCount > 0
                  ? 'text-slate-700 font-medium'
                  : 'text-slate-400'
              }
            >
              {assignedCount} назначенных исслед.
              {previewAssignedCount > 0 ? ` · +${previewAssignedCount} в расчёте` : ''}
            </span>
          </div>
        </div>

        <div className="grid w-full shrink-0 grid-cols-2 gap-2 sm:w-auto sm:grid-cols-1">
          {hasSelectedStudy && (
            <button
              onClick={() => onSelectForAssign(doc.id)}
              className={`rounded-xl border px-3 py-2 text-xs font-semibold transition ${
                isSelectedForAssign
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'border-slate-300 text-slate-600 hover:bg-blue-50 hover:border-blue-400'
              }`}
            >
              {isSelectedForAssign ? '✓ Выбран' : 'Назначить'}
            </button>
          )}

          <button
            onClick={() => onToggleExpand(doc.id)}
            className="inline-flex items-center justify-center gap-1 rounded-xl border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
          >
            {isExpanded ? (
              <>
                <ChevronUp size={14} />
                Свернуть
              </>
            ) : (
              <>
                <ChevronDown size={14} />
                Исследования
              </>
            )}
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="rounded-b-xl bg-slate-50/90">
          {studiesState?.loading ? (
            <div className="px-4 py-6 flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" />
              Загрузка исследований...
            </div>
          ) : studiesState?.error ? (
            <div className="px-4 py-6 text-sm text-amber-600">{studiesState.error}</div>
          ) : hasDoctorStudies ? (
            <div>
              <div className="border-t border-slate-100 px-4 py-2 text-xs font-semibold text-slate-500">
                Назначенные исследования за текущий месяц
              </div>
              {assignedStudies.length ? (
                assignedStudies.map(renderStudyRow)
              ) : (
                <div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
                  Нет назначенных исследований
                </div>
              )}

              <div className="border-t border-slate-200 px-4 py-2 text-xs font-semibold text-slate-500">
                Выполненные исследования за текущий месяц
              </div>
              {completedStudies.length ? (
                completedStudies.map(renderStudyRow)
              ) : (
                <div className="border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
                  Нет выполненных исследований
                </div>
              )}
            </div>
          ) : (
            <div className="px-4 py-6 text-sm text-slate-500">
              У врача нет назначенных и выполненных исследований за текущий месяц
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DoctorCard;
