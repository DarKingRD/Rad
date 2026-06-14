import React from 'react';
import { Archive, Clock3, Trash2, X } from 'lucide-react';
import type { DistributionDraft } from '../../../types';

interface DraftsModalProps {
  isOpen: boolean;
  drafts: DistributionDraft[];
  onClose: () => void;
  onOpenDraft: (draft: DistributionDraft) => void;
  onRemoveDraft: (distributionId: string) => void;
}

const DraftsModal: React.FC<DraftsModalProps> = ({
  isOpen,
  drafts,
  onClose,
  onOpenDraft,
  onRemoveDraft,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center bg-slate-950/50 p-0 md:items-center md:p-4">
      <div className="flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-2xl bg-white shadow-lg md:max-w-3xl md:rounded-xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4 md:px-6">
          <div className="flex items-center gap-2">
            <Archive size={20} className="text-slate-600" />
            <div>
              <h3 className="text-lg font-bold text-slate-900">Черновики распределений</h3>
              <p className="text-sm text-slate-500">Сохранённые предварительные расчёты</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 md:p-6">
          {drafts.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 py-12 text-center text-sm text-slate-500">
              Черновиков пока нет
            </div>
          ) : (
            <div className="space-y-3">
              {drafts.map((draft) => (
                <div
                  key={draft.distribution_id}
                  className="rounded-xl border border-slate-200 bg-white p-4 transition hover:border-slate-300"
                >
                  <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                    <div className="min-w-0">
                      <div className="font-medium text-slate-900">
                        Распределение на {draft._savedDate || draft.target_date || '—'}
                      </div>

                      <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3 text-sm md:grid-cols-4">
                        <div>
                          <div className="text-slate-400">Назначено</div>
                          <div className="font-medium text-slate-800">
                            {draft.assigned ?? draft.assignments?.filter((a) => a.doctor_id).length ?? 0}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">Неназначено</div>
                          <div className="font-medium text-slate-800">
                            {draft.unassigned ?? draft.assignments?.filter((a) => !a.doctor_id).length ?? 0}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">Врачей</div>
                          <div className="font-medium text-slate-800">
                            {draft.doctor_stats?.length ?? 0}
                          </div>
                        </div>
                        <div>
                          <div className="text-slate-400">Сохранено</div>
                          <div className="font-medium text-slate-800 inline-flex items-center gap-1">
                            <Clock3 size={14} />
                            {draft._savedAt
                              ? new Date(draft._savedAt).toLocaleString('ru-RU')
                              : '—'}
                          </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-1 gap-2 shrink-0 sm:grid-cols-2 md:flex md:items-center">
                      <button
                        onClick={() => onOpenDraft(draft)}
                        className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-3 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700"
                      >
                        Открыть
                      </button>

                      <button
                        onClick={() => onRemoveDraft(draft.distribution_id)}
                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                      >
                        <Trash2 size={14} />
                        Удалить
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DraftsModal;
