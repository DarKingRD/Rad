import React, { useState, useEffect, useMemo } from 'react';
import { studiesApi, doctorsApi } from '../../services/api';
import { 
  UserCheck, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, 
  Loader2, RefreshCw, Zap, Calendar, CheckCircle, XCircle, Edit2,
  Save, X, AlertTriangle
} from 'lucide-react';
import { Study, DoctorWithLoad } from '../../types';

// ─── Константы и утилиты ────────────────────────────────────────────────────────
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
  if (status === 'signed' || status === 'Подписано') return 'bg-blue-100 text-blue-700';
  return 'bg-slate-100 text-slate-600';
};

const formatDate = (iso: string) =>
  new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit' });

const formatTime = (iso: string) =>
  new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

const getTodayString = () => new Date().toISOString().split('T')[0];

// ─── Типы ───────────────────────────────────────────────────────────────────────
interface DoctorStudiesState {
  loading: boolean;
  studies: Study[];
  error: string | null;
}

interface DoctorDistStat {
  doctor_id: number;
  doctor_name: string;
  assigned_studies: number;
  total_up: number;
  max_up: number;
  load_percent: number;
  remaining_up: number;
}

interface Assignment {
  study_number: string;
  doctor_id: number;
  doctor_name: string;
  priority: string;
  deadline: string;
  completion_time: string;
  tardiness_hours: number;
  up_value: number;
  is_overdue: boolean;
}

interface DistResult {
  doctor_stats: DoctorDistStat[];
  assigned: number;
  unassigned: number;
  total_weighted_tardiness: number;
  assignments: Assignment[];
  distribution_id?: string;
  preview_mode?: boolean;
  target_date?: string;
  _savedAt?: string;
  _savedDate?: string;
}

interface DateRange {
  min: string | null;
  max: string | null;
}

interface DistributionInfo {
  pending_studies: number;
  available_doctors: number;
  study_date_range: DateRange;
  schedule_date_range: DateRange;
  message: string;
}

