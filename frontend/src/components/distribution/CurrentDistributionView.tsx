import React, { useState, useEffect, useMemo } from 'react';
import { studiesApi, doctorsApi } from '../../services/api';
import { UserCheck, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Loader2, RefreshCw, Zap } from 'lucide-react';
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

// ─── Типы ───────────────────────────────────────────────────────────────────

interface DoctorStudiesState {
  loading: boolean;
  studies: Study[];
  error: string | null;
}

// Статистика врача из результата последнего распределения
interface DoctorDistStat {
  doctor_id: number;
  doctor_name: string;
  assigned_studies: number;
  total_up: number;
  max_up: number;
  load_percent: number;
  remaining_up: number;
}

// ─── Компонент карточки врача ────────────────────────────────────────────────

interface DoctorCardProps {
  doc: DoctorWithLoad;
  distStat?: DoctorDistStat;       // статистика из последнего распределения (если есть)
  isSelectedForAssign: boolean;
  isExpanded: boolean;
  studiesState: DoctorStudiesState;
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
  // Если есть данные из последнего распределения — используем их,
  // иначе — из ежемесячной статистики (with_load)
  const assignedCount = distStat?.assigned_studies ?? doc.active_studies ?? 0;
  const totalUp       = distStat ? distStat.total_up   : (doc.current_load ?? 0);
  const maxUp         = distStat ? distStat.max_up     : (doc.max_load ?? 50);
  const loadPct       = maxUp > 0 ? Math.min((totalUp / maxUp) * 100, 100) : 0;
  const isOverloaded  = loadPct > 80;

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
          <div className="w-10 h-10 shrink-0 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-sm">
            {doc.fio_alias.charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="font-medium text-slate-900 text-sm truncate">{doc.fio_alias}</div>
            <div className="text-xs text-slate-500">{doc.specialty}</div>
          </div>
        </div>

        {/* Нагрузка */}
        <div className="text-right shrink-0 min-w-[120px]">
          <div className="text-sm font-semibold text-slate-900">
            {typeof totalUp === 'number' ? totalUp.toFixed(2) : totalUp}
            <span className="text-slate-400 font-normal"> / {maxUp} УП</span>
          </div>
          {/* Прогресс-бар */}
          <div className="w-28 h-1.5 bg-slate-100 rounded-full mt-1 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isOverloaded ? 'bg-red-500' : loadPct > 50 ? 'bg-amber-400' : 'bg-green-500'
              }`}
              style={{ width: `${loadPct}%` }}
            />
          </div>
          {/* Количество исследований */}
          <div className="text-xs mt-1 flex items-center justify-end gap-1">
            <UserCheck size={11} className={assignedCount > 0 ? 'text-green-500' : 'text-slate-300'} />
            <span className={assignedCount > 0 ? 'text-slate-700 font-medium' : 'text-slate-400'}>
              {assignedCount} исследований
            </span>
          </div>
          {/* Метка из распределения */}
          {distStat && (
            <div className="text-[10px] text-blue-500 mt-0.5 font-medium">
              сегодняшняя смена
            </div>
          )}
        </div>

        {/* Кнопки */}
        <div className="flex flex-col gap-1 shrink-0">
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
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
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
                      {study.status === 'confirmed' ? 'Назначено'
                       : study.status === 'signed'  ? 'Подписано'
                       : study.status === 'pending' ? 'Ожидает'
                       : study.status}
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


// ─── Тип результата распределения + localStorage ─────────────────────────────

interface DistResult {
  doctor_stats: DoctorDistStat[];
  assigned: number;
  unassigned: number;
  total_weighted_tardiness: number;
  _savedAt?: string;
  _savedDate?: string;
}

const getTodayKey = () =>
  `radplan_dist_${new Date().toISOString().slice(0, 10)}`;

const loadDistResult = (): DistResult | null => {
  try {
    const raw = localStorage.getItem(getTodayKey());
    return raw ? (JSON.parse(raw) as DistResult) : null;
  } catch { return null; }
};

const saveDistResult = (result: DistResult): void => {
  try {
    const key = getTodayKey();
    localStorage.setItem(key, JSON.stringify({
      ...result,
      _savedAt: new Date().toISOString(),
      _savedDate: new Date().toISOString().slice(0, 10),
    }));
    // удаляем устаревшие ключи
    Object.keys(localStorage)
      .filter(k => k.startsWith('radplan_dist_') && k !== key)
      .forEach(k => localStorage.removeItem(k));
  } catch { /* ignore */ }
};

// ─── Главный компонент ───────────────────────────────────────────────────────

export const CurrentDistributionView: React.FC = () => {
  const [selectedStudy,  setSelectedStudy]  = useState<Study | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);
  const [allStudies,     setAllStudies]     = useState<Study[]>([]);
  const [doctors,        setDoctors]        = useState<DoctorWithLoad[]>([]);
  const [loading,        setLoading]        = useState(true);
  const [distributing,   setDistributing]   = useState(false);
  const [distResult,     setDistResult]     = useState<DistResult | null>(
    () => loadDistResult()
  );
  const [currentPage,    setCurrentPage]    = useState(1);
  const [itemsPerPage]                      = useState(20);

  const [expandedDoctor,  setExpandedDoctor]  = useState<number | null>(null);
  const [doctorStudies,   setDoctorStudies]   = useState<Record<number, DoctorStudiesState>>({});

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [studiesRes, doctorsRes] = await Promise.all([
        studiesApi.getPending(),
        doctorsApi.getWithLoad(),
      ]);
      setAllStudies(studiesRes.data || []);
      setDoctors(doctorsRes.data || []);
    } catch (error) {
      console.error('Error loading data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Запуск авто-распределения (POST /api/distribute/)
  const handleDistribute = async () => {
    setDistributing(true);
    try {
      const res = await fetch('/api/distribute/', { method: 'POST' });
      const data = await res.json();
      setDistResult(data);
      saveDistResult(data);  // ← сохраняем в localStorage
      // Сбрасываем кэш снимков врачей и перегружаем данные
      setDoctorStudies({});
      await loadData();
    } catch (err) {
      console.error('Distribution error:', err);
      alert('Ошибка при запуске распределения');
    } finally {
      setDistributing(false);
    }
  };

  const loadDoctorStudies = async (doctorId: number) => {
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
    } catch {
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
    setSelectedDoctor(prev => (prev === doctorId ? null : doctorId));
  };

  const sortedStudies = useMemo(() => {
    return [...allStudies].sort((a, b) => {
      const diff = (PRIORITY_ORDER[a.priority] || 3) - (PRIORITY_ORDER[b.priority] || 3);
      if (diff !== 0) return diff;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });
  }, [allStudies]);

  const totalPages  = Math.ceil(sortedStudies.length / itemsPerPage);
  const startIndex  = (currentPage - 1) * itemsPerPage;
  const paginatedStudies = sortedStudies.slice(startIndex, startIndex + itemsPerPage);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setSelectedStudy(null);
    setSelectedDoctor(null);
  };

  const handleAssign = async () => {
    if (!selectedStudy) return;
    const targetId = selectedDoctor;
    if (!targetId) { alert('Выберите врача'); return; }

    try {
      await studiesApi.assign(selectedStudy.id, targetId);
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

  // Карта doctor_id → stat из последнего распределения
  const distStatMap = useMemo<Record<number, DoctorDistStat>>(() => {
    if (!distResult?.doctor_stats) return {};
    return Object.fromEntries(distResult.doctor_stats.map(s => [s.doctor_id, s]));
  }, [distResult]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin text-slate-400 mr-2" size={20} />
        <span className="text-slate-500">Загрузка...</span>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-140px)] flex flex-col gap-4">

      {/* ── Верхняя панель: кнопка авторапределения + статистика ────────── */}
      <div className="flex items-center justify-between bg-white rounded-xl border border-slate-200 shadow-sm px-5 py-3">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-sm text-slate-500">Ожидают назначения: </span>
            <span className="font-semibold text-slate-900">{allStudies.length}</span>
          </div>
          <div>
            <span className="text-sm text-slate-500">Врачей: </span>
            <span className="font-semibold text-slate-900">{doctors.length}</span>
          </div>
          {distResult && (
            <>
              <div className="h-4 w-px bg-slate-200" />
              <div>
                <span className="text-sm text-slate-500">Назначено: </span>
                <span className="font-semibold text-green-700">{distResult.assigned}</span>
              </div>
              <div>
                <span className="text-sm text-slate-500">Не назначено: </span>
                <span className="font-semibold text-amber-600">{distResult.unassigned}</span>
              </div>
              <div>
                <span className="text-sm text-slate-500">Z = </span>
                <span className="font-semibold text-slate-700">{distResult.total_weighted_tardiness?.toFixed(2)}</span>
              </div>
              {distResult._savedAt && (
                <div className="text-xs text-slate-400 flex items-center gap-1">
                  <span>обновлено в</span>
                  <span className="font-medium text-slate-500">
                    {new Date(distResult._savedAt).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadData}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-slate-50 transition"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
          <button
            onClick={handleDistribute}
            disabled={distributing || allStudies.length === 0}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {distributing
              ? <><Loader2 size={14} className="animate-spin" /> Распределение...</>
              : <><Zap size={14} /> Авто-распределить</>
            }
          </button>
        </div>
      </div>

      {/* ── Основной контент: очередь + врачи ───────────────────────────── */}
      <div className="flex space-x-6 flex-1 min-h-0">

        {/* Левая колонка: очередь исследований */}
        <div className="w-1/2 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col min-h-0">
          <div className="p-4 border-b border-slate-200 shrink-0">
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
                  onClick={() => { setSelectedStudy(study); setSelectedDoctor(null); }}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selectedStudy?.id === study.id
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                      : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-medium text-slate-900 text-sm">{study.research_number}</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(study.priority)}`}>
                      {getPriorityLabel(study.priority)}
                    </span>
                  </div>
                  <div className="text-xs text-slate-600 mb-1 flex items-center gap-2 flex-wrap">
                    <span>{study.study_type?.name || `ID: ${study.study_type_id}`}</span>
                    {study.study_type?.modality && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                        {study.study_type.modality}
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Создано: {formatDate(study.created_at)}</span>
                    <span className={`px-1.5 py-0.5 rounded ${getStatusColor(study.status)}`}>
                      {study.status === 'pending' ? 'Ожидает'
                       : study.status === 'confirmed' ? 'Назначено'
                       : study.status}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Пагинация */}
          {totalPages > 1 && (
            <div className="p-3 border-t border-slate-200 flex items-center justify-between shrink-0">
              <div className="text-xs text-slate-500">
                {startIndex + 1}–{Math.min(startIndex + itemsPerPage, sortedStudies.length)} из {sortedStudies.length}
              </div>
              <div className="flex items-center space-x-1">
                <button
                  onClick={() => handlePageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  className="p-1.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ChevronLeft size={14} />
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
                      className={`px-2.5 py-1 rounded text-xs ${
                        currentPage === p
                          ? 'bg-blue-600 text-white'
                          : 'border border-slate-200 text-slate-600 hover:bg-slate-50'
                      }`}
                    >
                      {p}
                    </button>
                  );
                })}
                <button
                  onClick={() => handlePageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  className="p-1.5 rounded border border-slate-200 text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Правая колонка: врачи + панель назначения */}
        <div className="w-1/2 flex flex-col gap-4 min-h-0">

          <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex-1 overflow-y-auto p-4 min-h-0">
            <h3 className="font-semibold text-slate-800 mb-3 sticky top-0 bg-white pb-1 z-10">
              Состояние врачей ({doctors.length})
              {selectedStudy && (
                <span className="ml-2 text-xs font-normal text-blue-600">
                  — нажмите «Назначить» у нужного врача
                </span>
              )}
              {distResult && (
                <span className="ml-2 text-xs font-normal text-green-600">
                  · данные из последнего авто-распределения
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
                    distStat={distStatMap[doc.id]}
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

          {/* Панель назначения */}
          {selectedStudy && (
            <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg shrink-0">
              <h4 className="font-medium mb-1 text-sm">{selectedStudy.research_number}</h4>
              <p className="text-blue-100 text-xs mb-3 flex items-center gap-2 flex-wrap">
                <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-500/50 text-white`}>
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
                <p className="text-blue-100 text-xs mb-3">
                  Врач: <strong>{doctors.find(d => d.id === selectedDoctor)?.fio_alias}</strong>
                </p>
              )}

              <div className="flex space-x-2">
                {selectedDoctor ? (
                  <>
                    <button
                      onClick={handleAssign}
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
    </div>
  );
};