import React, { useEffect, useMemo, useState } from 'react';
import { distributionApi, studiesApi, doctorsApi } from '../../services/api';
import {
  UserCheck,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Loader2,
  Zap,
  Calendar,
  CheckCircle,
  X,
  Edit2,
  Save,
  AlertTriangle,
  Clock,
  Search,
  Archive,
  Filter,
  Eye,
  Users,
  FileWarning,
  BarChart3,
} from 'lucide-react';
import {
  Study,
  DoctorWithLoad,
  Assignment,
  DistResult,
  DistributionInfo,
  DoctorDistStat,
  DistributionDraft,
} from '../../types';

const DRAFTS_STORAGE_KEY = 'distribution_preview_drafts_v1';
const PRIORITY_ORDER: Record<string, number> = { cito: 1, asap: 2, normal: 3 };

type ConfirmTab = 'summary' | 'assigned' | 'unassigned' | 'doctors';
type AssignmentFilter = 'all' | 'cito' | 'asap' | 'normal';
type MobileTab = 'studies' | 'doctors';

const ITEMS_PER_PAGE = 20;
const DOCTORS_PER_PAGE = 8;

const getPriorityColor = (priority: string) => {
  if (priority === 'cito') return 'bg-red-100 text-red-700 border-red-200';
  if (priority === 'asap') return 'bg-amber-100 text-amber-700 border-amber-200';
  return 'bg-slate-100 text-slate-600 border-slate-200';
};

const getPriorityLabel = (priority: string) => {
  if (priority === 'cito') return 'CITO';
  if (priority === 'asap') return 'ASAP';
  return 'План';
};

const getStatusColor = (status: string) => {
  if (status === 'confirmed' || status === 'Подтверждено') return 'bg-green-100 text-green-700';
  if (status === 'signed' || status === 'Подписано') return 'bg-blue-100 text-blue-700';
  return 'bg-slate-100 text-slate-600';
};

const formatDate = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString('ru-RU', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
      })
    : '—';

const formatTime = (iso?: string | null) =>
  iso
    ? new Date(iso).toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
      })
    : '—';

const getTodayString = () => new Date().toISOString().split('T')[0];

const safelyReadDrafts = (): DistributionDraft[] => {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveDrafts = (drafts: DistributionDraft[]) => {
  localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(drafts.slice(0, 20)));
};

interface DoctorStudiesState {
  loading: boolean;
  studies: Study[];
  error: string | null;
}

