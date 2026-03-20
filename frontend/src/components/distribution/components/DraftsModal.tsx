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
    <div className="fixed inset-0 z-[70] bg-black/50 flex items-end md:items-center justify-center p-0 md:p-4">
      <div className="bg-white w-full md:max-w-3xl md:rounded-2xl shadow-2xl max-h-[90vh] overflow-hidden rounded-t-2xl md:rounded-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 md:px-6 py-4">
          <div className="flex items-center gap-2">
            <Archive size={20} className="text-slate-600" />
            <div>
              <h3 className="text-lg font-bold text-slate-900">Черновики распределений</h3>
              <p className="text-sm text-slate-500">Сохранённые preview-результаты</p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </div>

        <div className="p-4 md:p-6 overflow-y-auto max-h-[calc(90vh-88px)]">
          {drafts.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              Черновиков пока нет
            </div>
          ) : (
            <div className="space-y-3">
              {drafts.map((draft) => (
                <div
                  key={draft.distribution_id}
                  className="border border-slate-200 rounded-xl p-4 hover:shadow-sm transition"
                >
                  <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                    <div className="min-w-0">
                      <div className="font-medium text-slate-900">
                        Распределение на {draft._savedDate || draft.target_date || '—'}
                      </div>

                      <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
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

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => onOpenDraft(draft)}
                        className="px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700"
                      >
                        Открыть
                      </button>

                      <button
                        onClick={() => onRemoveDraft(draft.distribution_id)}
                        className="px-3 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm hover:bg-slate-50 inline-flex items-center gap-2"
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