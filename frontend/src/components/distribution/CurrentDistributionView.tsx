import React, { useState, useEffect, useMemo } from 'react';
import { studiesApi, doctorsApi } from '../../services/api';
import { UserCheck, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { Study, DoctorWithLoad } from '../../types';

// ─── Вспомогательные утилиты ────────────────────────────────────────────────

const PRIORITY_ORDER: Record<string, number> = { cito: 1, asap: 2, normal: 3 };

const getPriorityColor = (priority: string) => {
  if (priority === 'cito') return 'bg-red-100 text-red-700';
  if (priority === 'asap') return 'bg-amber-100 text-amber-700';
  return 'bg-slate-100 text-slate-600';
};

const getPriorityLabel = (priority: string) => {
  if (priority === 'cito') return 'CITO';
  if (priority === 'asap') return 'ASAP';
  return 'План';
};

const getStatusColor = (status: string) => {
  if (status === 'confirmed' || status === 'Подтверждено') return 'bg-green-100 text-green-700';
  if (status === 'signed'    || status === 'Подписано')    return 'bg-blue-100 text-blue-700';
  return 'bg-slate-100 text-slate-600';
};

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

// ─── Тип для исследований врача ─────────────────────────────────────────────

interface DoctorStudiesState {
  loading: boolean;
  studies: Study[];
  error: string | null;
}

// ─── Компонент карточки врача ────────────────────────────────────────────────

interface DoctorCardProps {
  doc: DoctorWithLoad;
  isSelectedForAssign: boolean;
  isExpanded: boolean;
  studiesState: DoctorStudiesState;
  hasSelectedStudy: boolean;
  onToggleExpand: (id: number) => void;
  onSelectForAssign: (id: number) => void;
}

const DoctorCard: React.FC<DoctorCardProps> = ({
  doc,
  isSelectedForAssign,
  isExpanded,
  studiesState,
  hasSelectedStudy,
  onToggleExpand,
  onSelectForAssign,
}) => {
  const loadPct = doc.max_load > 0 ? Math.min((doc.current_load / doc.max_load) * 100, 100) : 0;
  const isOverloaded = loadPct > 80;

  return (
    <div
      className={`border rounded-lg transition-all ${
        isSelectedForAssign && hasSelectedStudy
          ? 'border-blue-500 ring-2 ring-blue-200'
          : 'border-slate-200'
      }`}
    >
      {/* Основная строка врача */}
      <div className="flex items-center justify-between p-3 gap-3">
        {/* Аватар + имя */}
        <div className="flex items-center space-x-3 min-w-0 flex-1">
          <div className="w-10 h-10 shrink-0 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold">
            {doc.fio_alias.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="font-medium text-slate-900 truncate">{doc.fio_alias}</div>
            <div className="text-xs text-slate-500">{doc.specialty}</div>
          </div>
        </div>

        {/* Нагрузка */}
        <div className="text-right shrink-0">
          <div className="text-sm font-medium text-slate-900">
            {doc.current_load} / {doc.max_load} УП
          </div>
          <div className="w-24 h-2 bg-slate-100 rounded-full mt-1 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${isOverloaded ? 'bg-red-500' : 'bg-green-500'}`}
              style={{ width: `${loadPct}%` }}
            />
          </div>
          <div className="text-xs text-green-600 mt-1 flex items-center justify-end">
            <UserCheck size={12} className="mr-1" />
            {doc.active_studies} исследований
          </div>
        </div>

        {/* Кнопки */}
        <div className="flex flex-col gap-1 shrink-0">
          {/* Кнопка «выбрать для назначения» — видна только если выбрано исследование */}
          {hasSelectedStudy && (
            <button
              onClick={() => onSelectForAssign(doc.id)}
              className={`text-xs px-2 py-1 rounded border transition-all ${
                isSelectedForAssign
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'border-slate-300 text-slate-600 hover:bg-blue-50 hover:border-blue-400'
              }`}
            >
              {isSelectedForAssign ? '✓ Выбран' : 'Назначить'}
            </button>
          )}

          {/* Кнопка раскрытия списка снимков */}
          <button
            onClick={() => onToggleExpand(doc.id)}
            className="text-xs px-2 py-1 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 flex items-center gap-1"
          >
            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            Снимки
          </button>
        </div>
      </div>

      {/* Раскрывающийся список исследований врача */}
      {isExpanded && (
        <div className="border-t border-slate-100 bg-slate-50 rounded-b-lg">
          {studiesState.loading ? (
            <div className="flex items-center justify-center py-4 gap-2 text-slate-400 text-sm">
              <Loader2 size={14} className="animate-spin" />
              Загрузка...
            </div>
          ) : studiesState.error ? (
            <div className="py-3 px-4 text-sm text-red-500">{studiesState.error}</div>
          ) : studiesState.studies.length === 0 ? (
            <div className="py-3 px-4 text-sm text-slate-400">Нет назначенных исследований</div>
          ) : (
            <div className="p-2 space-y-1 max-h-64 overflow-y-auto">
              {studiesState.studies.map((study) => (
                <div
                  key={study.id}
                  className="bg-white rounded-md border border-slate-200 px-3 py-2 flex items-center justify-between gap-2"
                >
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-slate-800 truncate">
                      {study.research_number}
                    </div>
                    <div className="text-xs text-slate-500 truncate flex items-center gap-1 flex-wrap">
                      <span>{study.study_type?.name || `Тип ${study.study_type_id}`}</span>
                      {study.study_type?.modality && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                          {study.study_type.modality}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400">
                      {formatDate(study.created_at)} {formatTime(study.created_at)}
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${getPriorityColor(study.priority)}`}>
                      {getPriorityLabel(study.priority)}
                    </span>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${getStatusColor(study.status)}`}>
                      {study.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ─── Главный компонент ───────────────────────────────────────────────────────

export const CurrentDistributionView: React.FC = () => {
  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);
  const [allStudies, setAllStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(20);

  // expandedDoctor — какой врач раскрыт; doctorStudies — кэш загруженных снимков
  const [expandedDoctor, setExpandedDoctor] = useState<number | null>(null);
  const [doctorStudies, setDoctorStudies] = useState<Record<number, DoctorStudiesState>>({});

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [studiesRes, doctorsRes] = await Promise.all([
        studiesApi.getPending(),
        doctorsApi.getWithLoad(),
      ]);
      setAllStudies(studiesRes.data || []);
      setDoctors(doctorsRes.data);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Загрузка исследований для конкретного врача
  const loadDoctorStudies = async (doctorId: number) => {
    // Уже загружено — не дёргаем снова
    if (doctorStudies[doctorId] && !doctorStudies[doctorId].error) return;

    setDoctorStudies(prev => ({
      ...prev,
      [doctorId]: { loading: true, studies: [], error: null },
    }));

    try {
      const res = await studiesApi.getList({ diagnostician_id: doctorId, status: 'confirmed' });
      setDoctorStudies(prev => ({
        ...prev,
        [doctorId]: { loading: false, studies: res.data || [], error: null },
      }));
    } catch (err) {
      setDoctorStudies(prev => ({
        ...prev,
        [doctorId]: { loading: false, studies: [], error: 'Ошибка загрузки' },
      }));
    }
  };

  const handleToggleExpand = (doctorId: number) => {
    if (expandedDoctor === doctorId) {
      setExpandedDoctor(null);
    } else {
      setExpandedDoctor(doctorId);
      loadDoctorStudies(doctorId);
    }
  };

  const handleSelectForAssign = (doctorId: number) => {
    setSelectedDoctor(prev => prev === doctorId ? null : doctorId);
  };

  // Сортировка очереди: CITO → ASAP → План, внутри — по дате создания (старые первыми)
  const sortedStudies = useMemo(() => {
    return [...allStudies].sort((a, b) => {
      const diff = (PRIORITY_ORDER[a.priority] || 3) - (PRIORITY_ORDER[b.priority] || 3);
      if (diff !== 0) return diff;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });
  }, [allStudies]);

  const totalPages = Math.ceil(sortedStudies.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedStudies = sortedStudies.slice(startIndex, startIndex + itemsPerPage);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setSelectedStudy(null);
    setSelectedDoctor(null);
  };

  const handleAssign = async (doctorId?: number) => {
    if (!selectedStudy) return;
    const targetId = doctorId ?? selectedDoctor;
    if (!targetId) { alert('Выберите врача'); return; }

    try {
      await studiesApi.assign(selectedStudy.id, targetId);
      // Инвалидируем кэш назначенных снимков для этого врача
      setDoctorStudies(prev => {
        const next = { ...prev };
        delete next[targetId];
        return next;
      });
      await loadData();
      setSelectedStudy(null);
      setSelectedDoctor(null);
    } catch {
      alert('Ошибка при назначении');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-slate-400 mr-2" size={20} />
        <span className="text-slate-500">Загрузка...</span>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-140px)] flex space-x-6">

      {/* ── Очередь исследований ───────────────────────────────────────────── */}
      <div className="w-1/2 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col">
        <div className="p-4 border-b border-slate-200">
          <h3 className="font-semibold text-slate-800">
            Очередь исследований ({sortedStudies.length})
          </h3>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {paginatedStudies.length === 0 ? (
            <div className="p-8 text-center text-slate-500">Нет исследований в очереди</div>
          ) : (
            paginatedStudies.map((study) => (
              <div
                key={study.id}
                onClick={() => {
                  setSelectedStudy(study);
                  setSelectedDoctor(null);
                }}
                className={`p-4 rounded-lg border cursor-pointer transition-all ${
                  selectedStudy?.id === study.id
                    ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                    : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="font-medium text-slate-900">{study.research_number}</span>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(study.priority)}`}>
                    {getPriorityLabel(study.priority)}
                  </span>
                </div>
                <div className="text-sm text-slate-600 mb-2 flex items-center gap-2 flex-wrap">
                  <span>{study.study_type?.name || `ID: ${study.study_type_id}`}</span>
                  {study.study_type?.modality && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                      {study.study_type.modality}
                    </span>
                  )}
                </div>
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Создано: {formatDate(study.created_at)}</span>
                  <span className={`px-2 py-0.5 rounded ${getStatusColor(study.status)}`}>
                    {study.status}
                  </span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Пагинация */}
        {totalPages > 1 && (
          <div className="p-4 border-t border-slate-200 flex items-center justify-between">
            <div className="text-sm text-slate-600">
              {startIndex + 1}–{Math.min(startIndex + itemsPerPage, sortedStudies.length)} из {sortedStudies.length}
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-2 rounded-md border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronLeft size={16} />
              </button>
              {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                let p: number;
                if (totalPages <= 5) p = i + 1;
                else if (currentPage <= 3) p = i + 1;
                else if (currentPage >= totalPages - 2) p = totalPages - 4 + i;
                else p = currentPage - 2 + i;
                return (
                  <button
                    key={p}
                    onClick={() => handlePageChange(p)}
                    className={`px-3 py-1 rounded-md text-sm ${
                      currentPage === p
                        ? 'bg-blue-600 text-white'
                        : 'border border-slate-300 text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                className="p-2 rounded-md border border-slate-300 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Правая колонка: врачи + панель назначения ─────────────────────── */}
      <div className="w-1/2 flex flex-col space-y-4">

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex-1 overflow-y-auto">
          <h3 className="font-semibold text-slate-800 mb-4 sticky top-0 bg-white pb-1">
            Состояние врачей ({doctors.length})
            {selectedStudy && (
              <span className="ml-2 text-xs font-normal text-blue-600">
                — нажмите «Назначить» у нужного врача
              </span>
            )}
          </h3>

          <div className="space-y-3">
            {doctors.length === 0 ? (
              <div className="p-8 text-center text-slate-500">Нет активных врачей</div>
            ) : (
              doctors.map((doc) => (
                <DoctorCard
                  key={doc.id}
                  doc={doc}
                  isSelectedForAssign={selectedDoctor === doc.id}
                  isExpanded={expandedDoctor === doc.id}
                  studiesState={doctorStudies[doc.id] ?? { loading: false, studies: [], error: null }}
                  hasSelectedStudy={!!selectedStudy}
                  onToggleExpand={handleToggleExpand}
                  onSelectForAssign={handleSelectForAssign}
                />
              ))
            )}
          </div>
        </div>

        {/* Панель назначения — появляется когда выбрано исследование */}
        {selectedStudy && (
          <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg shrink-0">
            <h4 className="font-medium mb-1">
              {selectedStudy.research_number}
            </h4>
            <p className="text-blue-100 text-sm mb-3 flex items-center gap-2 flex-wrap">
              <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium mr-2 ${getPriorityColor(selectedStudy.priority)} !bg-blue-500 !text-white`}>
                {getPriorityLabel(selectedStudy.priority)}
              </span>
              <span>{selectedStudy.study_type?.name}</span>
              {selectedStudy.study_type?.modality && (
                <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-500/30 text-blue-100 text-[10px] font-medium uppercase tracking-wide">
                  {selectedStudy.study_type.modality}
                </span>
              )}
            </p>

            {selectedDoctor && (
              <p className="text-blue-100 text-sm mb-3">
                Врач: <strong>{doctors.find(d => d.id === selectedDoctor)?.fio_alias}</strong>
              </p>
            )}

            <div className="flex space-x-2">
              {selectedDoctor ? (
                <>
                  <button
                    onClick={() => handleAssign()}
                    className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50"
                  >
                    Подтвердить назначение
                  </button>
                  <button
                    onClick={() => setSelectedDoctor(null)}
                    className="px-3 py-2 bg-blue-500 text-white rounded-md text-sm hover:bg-blue-400"
                  >
                    Сбросить
                  </button>
                </>
              ) : (
                <p className="text-blue-200 text-sm py-1">
                  ↑ Нажмите «Назначить» рядом с нужным врачом
                </p>
              )}
              <button
                onClick={() => { setSelectedStudy(null); setSelectedDoctor(null); }}
                className="px-3 py-2 bg-blue-700 text-white border border-blue-500 rounded-md text-sm hover:bg-blue-800"
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};