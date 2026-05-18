import { Stethoscope } from 'lucide-react';

type DoctorSettingsPanelProps = {
  availableModalities: string[];
  selectedModalities: string[];
  isSaving: boolean;
  onToggleModality: (modality: string) => void;
  onSave: () => void;
};

export function DoctorSettingsPanel({
  availableModalities,
  selectedModalities,
  isSaving,
  onToggleModality,
  onSave,
}: DoctorSettingsPanelProps) {
  return (
    <section className="mb-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-950">Настройки</h2>
          <p className="text-sm text-slate-500">Специализации врача</p>
        </div>
        <button
          type="button"
          onClick={onSave}
          disabled={isSaving}
          className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 disabled:opacity-60"
        >
          {isSaving ? 'Сохраняем...' : 'Сохранить'}
        </button>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {availableModalities.map((modality) => {
          const checked = selectedModalities.includes(modality);
          return (
            <label
              key={modality}
              className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-3 text-sm font-semibold transition ${
                checked
                  ? 'border-blue-200 bg-blue-50 text-blue-800'
                  : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50'
              }`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => onToggleModality(modality)}
                className="h-4 w-4 accent-blue-600"
              />
              <Stethoscope size={17} className={checked ? 'text-blue-600' : 'text-slate-400'} />
              <span>{modality}</span>
            </label>
          );
        })}
      </div>
    </section>
  );
}