// ─── Карточка врача ─────────────────────────────────────────────────────────────
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
  const totalUp = distStat ? distStat.total_up : (doc.current_load ?? 0);
  const maxUp = distStat ? distStat.max_up : (doc.max_load ?? 50);
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
        {/* Аватар */}
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white font-semibold text-sm shrink-0">
          {doc.fio_alias?.charAt(0) || 'В'}
        </div>

        {/* Информация о враче */}
        <div className="flex-1 min-w-0">
          <div className="font-medium text-slate-900 truncate">{doc.fio_alias || `Врач ${doc.id}`}</div>
          <div className="text-xs text-slate-500">{doc.specialty || doc.position_type}</div>
          {distStat && (
            <div className="text-[10px] text-blue-500 mt-0.5 font-medium flex items-center gap-1">
              <Calendar size={10} />
              смена: {distStat.assigned_studies} исслед.
            </div>
          )}
        </div>

        {/* Нагрузка */}
        <div className="text-right shrink-0 min-w-[140px]">
          <div className="text-sm font-semibold text-slate-900">
            {typeof totalUp === 'number' ? totalUp.toFixed(2) : totalUp}
            <span className="text-slate-400 font-normal"> / {maxUp} УП</span>
          </div>
          <div className="w-32 h-2 bg-slate-100 rounded-full mt-1 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ${
                isOverloaded ? 'bg-red-500' : loadPct > 50 ? 'bg-amber-400' : 'bg-green-500'
              }`}
              style={{ width: `${loadPct}%` }}
            />
          </div>
          <div className="text-xs mt-1 flex items-center justify-end gap-1">
            <UserCheck size={11} className={assignedCount > 0 ? 'text-green-500' : 'text-slate-300'} />
            <span className={assignedCount > 0 ? 'text-slate-700 font-medium' : 'text-slate-400'}>
              {assignedCount} исследований
            </span>
          </div>
        </div>

        {/* Кнопки */}
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

      {/* Раскрывающийся список исследований */}
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
                       : study.status === 'signed' ? 'Подписано'
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

// ─── Модальное окно подтверждения ───────────────────────────────────────────────
interface ConfirmModalProps {
  isOpen: boolean;
  distResult: DistResult | null;
  assignments: Assignment[];
  doctors: DoctorWithLoad[];
  onConfirm: () => void;
  onCancel: () => void;
  onReassign: (assignment: Assignment, newDoctorId: number) => void;
  confirming: boolean;
}

const ConfirmModal: React.FC<ConfirmModalProps> = ({
  isOpen,
  distResult,
  assignments,
  doctors,
  onConfirm,
  onCancel,
  onReassign,
  confirming,
}) => {
  const [editingAssignment, setEditingAssignment] = useState<Assignment | null>(null);

  if (!isOpen || !distResult) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-6xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Заголовок */}
        <div className="p-6 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold text-slate-900 flex items-center gap-2">
              <CheckCircle className="text-green-500" size={24} />
              Подтверждение распределения
            </h2>
            <p className="text-sm text-slate-500 mt-1">
              Дата: <span className="font-medium">{distResult.target_date}</span> |
              Назначено: <span className="font-medium text-green-600">{distResult.assigned}</span> |
              Не назначено: <span className="font-medium text-amber-600">{distResult.unassigned}</span>
            </p>
          </div>
          <button
            onClick={onCancel}
            className="p-2 hover:bg-slate-100 rounded-lg transition"
          >
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        {/* Контент */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Статистика по врачам */}
          <div>
            <h3 className="font-medium text-slate-800 mb-3 flex items-center gap-2">
              <UserCheck size={18} />
              Нагрузка врачей
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {distResult.doctor_stats?.map((stat) => {
                const loadPct = stat.max_up > 0 ? (stat.total_up / stat.max_up) * 100 : 0;
                const isOverloaded = loadPct > 80;
                return (
                  <div key={stat.doctor_id} className="border rounded-lg p-3 bg-slate-50">
                    <div className="text-sm font-medium text-slate-900 truncate">{stat.doctor_name}</div>
                    <div className="text-xs text-slate-500 mt-1">
                      {stat.assigned_studies} исслед. | {stat.total_up.toFixed(2)}/{stat.max_up} УП
                    </div>
                    <div className="w-full h-2 bg-slate-200 rounded-full mt-2">
                      <div
                        className={`h-full rounded-full transition-all ${
                          isOverloaded ? 'bg-red-500' : loadPct > 50 ? 'bg-amber-400' : 'bg-green-500'
                        }`}
                        style={{ width: `${Math.min(loadPct, 100)}%` }}
                      />
                    </div>
                    <div className="text-xs text-slate-400 mt-1">
                      {loadPct.toFixed(1)}% загрузки
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Таблица назначений */}
          <div>
            <h3 className="font-medium text-slate-800 mb-3 flex items-center gap-2">
              <Save size={18} />
              Назначения ({assignments.length})
            </h3>
            <div className="border rounded-lg overflow-hidden">
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">Исследование</th>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">Приоритет</th>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">Врач</th>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">УП</th>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">Запаздывание (ч)</th>
                      <th className="px-3 py-2 text-left text-slate-600 font-medium">Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assignments.slice(0, 100).map((assignment) => (
                      <tr key={assignment.study_number} className="border-t border-slate-100 hover:bg-slate-50">
                        <td className="px-3 py-2 font-medium text-slate-900">{assignment.study_number}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(assignment.priority)}`}>
                            {getPriorityLabel(assignment.priority)}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          {editingAssignment?.study_number === assignment.study_number ? (
                            <select
                              className="border rounded px-2 py-1 text-xs bg-white"
                              value={assignment.doctor_id}
                              onChange={(e) => {
                                onReassign(assignment, parseInt(e.target.value));
                                setEditingAssignment(null);
                              }}
                              onBlur={() => setEditingAssignment(null)}
                              autoFocus
                            >
                              {doctors.map((d) => (
                                <option key={d.id} value={d.id}>
                                  {d.fio_alias}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <span className="text-slate-700">{assignment.doctor_name}</span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-slate-600">{assignment.up_value.toFixed(3)}</td>
                        <td className={`px-3 py-2 font-medium ${assignment.tardiness_hours > 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {assignment.tardiness_hours.toFixed(2)}
                        </td>
                        <td className="px-3 py-2">
                          <button
                            onClick={() => setEditingAssignment(assignment)}
                            className="text-blue-600 hover:text-blue-800 transition"
                            title="Изменить врача"
                          >
                            <Edit2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {assignments.length > 100 && (
                <div className="p-3 text-center text-xs text-slate-500 bg-slate-50 border-t">
                  Показано 100 из {assignments.length} назначений
                </div>
              )}
            </div>
          </div>

          {/* Предупреждение о неназначенных */}
          {distResult.unassigned > 0 && (
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-start gap-3">
              <AlertTriangle className="text-amber-600 shrink-0" size={20} />
              <div>
                <div className="font-medium text-amber-800">
                  {distResult.unassigned} исследований не назначено
                </div>
                <p className="text-sm text-amber-700 mt-1">
                  Проверьте расписание врачей и совместимость модальностей
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Футер с кнопками */}
        <div className="p-6 border-t border-slate-200 flex justify-end gap-3 bg-slate-50">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-slate-300 rounded-lg text-slate-600 hover:bg-white transition"
          >
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={confirming}
            className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 flex items-center gap-2 transition"
          >
            {confirming ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Сохранение...
              </>
            ) : (
              <>
                <CheckCircle size={16} />
                Подтвердить и сохранить
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

// ─── Главный компонент ──────────────────────────────────────────────────────────
export const CurrentDistributionView: React.FC = () => {
  // Состояния для выбора даты
  const [selectedDate, setSelectedDate] = useState<string>(getTodayString());
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [dateRange, setDateRange] = useState<DistributionInfo | null>(null);

  // Состояния данных
  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);
  const [allStudies, setAllStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [loading, setLoading] = useState(true);

  // Состояния распределения
  const [distributing, setDistributing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [distResult, setDistResult] = useState<DistResult | null>(null);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // UI состояния
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(20);
  const [expandedDoctor, setExpandedDoctor] = useState<number | null>(null);
  const [doctorStudies, setDoctorStudies] = useState<Record<number, DoctorStudiesState>>({});

  // ─── Эффекты ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    loadDistributionInfo();
    loadData();
  }, []);

  // ─── Загрузка данных ──────────────────────────────────────────────────────────
  const loadDistributionInfo = async () => {
    try {
      const res = await fetch('/api/distribute/');
      const data = await res.json();
      setDateRange(data);
      if (data.study_date_range?.min) {
        setDateFrom(data.study_date_range.min);
      }
      if (data.study_date_range?.max) {
        setDateTo(data.study_date_range.max);
      }
    } catch (error) {
      console.error('Error loading distribution info:', error);
    }
  };

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

  const loadDoctorStudies = async (doctorId: number) => {
    if (doctorStudies[doctorId] && !doctorStudies[doctorId].error) return;
    setDoctorStudies((prev) => ({
      ...prev,
      [doctorId]: { loading: true, studies: [], error: null },
    }));
    try {
      const res = await studiesApi.getList({ diagnostician_id: doctorId, status: 'confirmed' });
      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: { loading: false, studies: res.data || [], error: null },
      }));
    } catch {
      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: { loading: false, studies: [], error: 'Ошибка загрузки' },
      }));
    }
  };

  // ─── Обработчики ──────────────────────────────────────────────────────────────
  const handleDistribute = async () => {
    setDistributing(true);
    try {
      const res = await fetch('/api/distribute/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          date: selectedDate,
          preview: true,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          use_mip: true,
        }),
      });
      const data = await res.json();

      if (res.ok) {
        setDistResult(data);
        setAssignments(data.assignments || []);
        setShowConfirmModal(true);
      } else {
        alert(`Ошибка: ${data.error || data.message}`);
      }
    } catch (err) {
      console.error('Distribution error:', err);
      alert('Ошибка при запуске распределения');
    } finally {
      setDistributing(false);
    }
  };

  const handleConfirmDistribution = async () => {
    if (!distResult?.distribution_id) {
      alert('Ошибка: нет ID распределения');
      return;
    }

    setConfirming(true);
    try {
      const res = await fetch('/api/distribute/confirm/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          distribution_id: distResult.distribution_id,
        }),
      });
      const data = await res.json();

      if (res.ok) {
        alert(`Успешно сохранено ${data.assigned} назначений!`);
        setShowConfirmModal(false);
        setDistResult(null);
        setAssignments([]);
        setDoctorStudies({});
        await loadData();
      } else {
        alert(`Ошибка: ${data.error || data.message}`);
      }
    } catch (err) {
      console.error('Confirm error:', err);
      alert('Ошибка при подтверждении распределения');
    } finally {
      setConfirming(false);
    }
  };

  const handleReassign = async (assignment: Assignment, newDoctorId: number) => {
    try {
      await studiesApi.assign(assignment.study_number, newDoctorId);
      setAssignments((prev) =>
        prev.map((a) =>
          a.study_number === assignment.study_number
            ? {
                ...a,
                doctor_id: newDoctorId,
                doctor_name: doctors.find((d) => d.id === newDoctorId)?.fio_alias || '',
              }
            : a
        )
      );
      setDistResult((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          doctor_stats: prev.doctor_stats.map((stat) => {
            if (stat.doctor_id === assignment.doctor_id) {
              return { ...stat, assigned_studies: stat.assigned_studies - 1 };
            }
            if (stat.doctor_id === newDoctorId) {
              return { ...stat, assigned_studies: stat.assigned_studies + 1 };
            }
            return stat;
          }),
        };
      });
    } catch (err) {
      alert('Ошибка при переназначении');
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
    setSelectedDoctor((prev) => (prev === doctorId ? null : doctorId));
  };

  const handleAssign = async () => {
    if (!selectedStudy) return;
    const targetId = selectedDoctor;
    if (!targetId) {
      alert('Выберите врача');
      return;
    }
    try {
      await studiesApi.assign(selectedStudy.id, targetId);
      setDoctorStudies((prev) => {
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

  // ─── Вычисления ───────────────────────────────────────────────────────────────
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

  const distStatMap = useMemo<Record<number, DoctorDistStat>>(() => {
    if (!distResult?.doctor_stats) return {};
    return Object.fromEntries(distResult.doctor_stats.map((s) => [s.doctor_id, s]));
  }, [distResult]);

  // ─── Рендер ───────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="animate-spin text-slate-400 mr-2" size={20} />
        Загрузка...
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* ── Панель выбора даты ────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <h2 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
          <Calendar size={20} className="text-blue-600" />
          Параметры распределения
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Дата распределения *
            </label>
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              min={dateRange?.schedule_date_range?.min || undefined}
              max={dateRange?.schedule_date_range?.max || undefined}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Исследования с
            </label>
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              min={dateRange?.study_date_range?.min || undefined}
              max={dateRange?.study_date_range?.max || undefined}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Исследования по
            </label>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              min={dateRange?.study_date_range?.min || undefined}
              max={dateRange?.study_date_range?.max || undefined}
            />
          </div>

          <div className="flex items-end">
            <button
              onClick={handleDistribute}
              disabled={distributing || !selectedDate}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {distributing ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Расчёт...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Рассчитать распределение
                </>
              )}
            </button>
          </div>
        </div>

        {dateRange && (
          <div className="mt-4 text-xs text-slate-500 flex flex-wrap gap-4">
            <span>
              📅 Исследования:{' '}
              <span className="font-medium">{dateRange.study_date_range.min || '—'}</span> —{' '}
              <span className="font-medium">{dateRange.study_date_range.max || '—'}</span>
            </span>
            <span>
              👨‍⚕️ Расписания:{' '}
              <span className="font-medium">{dateRange.schedule_date_range.min || '—'}</span> —{' '}
              <span className="font-medium">{dateRange.schedule_date_range.max || '—'}</span>
            </span>
          </div>
        )}
      </div>

      {/* ── Статистика распределения ─────────────────────────────────────────── */}
      {distResult && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-6 flex-wrap">
              <div>
                <span className="text-sm text-slate-500">Назначено:</span>
                <span className="ml-2 font-semibold text-green-700">{distResult.assigned}</span>
              </div>
              <div>
                <span className="text-sm text-slate-500">Не назначено:</span>
                <span className="ml-2 font-semibold text-amber-600">{distResult.unassigned}</span>
              </div>
              <div>
                <span className="text-sm text-slate-500">Z (взв. запаздывание):</span>
                <span className="ml-2 font-semibold text-slate-700">
                  {distResult.total_weighted_tardiness?.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-sm text-slate-500">Дата:</span>
                <span className="ml-2 font-semibold text-slate-700">{distResult.target_date}</span>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs rounded-full font-medium">
                Режим предпросмотра
              </span>
              <button
                onClick={() => setShowConfirmModal(true)}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm flex items-center gap-2 transition"
              >
                <CheckCircle size={16} />
                Подтвердить
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Основной контент ─────────────────────────────────────────────────── */}
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
                    <span className="font-medium text-slate-900 text-sm">{study.research_number}</span>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${getPriorityColor(
                        study.priority
                      )}`}
                    >
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
                    <span
                      className={`px-1.5 py-0.5 rounded ${getStatusColor(study.status)}`}
                    >
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

          {/* Пагинация */}
          {totalPages > 1 && (
            <div className="p-3 border-t border-slate-200 flex items-center justify-between shrink-0">
              <div className="text-xs text-slate-500">
                {startIndex + 1}–{Math.min(startIndex + itemsPerPage, sortedStudies.length)} из{' '}
                {sortedStudies.length}
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
                  · данные из текущего распределения
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
                <span
                  className={`inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-500/50 text-white`}
                >
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
                  Врач: <strong>{doctors.find((d) => d.id === selectedDoctor)?.fio_alias}</strong>
                </p>
              )}

              <div className="flex space-x-2">
                {selectedDoctor ? (
                  <>
                    <button
                      onClick={handleAssign}
                      className="flex-1 bg-white text-blue-600 py-2 rounded-md font-medium text-sm hover:bg-blue-50 transition"
                    >
                      Подтвердить назначение
                    </button>
                    <button
                      onClick={() => setSelectedDoctor(null)}
                      className="px-3 py-2 bg-blue-500 text-white rounded-md text-sm hover:bg-blue-400 transition"
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

      {/* ── Модальное окно подтверждения ─────────────────────────────────────── */}
      <ConfirmModal
        isOpen={showConfirmModal}
        distResult={distResult}
        assignments={assignments}
        doctors={doctors}
        onConfirm={handleConfirmDistribution}
        onCancel={() => setShowConfirmModal(false)}
        onReassign={handleReassign}
        confirming={confirming}
      />
    </div>
  );
};



