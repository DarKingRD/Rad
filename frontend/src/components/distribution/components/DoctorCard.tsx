import React from 'react';
import { ChevronDown, ChevronUp, Clock, Loader2, UserCheck } from 'lucide-react';
import type { DoctorDistStat, DoctorWithLoad, Study } from '../../../types';
import type { DoctorStudiesState } from '../hooks/useDoctorStudies';
import { getPriorityColor, getPriorityLabel, getStatusColor } from '../utils/distributionFormatters';

interface DoctorCardProps {
  doc: DoctorWithLoad;
  distStat?: DoctorDistStat;
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
  isSelectedForAssign,
  isExpanded,
  studiesState,
  hasSelectedStudy,
  onToggleExpand,
  onSelectForAssign,
}) => {
  const assignedCount = distStat?.assigned_studies ?? doc.active_studies ?? 0;
  const totalUp = distStat ? distStat.total_up : doc.current_load ?? 0;
  const maxUp = distStat ? distStat.max_up : doc.max_load ?? 50;
  const loadPct = maxUp > 0 ? Math.min((totalUp / maxUp) * 100, 100) : 0;
  const isOverloaded = loadPct > 80;

  const renderStudyRow = (study: Study) => (
    <div
      key={study.research_number}
      className="px-4 py-3 border-t border-slate-100 flex items-start justify-between gap-3"
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
          {study.status || '—'}
        </span>
      </div>
    </div>
  );

  return (
    <div
      className={`border rounded-lg transition-all ${
        isSelectedForAssign && hasSelectedStudy
          ? 'border-blue-500 ring-2 ring-blue-200'
          : 'border-slate-200'
      }`}
    >
      <div className="p-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-semibold text-sm shrink-0">
          {doc.fio_alias?.charAt(0) || 'В'}
        </div>

        <div className="flex-1 min-w-0">
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

        <div className="text-right shrink-0 min-w-[140px]">
          <div className="text-sm font-semibold text-slate-900">
            {typeof totalUp === 'number' ? totalUp.toFixed(2) : totalUp}
            <span className="text-slate-400 font-normal"> / {maxUp} УП</span>
          </div>

          <div className="w-32 h-2 bg-slate-100 rounded-full mt-1 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isOverloaded
                  ? 'bg-red-500'
                  : loadPct > 50
                  ? 'bg-amber-400'
                  : 'bg-green-500'
              }`}
              style={{ width: `${loadPct}%` }}
            />
          </div>

          <div className="text-xs mt-1 flex items-center justify-end gap-1">
            <UserCheck
              size={11}
              className={assignedCount > 0 ? 'text-green-500' : 'text-slate-300'}
            />
            <span
              className={
                assignedCount > 0
                  ? 'text-slate-700 font-medium'
                  : 'text-slate-400'
              }
            >
              {assignedCount} исслед.
            </span>
          </div>
        </div>

        <div className="flex flex-col gap-1 shrink-0">
          {hasSelectedStudy && (
            <button
              onClick={() => onSelectForAssign(doc.id)}
              className={`text-xs px-3 py-1.5 rounded border transition-all ${
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
            className="text-xs px-3 py-1.5 rounded border border-slate-300 text-slate-600 hover:bg-slate-50 transition-all inline-flex items-center justify-center gap-1"
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
        <div className="bg-slate-50 rounded-b-lg">
          {studiesState?.loading ? (
            <div className="px-4 py-6 flex items-center gap-2 text-sm text-slate-500">
              <Loader2 size={16} className="animate-spin" />
              Загрузка исследований...
            </div>
          ) : studiesState?.error ? (
            <div className="px-4 py-6 text-sm text-red-600">{studiesState.error}</div>
          ) : studiesState?.studies?.length ? (
            <div>{studiesState.studies.map(renderStudyRow)}</div>
          ) : (
            <div className="px-4 py-6 text-sm text-slate-500">
              У врача нет подтверждённых исследований
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default DoctorCard;