interface DoctorCardProps {
  doc: DoctorWithLoad;
  distStat?: DoctorDistStat;
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
  const assignedCount = distStat?.assigned_studies ?? doc.active_studies ?? 0;
  const totalUp = distStat ? distStat.total_up : doc.current_load ?? 0;
  const maxUp = distStat ? distStat.max_up : doc.max_load ?? 50;
  const loadPct = maxUp > 0 ? Math.min((totalUp / maxUp) * 100, 100) : 0;
  const isOverloaded = loadPct > 80;

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
            className="text-xs px-3 py-1.5 rounded border border-slate-200 text-slate-500 hover:bg-slate-50 flex items-center gap-1"
          >
            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            Снимки
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="border-t border-slate-100 bg-slate-50 rounded-b-lg">
          {studiesState.loading ? (
            <div className="flex items-center justify-center py-4 gap-2 text-slate-400 text-sm">
              <Loader2 size={14} className="animate-spin" /> Загрузка...
            </div>
          ) : studiesState.error ? (
            <div className="py-3 px-4 text-sm text-red-500">{studiesState.error}</div>
          ) : studiesState.studies.length === 0 ? (
            <div className="py-3 px-4 text-sm text-slate-400">
              Нет назначенных исследований
            </div>
          ) : (
            <div className="p-2 space-y-1 max-h-64 overflow-y-auto">
              {studiesState.studies.map((study) => (
                <div
                  key={study.research_number}
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
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium border ${getPriorityColor(
                        study.priority
                      )}`}
                    >
                      {getPriorityLabel(study.priority)}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs ${getStatusColor(
                        study.status
                      )}`}
                    >
                      {study.status === 'confirmed'
                        ? 'Назначено'
                        : study.status === 'signed'
                        ? 'Подписано'
                        : 'Ожидает'}
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

const Pagination: React.FC<{
  currentPage: number;
  totalPages: number;
  startIndex: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
}> = ({ currentPage, totalPages, startIndex, totalItems, itemsPerPage, onPageChange }) => {
  if (totalPages <= 1) return null;

  const end = Math.min(startIndex + itemsPerPage, totalItems);

  return (
    <div className="px-4 py-3 border-t border-slate-200 flex items-center justify-between text-sm text-slate-500">
      <span>
        Показано {startIndex + 1}–{end} из {totalItems}
      </span>
      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="p-2 rounded border border-slate-200 disabled:opacity-40"
        >
          <ChevronLeft size={16} />
        </button>
        <span className="text-xs">
          {currentPage} / {totalPages}
        </span>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="p-2 rounded border border-slate-200 disabled:opacity-40"
        >
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

const ConfirmModal: React.FC<{
  isOpen: boolean;
  distResult: DistResult | null;
  doctors: DoctorWithLoad[];
  onConfirm: () => void;
  onCancel: () => void;
  onReassign: (assignment: Assignment, newDoctorId: number) => void;
  confirming: boolean;
}> = ({ isOpen, distResult, doctors, onConfirm, onCancel, onReassign, confirming }) => {
  const [editingAssignment, setEditingAssignment] = useState<Assignment | null>(null);
  const [activeTab, setActiveTab] = useState<ConfirmTab>('summary');
  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<AssignmentFilter>('all');
  const [selectedDoctorFilter, setSelectedDoctorFilter] = useState<'all' | number>('all');
  const [assignedPage, setAssignedPage] = useState(1);
  const pageSize = 25;

  useEffect(() => {
    if (isOpen) {
      setActiveTab('summary');
      setAssignedPage(1);
      setSearch('');
      setPriorityFilter('all');
      setSelectedDoctorFilter('all');
      setEditingAssignment(null);
    }
  }, [isOpen, distResult?.distribution_id]);

  if (!isOpen || !distResult) return null;

  const assigned = distResult.assignments || [];
  const unassignedCount = distResult.unassigned || 0;

  const filteredAssigned = assigned.filter((assignment) => {
    const searchMatch =
      !search ||
      assignment.study_number.toLowerCase().includes(search.toLowerCase()) ||
      assignment.doctor_name.toLowerCase().includes(search.toLowerCase());

    const priorityMatch =
      priorityFilter === 'all' || assignment.priority === priorityFilter;

    const doctorMatch =
      selectedDoctorFilter === 'all' || assignment.doctor_id === selectedDoctorFilter;

    return searchMatch && priorityMatch && doctorMatch;
  });

  const pagedAssigned = filteredAssigned.slice(
    (assignedPage - 1) * pageSize,
    assignedPage * pageSize
  );
  const totalAssignedPages = Math.max(1, Math.ceil(filteredAssigned.length / pageSize));

  const doctorSummary = [...(distResult.doctor_stats || [])].sort(
    (a, b) => b.assigned_studies - a.assigned_studies
  );

  const topDoctors = doctorSummary.slice(0, 5);
  const topDoctorsAssigned = topDoctors.reduce(
    (sum, item) => sum + item.assigned_studies,
    0
  );
  const avgLoad = doctorSummary.length
    ? doctorSummary.reduce((sum, item) => sum + item.load_percent, 0) /
      doctorSummary.length
    : 0;

  const summaryCards = [
    {
      title: 'Назначено',
      value: distResult.assigned,
      tone: 'text-green-700 bg-green-50 border-green-200',
      icon: CheckCircle,
    },
    {
      title: 'Не назначено',
      value: distResult.unassigned,
      tone: 'text-amber-700 bg-amber-50 border-amber-200',
      icon: FileWarning,
    },
    {
      title: 'CITO',
      value: `${distResult.cito_assigned ?? 0} / ${distResult.cito_total ?? 0}`,
      tone: 'text-red-700 bg-red-50 border-red-200',
      icon: AlertTriangle,
    },
    {
      title: 'Средняя просрочка',
      value: `${distResult.avg_tardiness ?? 0} ч`,
      tone: 'text-blue-700 bg-blue-50 border-blue-200',
      icon: Clock,
    },
  ];

  const tabs: { key: ConfirmTab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Сводка' },
    { key: 'assigned', label: 'Назначенные', count: assigned.length },
    { key: 'doctors', label: 'По врачам', count: doctorSummary.length },
    { key: 'unassigned', label: 'Неназначенные', count: unassignedCount },
  ];

  const TablePager = ({
    page,
    setPage,
    totalPages,
  }: {
    page: number;
    setPage: (page: number) => void;
    totalPages: number;
  }) => (
    <div className="flex items-center justify-between pt-3 text-xs text-slate-500">
      <span>
        Страница {page} из {totalPages}
      </span>
      <div className="flex items-center gap-1"> 
        <button
          onClick={() => setPage(Math.max(1, page - 1))}
          disabled={page === 1}
          className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
        >
          <ChevronLeft size={14} />
        </button>
        <button
          onClick={() => setPage(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          className="p-1.5 rounded border border-slate-200 disabled:opacity-40"
        >
          <ChevronRight size={14} />
        </button>
      </div>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-7xl w-full max-h-[92vh] overflow-hidden flex flex-col shadow-2xl">
        <div className="p-6 border-b border-slate-200 flex items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
              <CheckCircle className="text-green-500" size={24} />
              Подтверждение распределения
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              Дата: <span className="font-medium">{distResult.target_date || '—'}</span>
              {distResult._savedAt && (
                <span>
                  {' '}
                  · Черновик от {formatDate(distResult._savedAt)}{' '}
                  {formatTime(distResult._savedAt)}
                </span>
              )}
            </p>
          </div>
          <button onClick={onCancel} className="p-2 hover:bg-slate-100 rounded-lg transition">
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        <div className="p-4 border-b border-slate-200 flex flex-wrap gap-2 bg-slate-50">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition ${
                activeTab === tab.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-100'
              }`}
            >
              {tab.label}
              {typeof tab.count === 'number' ? ` (${tab.count})` : ''}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'summary' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {summaryCards.map((card) => {
                  const Icon = card.icon;
                  return (
                    <div key={card.title} className={`rounded-xl border p-4 ${card.tone}`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium">{card.title}</span>
                        <Icon size={18} />
                      </div>
                      <div className="text-2xl font-semibold">{card.value}</div>
                    </div>
                  );
                })}
              </div>

              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                <div className="border rounded-xl p-4">
                  <div className="flex items-center gap-2 text-slate-800 font-medium mb-3">
                    <BarChart3 size={18} />
                    Что получилось
                  </div>
                  <ul className="space-y-2 text-sm text-slate-600">
                    <li>
                      В распределении участвуют <strong>{doctorSummary.length}</strong> врачей.
                    </li>
                    <li>
                      Средняя загрузка по задействованным врачам —{' '}
                      <strong>{avgLoad.toFixed(1)}%</strong>.
                    </li>
                    <li>
                      Топ-5 врачей закрыли <strong>{topDoctorsAssigned}</strong> исследований.
                    </li>
                    <li>
                      Просроченных назначений в текущем preview:{' '}
                      <strong>{assigned.filter((a) => a.tardiness_hours > 0).length}</strong>.
                    </li>
                  </ul>
                </div>

                <div className="border rounded-xl p-4">
                  <div className="flex items-center gap-2 text-slate-800 font-medium mb-3">
                    <Users size={18} />
                    Самые загруженные врачи
                  </div>
                  <div className="space-y-3">
                    {topDoctors.length === 0 ? (
                      <div className="text-sm text-slate-500">Нет данных по врачам.</div>
                    ) : (
                      topDoctors.map((doctor) => (
                        <div key={doctor.doctor_id}>
                          <div className="flex items-center justify-between text-sm mb-1">
                            <span className="font-medium text-slate-700">
                              {doctor.doctor_name}
                            </span>
                            <span className="text-slate-500">
                              {doctor.assigned_studies} иссл. · {doctor.load_percent.toFixed(1)}%
                            </span>
                          </div>
                          <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                doctor.load_percent > 80
                                  ? 'bg-red-500'
                                  : doctor.load_percent > 50
                                  ? 'bg-amber-400'
                                  : 'bg-green-500'
                              }`}
                              style={{ width: `${Math.min(doctor.load_percent, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>

              {distResult.unassigned > 0 && (
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-3">
                  <AlertTriangle className="text-amber-600 shrink-0" size={20} />
                  <div>
                    <div className="font-medium text-amber-800">
                      Остались неназначенные исследования
                    </div>
                    <p className="text-sm text-amber-700 mt-1">
                      Сейчас в preview не назначено{' '}
                      <strong>{distResult.unassigned}</strong> исследований.
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          {activeTab === 'assigned' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="relative">
                  <Search
                    size={16}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Поиск по исследованию или врачу"
                    className="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm"
                  />
                </div>

                <select
                  value={priorityFilter}
                  onChange={(e) => setPriorityFilter(e.target.value as AssignmentFilter)}
                  className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="all">Все приоритеты</option>
                  <option value="cito">Только CITO</option>
                  <option value="asap">Только ASAP</option>
                  <option value="normal">Только плановые</option>
                </select>

                <select
                  value={selectedDoctorFilter}
                  onChange={(e) =>
                    setSelectedDoctorFilter(
                      e.target.value === 'all' ? 'all' : Number(e.target.value)
                    )
                  }
                  className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="all">Все врачи</option>
                  {doctors.map((doctor) => (
                    <option key={doctor.id} value={doctor.id}>
                      {doctor.fio_alias}
                    </option>
                  ))}
                </select>
              </div>

              <div className="border rounded-xl overflow-hidden">
                <div className="max-h-[52vh] overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 sticky top-0">
                      <tr>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Исследование
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Приоритет
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Врач
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          УП
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Просрочка
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Действия
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedAssigned.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                            Ничего не найдено
                          </td>
                        </tr>
                      ) : (
                        pagedAssigned.map((assignment) => (
                          <tr key={assignment.study_number} className="border-t border-slate-100">
                            <td className="px-3 py-3 font-medium text-slate-800">
                              {assignment.study_number}
                            </td>
                            <td className="px-3 py-3">
                              <span
                                className={`px-2 py-1 rounded text-xs border ${getPriorityColor(
                                  assignment.priority
                                )}`}
                              >
                                {getPriorityLabel(assignment.priority)}
                              </span>
                            </td>
                            <td className="px-3 py-3 text-slate-700">
                              {editingAssignment?.study_number === assignment.study_number ? (
                                <select
                                  defaultValue={assignment.doctor_id}
                                  onChange={(e) => {
                                    const newDoctorId = Number(e.target.value);
                                    onReassign(assignment, newDoctorId);
                                    setEditingAssignment(null);
                                  }}
                                  className="border border-slate-300 rounded px-2 py-1 text-xs"
                                >
                                  {doctors.map((doctor) => (
                                    <option key={doctor.id} value={doctor.id}>
                                      {doctor.fio_alias}
                                    </option>
                                  ))}
                                </select>
                              ) : (
                                assignment.doctor_name
                              )}
                            </td>
                            <td className="px-3 py-3 text-slate-600">
                              {assignment.up_value?.toFixed?.(3) ?? assignment.up_value}
                            </td>
                            <td className="px-3 py-3">
                              <span
                                className={
                                  assignment.tardiness_hours > 0
                                    ? 'text-red-600 font-medium'
                                    : 'text-green-600 font-medium'
                                }
                              >
                                {assignment.tardiness_hours.toFixed(2)} ч
                              </span>
                            </td>
                            <td className="px-3 py-3">
                              <button
                                onClick={() =>
                                  setEditingAssignment(
                                    editingAssignment?.study_number === assignment.study_number
                                      ? null
                                      : assignment
                                  )
                                }
                                className="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800 text-xs"
                              >
                                <Edit2 size={14} />
                                Изменить
                              </button>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="px-4 pb-3">
                  <TablePager
                    page={assignedPage}
                    setPage={setAssignedPage}
                    totalPages={totalAssignedPages}
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === 'doctors' && (
            <div className="border rounded-xl overflow-hidden">
              <div className="max-h-[60vh] overflow-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Врач</th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        Исследований
                      </th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">УП</th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">Лимит</th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        Загрузка
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {doctorSummary.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                          Нет данных по врачам
                        </td>
                      </tr>
                    ) : (
                      doctorSummary.map((doctor) => (
                        <tr key={doctor.doctor_id} className="border-t border-slate-100">
                          <td className="px-3 py-3 font-medium text-slate-800">
                            {doctor.doctor_name}
                          </td>
                          <td className="px-3 py-3 text-slate-600">
                            {doctor.assigned_studies}
                          </td>
                          <td className="px-3 py-3 text-slate-600">{doctor.total_up}</td>
                          <td className="px-3 py-3 text-slate-600">{doctor.max_up}</td>
                          <td className="px-3 py-3">
                            <div className="flex items-center gap-2">
                              <div className="w-28 h-2 rounded-full bg-slate-100 overflow-hidden">
                                <div
                                  className={`h-full rounded-full ${
                                    doctor.load_percent > 80
                                      ? 'bg-red-500'
                                      : doctor.load_percent > 50
                                      ? 'bg-amber-400'
                                      : 'bg-green-500'
                                  }`}
                                  style={{
                                    width: `${Math.min(doctor.load_percent, 100)}%`,
                                  }}
                                />
                              </div>
                              <span className="text-xs text-slate-600">
                                {doctor.load_percent.toFixed(1)}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'unassigned' && (
            <div className="space-y-4">
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl">
                <div className="font-medium text-amber-800">
                  {distResult.unassigned} исследований не назначено
                </div>
                <p className="text-sm text-amber-700 mt-1">
                  Сейчас backend не возвращает отдельный список неназначенных исследований в
                  preview. Поэтому здесь показывается только количество.
                </p>
              </div>

              <div className="border rounded-xl p-4">
                <div className="font-medium text-slate-800 mb-2">
                  Что стоит сделать дальше
                </div>
                <ul className="text-sm text-slate-600 space-y-2 list-disc pl-5">
                  <li>Проверить вкладку «По врачам» — возможно, перегружены конкретные врачи.</li>
                  <li>Проверить совместимость модальностей.</li>
                  <li>При необходимости пересчитать распределение на другую дату.</li>
                  <li>
                    Для полного списка неназначенных лучше добавить backend-эндпоинт.
                  </li>
                </ul>
              </div>
            </div>
          )}
        </div>

        <div className="p-4 border-t border-slate-200 flex items-center justify-between gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={confirming}
            className="px-5 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 inline-flex items-center gap-2"
          >
            {confirming ? <Loader2 size={16} className="animate-spin" /> : <Save size={16} />}
            Подтвердить и сохранить
          </button>
        </div>
      </div>
    </div>
  );
};

const CurrentDistributionView: React.FC = () => {
  const [studiesTotal, setStudiesTotal] = useState(0)
  const [studies, setStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);
  const [studiesLoading, setStudiesLoading] = useState(false);
  const [distributing, setDistributing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);
  const [expandedDoctor, setExpandedDoctor] = useState<number | null>(null);

  const [doctorStudies, setDoctorStudies] = useState<Record<number, DoctorStudiesState>>({});
  const [distInfo, setDistInfo] = useState<DistributionInfo | null>(null);
  const [distResult, setDistResult] = useState<DistResult | null>(null);

  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [showDrafts, setShowDrafts] = useState(false);
  const [drafts, setDrafts] = useState<DistributionDraft[]>([]);

  const [distributionDate, setDistributionDate] = useState(getTodayString());
  const [distributionDateFrom, setDistributionDateFrom] = useState('');
  const [distributionDateTo, setDistributionDateTo] = useState('');
  const [useMip, setUseMip] = useState(true);

  const [mobileTab, setMobileTab] = useState<MobileTab>('studies');
  const [currentPage, setCurrentPage] = useState(1);
  const [doctorPage, setDoctorPage] = useState(1);

  const totalPages = Math.max(1, Math.ceil(studiesTotal / ITEMS_PER_PAGE))
  const paginatedStudies = studies;

  const totalDoctorPages = Math.max(1, Math.ceil(doctors.length / DOCTORS_PER_PAGE));
  const doctorStartIndex = (doctorPage - 1) * DOCTORS_PER_PAGE;
  const paginatedDoctors = doctors.slice(
    doctorStartIndex,
    doctorStartIndex + DOCTORS_PER_PAGE
  );

  const distStatMap = useMemo<Record<number, DoctorDistStat>>(() => {
    const map: Record<number, DoctorDistStat> = {};
    (distResult?.doctor_stats || []).forEach((item) => {
      map[item.doctor_id] = item;
    });
    return map;
  }, [distResult]);

  const loadDrafts = () => setDrafts(safelyReadDrafts());

  const persistDraft = (result: DistResult) => {
    if (!result.distribution_id) return;

    const now = new Date().toISOString();
    const nextDraft: DistributionDraft = {
      ...result,
      distribution_id: result.distribution_id,
      _savedAt: now,
      _savedDate: result.target_date || distributionDate,
    };

    const current = safelyReadDrafts().filter(
      (item) => item.distribution_id !== result.distribution_id
    );
    const merged = [nextDraft, ...current];
    saveDrafts(merged);
    setDrafts(merged);
  };

  const removeDraft = (distributionId: string) => {
    const next = safelyReadDrafts().filter((item) => item.distribution_id !== distributionId);
    saveDrafts(next);
    setDrafts(next);

    if (distResult?.distribution_id === distributionId) {
      setDistResult(null);
      setShowConfirmModal(false);
    }
  };

  const openDraft = (draft: DistributionDraft) => {
    setDistResult(draft);
    setDistributionDate(draft.target_date || draft._savedDate || getTodayString());
    setShowDrafts(false);
    setShowConfirmModal(true);
  };

  const loadStudies = async () => {
  setStudiesLoading(true);
  setError(null);

  try {
    const pendingData = await studiesApi.getPending(currentPage, ITEMS_PER_PAGE);

    const pendingResults = pendingData.results || [];

    const sortedStudies = [...pendingResults].sort((a: Study, b: Study) => {
      const priorityDiff =
        (PRIORITY_ORDER[a.priority] || 999) -
        (PRIORITY_ORDER[b.priority] || 999);

      if (priorityDiff !== 0) return priorityDiff;

      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });

    setStudies(sortedStudies);
    setStudiesTotal(pendingData.total || pendingResults.length);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Ошибка загрузки исследований';
    setError(message);
  } finally {
    setStudiesLoading(false);
  }
};

  const loadData = async () => {
  setLoading(true);
  setError(null);

  try {
    const [doctorsData, infoData] = await Promise.all([
      doctorsApi.getWithLoad(),
      distributionApi.getInfo(),
    ]);

    setDoctors(doctorsData || []);
    setDistInfo(infoData || null);

    loadDrafts();

  } catch (err) {
    const message = err instanceof Error ? err.message : 'Ошибка загрузки данных';
    setError(message);
  } finally {
    setLoading(false);
  }
};

  useEffect(() => {
  loadData();
}, []);

  useEffect(() => {
  loadStudies();
}, [currentPage]);

  const handleToggleExpand = async (doctorId: number) => {
    setExpandedDoctor((prev) => (prev === doctorId ? null : doctorId));

    if (doctorStudies[doctorId]) return;

    setDoctorStudies((prev) => ({
      ...prev,
      [doctorId]: { loading: true, studies: [], error: null },
    }));

    try {
      const studiesData = await studiesApi.getAll({
        diagnostician_id: doctorId,
        status: 'confirmed',
      });

      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: { loading: false, studies: studiesData || [], error: null },
      }));
    } catch {
      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: {
          loading: false,
          studies: [],
          error: 'Не удалось загрузить исследования врача',
        },
      }));
    }
  };

  const handleSelectForAssign = (doctorId: number) => {
    setSelectedDoctor(doctorId);
  };

  const handleAssign = async () => {
    if (!selectedStudy || !selectedDoctor) return;

    try {
      await studiesApi.assign(selectedStudy.research_number, selectedDoctor);

      setStudies((prev) =>
        prev.filter((study) => study.research_number !== selectedStudy.research_number)
      );

      setSelectedStudy(null);
      setSelectedDoctor(null);

      await loadData();
    } catch (err: any) {
      setError(err?.response?.data?.error || 'Ошибка назначения исследования');
    }
  };

  const handleRunDistribution = async () => {
  setDistributing(true);
  setError(null);

  try {
    const payload = {
      date: distributionDate,
      preview: true,
      date_from: distributionDateFrom || undefined,
      date_to: distributionDateTo || undefined,
      use_mip: useMip,
    };

    const result = await distributionApi.preview(payload);
    setDistResult(result);
    persistDraft(result);
    setShowConfirmModal(true);
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Ошибка запуска распределения';
    setError(message);
  } finally {
    setDistributing(false);
  }
};

const handleConfirmDistribution = async () => {
  if (!distResult?.distribution_id) return;

  setConfirming(true);
  try {
    await distributionApi.confirm(distResult.distribution_id);
    removeDraft(distResult.distribution_id);
    setShowConfirmModal(false);
    setDistResult(null);
    await loadData();
    await loadStudies();
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Ошибка подтверждения распределения';
    setError(message);
  } finally {
    setConfirming(false);
  }
};

  const handleReassign = (assignment: Assignment, newDoctorId: number) => {
    if (!distResult) return;

    const doctor = doctors.find((item) => item.id === newDoctorId);
    if (!doctor) return;

    const updatedAssignments = distResult.assignments.map((item) =>
      item.study_number === assignment.study_number
        ? {
            ...item,
            doctor_id: newDoctorId,
            doctor_name: doctor.fio_alias,
          }
        : item
    );

    const updatedDoctorStats = [...(distResult.doctor_stats || [])];
    const oldDoctorStat = updatedDoctorStats.find((item) => item.doctor_id === assignment.doctor_id);
    const newDoctorStat = updatedDoctorStats.find((item) => item.doctor_id === newDoctorId);

    if (oldDoctorStat) {
      oldDoctorStat.assigned_studies = Math.max(0, oldDoctorStat.assigned_studies - 1);
      oldDoctorStat.total_up = Math.max(0, oldDoctorStat.total_up - assignment.up_value);
      oldDoctorStat.load_percent =
        oldDoctorStat.max_up > 0 ? (oldDoctorStat.total_up / oldDoctorStat.max_up) * 100 : 0;
      oldDoctorStat.remaining_up = Math.max(0, oldDoctorStat.max_up - oldDoctorStat.total_up);
    }

    if (newDoctorStat) {
      newDoctorStat.assigned_studies += 1;
      newDoctorStat.total_up += assignment.up_value;
      newDoctorStat.load_percent =
        newDoctorStat.max_up > 0 ? (newDoctorStat.total_up / newDoctorStat.max_up) * 100 : 0;
      newDoctorStat.remaining_up = Math.max(0, newDoctorStat.max_up - newDoctorStat.total_up);
    }

    const nextResult: DistResult = {
      ...distResult,
      assignments: updatedAssignments,
      doctor_stats: updatedDoctorStats,
    };

    setDistResult(nextResult);
    persistDraft(nextResult);
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center text-slate-500">
        <Loader2 className="animate-spin mr-2" size={18} />
        Загрузка данных...
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 space-y-4">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 md:p-5">
        <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
              <Zap className="text-blue-600" size={22} />
              Текущее распределение
            </h1>
            <p className="text-sm text-slate-500 mt-1">
              Очередь исследований, выбор врача и подтверждение preview-распределения
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => {
                loadDrafts();
                setShowDrafts(true);
              }}
              className="px-3 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm flex items-center gap-2"
            >
              <Archive size={16} />
              Несохранённые распределения
              {drafts.length > 0 && (
                <span className="px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 text-xs">
                  {drafts.length}
                </span>
              )}
            </button>

            <button
              onClick={loadData}
              className="px-3 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm"
            >
              Обновить
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 mt-5">
          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50">
            <div className="text-xs text-slate-500 mb-1">Очередь</div>
            <div className="text-2xl font-semibold text-slate-900">{distInfo?.pending_studies ?? studiesTotal}</div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50">
            <div className="text-xs text-slate-500 mb-1">Доступные врачи</div>
            <div className="text-2xl font-semibold text-slate-900">
              {distInfo?.available_doctors ?? doctors.length}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50">
            <div className="text-xs text-slate-500 mb-1">Диапазон исследований</div>
            <div className="text-sm font-medium text-slate-800">
              {distInfo?.study_date_range?.min || '—'} → {distInfo?.study_date_range?.max || '—'}
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50">
            <div className="text-xs text-slate-500 mb-1">Расписания</div>
            <div className="text-sm font-medium text-slate-800">
              {distInfo?.schedule_date_range?.min || '—'} → {distInfo?.schedule_date_range?.max || '—'}
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 lg:grid-cols-5 gap-3">
          <div className="lg:col-span-1">
            <label className="text-xs text-slate-500 mb-1 block">Дата распределения</label>
            <div className="relative">
              <Calendar size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="date"
                value={distributionDate}
                onChange={(e) => setDistributionDate(e.target.value)}
                className="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="lg:col-span-1">
            <label className="text-xs text-slate-500 mb-1 block">Период от</label>
            <input
              type="date"
              value={distributionDateFrom}
              onChange={(e) => setDistributionDateFrom(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          <div className="lg:col-span-1">
            <label className="text-xs text-slate-500 mb-1 block">Период до</label>
            <input
              type="date"
              value={distributionDateTo}
              onChange={(e) => setDistributionDateTo(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm"
            />
          </div>

          <div className="lg:col-span-1 flex items-end">
            <label className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm flex items-center gap-2 bg-white cursor-pointer">
              <input
                type="checkbox"
                checked={useMip}
                onChange={(e) => setUseMip(e.target.checked)}
              />
              Использовать MIP
            </label>
          </div>

          <div className="lg:col-span-1 flex items-end">
            <button
              onClick={handleRunDistribution}
              disabled={distributing}
              className="w-full px-4 py-2.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2 text-sm font-medium"
            >
              {distributing ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Расчёт...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Запустить preview
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {distResult && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
          <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 flex-1">
              <div className="rounded-lg border border-green-200 bg-green-50 p-3">
                <div className="text-xs text-green-700">Назначено</div>
                <div className="text-xl font-semibold text-green-800 mt-1">
                  {distResult.assigned}
                </div>
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                <div className="text-xs text-amber-700">Не назначено</div>
                <div className="text-xl font-semibold text-amber-800 mt-1">
                  {distResult.unassigned}
                </div>
              </div>
              <div className="rounded-lg border border-red-200 bg-red-50 p-3">
                <div className="text-xs text-red-700">CITO</div>
                <div className="text-xl font-semibold text-red-800 mt-1">
                  {distResult.cito_assigned ?? 0}/{distResult.cito_total ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
                <div className="text-xs text-blue-700">Средняя просрочка</div>
                <div className="text-xl font-semibold text-blue-800 mt-1">
                  {distResult.avg_tardiness ?? 0} ч
                </div>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowConfirmModal(true)}
                className="px-4 py-2 bg-white border border-slate-300 text-slate-700 rounded-lg hover:bg-slate-50 text-sm flex items-center gap-2 transition"
              >
                <Eye size={16} />
                Открыть результат
              </button>
              <button
                onClick={handleConfirmDistribution}
                disabled={confirming}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm flex items-center gap-2 transition disabled:opacity-50"
              >
                {confirming ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Save size={16} />
                )}
                Подтвердить
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="md:hidden flex rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
        <button
          onClick={() => setMobileTab('studies')}
          className={`flex-1 py-3 text-sm font-medium transition-colors ${
            mobileTab === 'studies'
              ? 'bg-blue-600 text-white'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          Исследования ({studiesTotal})
        </button>
        <button
          onClick={() => setMobileTab('doctors')}
          className={`flex-1 py-3 text-sm font-medium transition-colors ${
            mobileTab === 'doctors'
              ? 'bg-blue-600 text-white'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          Врачи ({doctors.length})
        </button>
      </div>

      <div
        className="hidden md:flex gap-6"
        style={{ height: 'calc(100vh - 390px)', minHeight: '500px' }}
      >
        <div className="w-1/2 bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
          <div className="p-4 border-b border-slate-200 shrink-0 flex items-center justify-between">
            <h3 className="font-semibold text-slate-800">Очередь исследований ({studiesTotal})</h3>
            <span className="text-xs text-slate-500">Приоритет уже отсортирован сервером</span>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-0">

            {studiesLoading ? (
              <div className="flex items-center justify-center py-10 text-slate-400">
                <Loader2 size={16} className="animate-spin mr-2" />
                Загрузка исследований...
              </div>

            ) : paginatedStudies.length === 0 ? (

              <div className="p-8 text-center text-slate-500">
                Нет исследований в очереди
              </div>

            ) : (

              paginatedStudies.map((study) => (
                <div
                  key={study.research_number}
                  onClick={() => {
                    setSelectedStudy(study);
                    setSelectedDoctor(null);
                  }}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    selectedStudy?.research_number === study.research_number
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                      : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                  }`}
                >

                  <div className="flex justify-between items-start mb-1">
                    <span className="font-medium text-slate-900 text-sm">
                      {study.research_number}
                    </span>

                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium border ${getPriorityColor(
                        study.priority
                      )}`}
                    >
                      {getPriorityLabel(study.priority)}
                    </span>
                  </div>

                  <div className="text-xs text-slate-600 mb-1 flex items-center gap-2 flex-wrap">
                    <span>
                      {study.study_type?.name || `ID: ${study.study_type_id}`}
                    </span>

                    {study.study_type?.modality && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                        {study.study_type.modality}
                      </span>
                    )}
                  </div>

                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Создано: {formatDate(study.created_at)}</span>

                    <span className={`px-1.5 py-0.5 rounded ${getStatusColor(study.status)}`}>
                      {study.status === 'pending'
                        ? 'Ожидает'
                        : study.status === 'confirmed'
                        ? 'Назначено'
                        : study.status}
                    </span>
                  </div>

                </div>
              ))

            )}

          </div>

          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            startIndex={(currentPage - 1) * ITEMS_PER_PAGE}
            totalItems={studiesTotal}
            itemsPerPage={ITEMS_PER_PAGE}
            onPageChange={setCurrentPage}
          />
        </div>

        <div className="w-1/2 flex flex-col gap-3 overflow-hidden">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col flex-1 overflow-hidden min-h-0">
            <div className="p-4 border-b border-slate-200 shrink-0 flex items-center justify-between">
              <h3 className="font-semibold text-slate-800">Врачи ({doctors.length})</h3>
              {selectedStudy && (
                <span className="text-xs text-blue-600">
                  Выберите врача кнопкой «Назначить»
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
              {doctors.length === 0 ? (
                <div className="p-8 text-center text-slate-500">Нет активных врачей</div>
              ) : (
                paginatedDoctors.map((doc) => (
                  <DoctorCard
                    key={doc.id}
                    doc={doc}
                    distStat={distStatMap[doc.id]}
                    isSelectedForAssign={selectedDoctor === doc.id}
                    isExpanded={expandedDoctor === doc.id}
                    studiesState={
                      doctorStudies[doc.id] ?? {
                        loading: false,
                        studies: [],
                        error: null,
                      }
                    }
                    hasSelectedStudy={!!selectedStudy}
                    onToggleExpand={handleToggleExpand}
                    onSelectForAssign={handleSelectForAssign}
                  />
                ))
              )}
            </div>

            <Pagination
              currentPage={doctorPage}
              totalPages={totalDoctorPages}
              startIndex={doctorStartIndex}
              totalItems={doctors.length}
              itemsPerPage={DOCTORS_PER_PAGE}
              onPageChange={setDoctorPage}
            />
          </div>

          {selectedStudy && (
            <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg shrink-0">
              <h4 className="font-medium mb-1 text-sm">{selectedStudy.research_number}</h4>
              <p className="text-blue-100 text-xs mb-3 flex items-center gap-2 flex-wrap">
                <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-500/50 text-white">
                  {getPriorityLabel(selectedStudy.priority)}
                </span>
                <span>{selectedStudy.study_type?.name}</span>
                {selectedStudy.study_type?.modality && (
                  <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-blue-500/30 text-blue-100 text-[10px] font-medium uppercase tracking-wide">
                    {selectedStudy.study_type.modality}
                  </span>
                )}
              </p>

              {selectedDoctor ? (
                <p className="text-blue-100 text-xs mb-3">
                  Врач:{' '}
                  <strong>
                    {doctors.find((doctor) => doctor.id === selectedDoctor)?.fio_alias}
                  </strong>
                </p>
              ) : (
                <p className="text-blue-200 text-sm py-1 mb-2">
                  ↑ Нажмите «Назначить» рядом с нужным врачом
                </p>
              )}

              <div className="flex space-x-2">
                {selectedDoctor && (
                  <button
                    onClick={handleAssign}
                    className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50 transition"
                  >
                    Подтвердить назначение
                  </button>
                )}
                <button
                  onClick={() => {
                    setSelectedStudy(null);
                    setSelectedDoctor(null);
                  }}
                  className="px-3 py-2 bg-blue-700 text-white border border-blue-500 rounded-md text-sm hover:bg-blue-800 transition"
                >
                  Отмена
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="md:hidden">
        {mobileTab === 'studies' ? (
          <div
            className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden"
            style={{ height: 'calc(100vh - 390px)', minHeight: '400px' }}
          >
            <div className="flex-1 overflow-y-auto p-2 space-y-2 min-h-0">

              {studiesLoading ? (
                <div className="flex items-center justify-center py-10 text-slate-400">
                  <Loader2 size={16} className="animate-spin mr-2" />
                  Загрузка исследований...
                </div>
              ) : paginatedStudies.length === 0 ? (
                <div className="p-8 text-center text-slate-500">
                  Нет исследований в очереди
                </div>
              ) : (
                paginatedStudies.map((study) => (
                  <div
                    key={study.research_number}
                    onClick={() => {
                      setSelectedStudy(study);
                      setSelectedDoctor(null);
                    }}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      selectedStudy?.research_number === study.research_number
                        ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-500'
                        : 'border-slate-200 hover:border-blue-300 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-1">
                      <span className="font-medium text-slate-900 text-sm">
                        {study.research_number}
                      </span>

                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium border ${getPriorityColor(
                          study.priority
                        )}`}
                      >
                        {getPriorityLabel(study.priority)}
                      </span>
                    </div>

                    <div className="text-xs text-slate-600 mb-1 flex items-center gap-2 flex-wrap">
                      <span>
                        {study.study_type?.name || `ID: ${study.study_type_id}`}
                      </span>

                      {study.study_type?.modality && (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-700">
                          {study.study_type.modality}
                        </span>
                      )}
                    </div>

                    <div className="flex justify-between text-xs text-slate-400">
                      <span>Создано: {formatDate(study.created_at)}</span>

                      <span className={`px-1.5 py-0.5 rounded ${getStatusColor(study.status)}`}>
                        {study.status === 'pending'
                          ? 'Ожидает'
                          : study.status === 'confirmed'
                          ? 'Назначено'
                          : study.status}
                      </span>
                    </div>
                  </div>
                ))
              )}

            </div>

            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              startIndex={(currentPage - 1) * ITEMS_PER_PAGE}
              totalItems={studiesTotal}
              itemsPerPage={ITEMS_PER_PAGE}
              onPageChange={setCurrentPage}
            />
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div
              className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden"
              style={{ height: 'calc(100vh - 420px)', minHeight: '360px' }}
            >
              <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
                {selectedStudy && (
                  <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-700">
                    Выбрано: <strong>{selectedStudy.research_number}</strong>. Теперь
                    выберите врача.
                  </div>
                )}

                {paginatedDoctors.map((doc) => (
                  <DoctorCard
                    key={doc.id}
                    doc={doc}
                    distStat={distStatMap[doc.id]}
                    isSelectedForAssign={selectedDoctor === doc.id}
                    isExpanded={expandedDoctor === doc.id}
                    studiesState={
                      doctorStudies[doc.id] ?? {
                        loading: false,
                        studies: [],
                        error: null,
                      }
                    }
                    hasSelectedStudy={!!selectedStudy}
                    onToggleExpand={handleToggleExpand}
                    onSelectForAssign={handleSelectForAssign}
                  />
                ))}
              </div>

              <Pagination
                currentPage={doctorPage}
                totalPages={totalDoctorPages}
                startIndex={doctorStartIndex}
                totalItems={doctors.length}
                itemsPerPage={DOCTORS_PER_PAGE}
                onPageChange={setDoctorPage}
              />
            </div>

            {selectedStudy && selectedDoctor && (
              <div className="bg-blue-600 text-white p-4 rounded-xl shadow-lg">
                <div className="text-sm font-medium mb-1">{selectedStudy.research_number}</div>
                <div className="text-xs text-blue-200 mb-3">
                  Врач:{' '}
                  <strong>
                    {doctors.find((doctor) => doctor.id === selectedDoctor)?.fio_alias}
                  </strong>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleAssign}
                    className="flex-1 bg-white text-blue-600 py-2.5 rounded-lg font-medium text-sm hover:bg-blue-50 transition"
                  >
                    Подтвердить назначение
                  </button>
                  <button
                    onClick={() => {
                      setSelectedStudy(null);
                      setSelectedDoctor(null);
                    }}
                    className="px-3 py-2 bg-blue-700 rounded-lg text-sm hover:bg-blue-800 transition"
                  >
                    Отмена
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showDrafts && (
        <div className="fixed inset-0 bg-black/40 z-40 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-4xl w-full max-h-[85vh] overflow-hidden flex flex-col shadow-2xl">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2 text-slate-900 font-semibold">
                <Archive size={18} />
                Несохранённые распределения
              </div>
              <button
                onClick={() => setShowDrafts(false)}
                className="p-2 rounded-lg hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-5 flex-1 overflow-y-auto">
              {drafts.length === 0 ? (
                <div className="text-center py-12 text-slate-500">
                  Черновиков пока нет.
                </div>
              ) : (
                <div className="space-y-3">
                  {drafts.map((draft) => (
                    <div
                      key={draft.distribution_id}
                      className="border border-slate-200 rounded-xl p-4 flex items-start justify-between gap-4"
                    >
                      <div className="min-w-0">
                        <div className="font-medium text-slate-900">
                          Распределение на {draft._savedDate || draft.target_date || '—'}
                        </div>
                        <div className="text-sm text-slate-500 mt-1">
                          Создано: {formatDate(draft._savedAt)} {formatTime(draft._savedAt)}
                        </div>
                        <div className="flex flex-wrap gap-2 mt-3 text-xs">
                          <span className="px-2 py-1 rounded-full bg-green-100 text-green-700">
                            Назначено: {draft.assigned}
                          </span>
                          <span className="px-2 py-1 rounded-full bg-amber-100 text-amber-700">
                            Не назначено: {draft.unassigned}
                          </span>
                          <span className="px-2 py-1 rounded-full bg-red-100 text-red-700">
                            CITO: {draft.cito_assigned ?? 0}/{draft.cito_total ?? 0}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        <button
                          onClick={() => openDraft(draft)}
                          className="px-3 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm"
                        >
                          Открыть
                        </button>
                        <button
                          onClick={() => removeDraft(draft.distribution_id)}
                          className="px-3 py-2 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 text-sm"
                        >
                          Удалить
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
 
      <ConfirmModal
        isOpen={showConfirmModal}
        distResult={distResult}
        doctors={doctors}
        onConfirm={handleConfirmDistribution}
        onCancel={() => setShowConfirmModal(false)}
        onReassign={handleReassign}
        confirming={confirming}
      />
    </div>
  );
};

export default CurrentDistributionView;