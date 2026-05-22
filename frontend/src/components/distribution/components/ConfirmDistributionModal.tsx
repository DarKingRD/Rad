import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Clock,
  FileWarning,
  Search,
  Users,
  X,
} from 'lucide-react';
import type { Assignment, DistResult, DoctorWithLoad } from '../../../types';
import type { AssignmentFilter, ConfirmTab } from '../utils/distributionConstants';
import { getPriorityColor, getPriorityLabel } from '../utils/distributionFormatters';
import Pagination from './Pagination';

interface ConfirmDistributionModalProps {
  isOpen: boolean;
  distResult: DistResult | null;
  doctors: DoctorWithLoad[];
  onConfirm: () => void;
  onCancel: () => void;
  onReassign: (assignment: Assignment, newDoctorId: number) => void;
  confirming: boolean;
}

const PAGE_SIZE = 10;

const priorityRows = [
  { key: 'plan' as const, label: 'Плановые' },
  { key: 'asap' as const, label: 'Срочные' },
  { key: 'cito' as const, label: 'CITO' },
];

const ConfirmDistributionModal = ({
  isOpen,
  distResult,
  doctors,
  onConfirm,
  onCancel,
  onReassign,
  confirming,
}: ConfirmDistributionModalProps) => {
  const [activeTab, setActiveTab] = useState<ConfirmTab>('summary');
  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<AssignmentFilter>('all');
  const [selectedDoctorFilter, setSelectedDoctorFilter] = useState<number | 'all'>('all');
  const [assignedPage, setAssignedPage] = useState(1);
  const [unassignedPage, setUnassignedPage] = useState(1);

  useEffect(() => {
    if (isOpen) {
      setActiveTab('summary');
      setAssignedPage(1);
      setUnassignedPage(1);
      setSearch('');
      setPriorityFilter('all');
      setSelectedDoctorFilter('all');
    }
  }, [isOpen, distResult?.distribution_id]);

  const assignments = distResult?.assignments || [];
  const assigned = assignments.filter((item) => item.doctor_id !== null && item.doctor_id !== undefined);
  const unassigned = assignments.filter((item) => item.doctor_id === null || item.doctor_id === undefined);
  const doctorSummary = distResult?.doctor_stats || [];
  const resultSummary = distResult?.summary ?? distResult;
  const citoStats = distResult?.priority_breakdown?.cito;

  const filterAssignments = (items: Assignment[], includeDoctorFilter: boolean) => {
    let data = [...items];
    const q = search.trim().toLowerCase();

    if (q) {
      data = data.filter(
        (item) =>
          item.study_number?.toLowerCase().includes(q) ||
          item.doctor_name?.toLowerCase().includes(q) ||
          item.study_modality?.join(' ').toLowerCase().includes(q)
      );
    }

    if (priorityFilter !== 'all') {
      data = data.filter((item) => item.priority === priorityFilter);
    }

    if (includeDoctorFilter && selectedDoctorFilter !== 'all') {
      data = data.filter((item) => item.doctor_id === selectedDoctorFilter);
    }

    return data;
  };

  const filteredAssigned = useMemo(
    () => filterAssignments(assigned, true),
    [assigned, search, priorityFilter, selectedDoctorFilter]
  );
  const filteredUnassigned = useMemo(
    () => filterAssignments(unassigned, false),
    [unassigned, search, priorityFilter]
  );

  const totalAssignedPages = Math.max(1, Math.ceil(filteredAssigned.length / PAGE_SIZE));
  const totalUnassignedPages = Math.max(1, Math.ceil(filteredUnassigned.length / PAGE_SIZE));
  const assignedPageItems = filteredAssigned.slice((assignedPage - 1) * PAGE_SIZE, assignedPage * PAGE_SIZE);
  const unassignedPageItems = filteredUnassigned.slice(
    (unassignedPage - 1) * PAGE_SIZE,
    unassignedPage * PAGE_SIZE
  );

  const topDoctors = useMemo(
    () =>
      [...doctorSummary]
        .sort((a, b) => (b.load_percent || 0) - (a.load_percent || 0))
        .slice(0, 4),
    [doctorSummary]
  );

  const avgLoad = useMemo(() => {
    if (!doctorSummary.length) return 0;
    return doctorSummary.reduce((sum, item) => sum + (item.load_percent || 0), 0) / doctorSummary.length;
  }, [doctorSummary]);

  const assignedRate =
    resultSummary?.assignment_rate_percent ?? (assignments.length ? (assigned.length / assignments.length) * 100 : 0);
  const remainingOverdue = resultSummary?.overdue_remaining ?? resultSummary?.overdue_unassigned ?? 0;
  const overdueHoursRemaining = resultSummary?.queue_overdue_hours_remaining ?? 0;

  const tabs: { key: ConfirmTab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Сводка' },
    { key: 'assigned', label: 'Назначено', count: assigned.length },
    { key: 'unassigned', label: 'Осталось', count: unassigned.length },
    { key: 'doctors', label: 'Врачи', count: doctorSummary.length },
  ];

  const handleReassignChange = (assignment: Assignment, value: string) => {
    const doctorId = Number(value);
    if (!Number.isNaN(doctorId)) {
      onReassign(assignment, doctorId);
    }
  };

  const renderFilters = (showDoctorFilter: boolean) => (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div className="relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setAssignedPage(1);
            setUnassignedPage(1);
          }}
          placeholder="Поиск по исследованию, врачу или модальности"
          className="w-full rounded-lg border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
        />
      </div>

      <select
        value={priorityFilter}
        onChange={(event) => {
          setPriorityFilter(event.target.value as AssignmentFilter);
          setAssignedPage(1);
          setUnassignedPage(1);
        }}
        className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
      >
        <option value="all">Все приоритеты</option>
        <option value="cito">CITO</option>
        <option value="asap">Срочные</option>
        <option value="normal">Плановые</option>
      </select>

      <select
        value={showDoctorFilter ? selectedDoctorFilter : 'all'}
        onChange={(event) => {
          setSelectedDoctorFilter(event.target.value === 'all' ? 'all' : Number(event.target.value));
          setAssignedPage(1);
        }}
        disabled={!showDoctorFilter}
        className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100 disabled:opacity-60"
      >
        <option value="all">{showDoctorFilter ? 'Все врачи' : 'Врач не назначен'}</option>
        {showDoctorFilter &&
          doctors.map((doctor) => (
            <option key={doctor.id} value={doctor.id}>
              {doctor.fio_alias}
            </option>
          ))}
      </select>
    </div>
  );

  const renderAssignmentTable = (
    items: Assignment[],
    emptyText: string,
    page: number,
    setPage: (page: number) => void,
    totalPages: number
  ) => (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="max-h-[52vh] overflow-auto">
        <div className="min-w-[900px]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-50">
              <tr>
                <th className="px-3 py-3 text-left font-medium text-slate-600">Исследование</th>
                <th className="px-3 py-3 text-left font-medium text-slate-600">Модальность</th>
                <th className="px-3 py-3 text-left font-medium text-slate-600">Приоритет</th>
                <th className="px-3 py-3 text-left font-medium text-slate-600">Врач</th>
                <th className="px-3 py-3 text-left font-medium text-slate-600">УП</th>
                <th className="px-3 py-3 text-left font-medium text-slate-600">Действие</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                    {emptyText}
                  </td>
                </tr>
              ) : (
                items.map((assignment) => (
                  <tr key={`${assignment.study_number}-${assignment.doctor_id ?? 'none'}`} className="border-t border-slate-100">
                    <td className="px-3 py-3 font-medium text-slate-800">{assignment.study_number}</td>
                    <td className="px-3 py-3 text-slate-700">{assignment.study_modality?.join(', ') || '—'}</td>
                    <td className="px-3 py-3">
                      <span
                        className={`inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium ${getPriorityColor(
                          assignment.priority
                        )}`}
                      >
                        {getPriorityLabel(assignment.priority)}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-slate-700">{assignment.doctor_name || '—'}</td>
                    <td className="px-3 py-3 text-slate-700">{assignment.up_value ?? '—'}</td>
                    <td className="px-3 py-3">
                      <select
                        value={assignment.doctor_id ?? ''}
                        onChange={(event) => handleReassignChange(assignment, event.target.value)}
                        className="w-56 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        <option value="" disabled>
                          Выбрать врача
                        </option>
                        {doctors.map((doctor) => (
                          <option key={doctor.id} value={doctor.id}>
                            {doctor.fio_alias}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="px-4 py-3">
        <Pagination page={page} setPage={setPage} totalPages={totalPages} />
      </div>
    </div>
  );

  if (!isOpen || !distResult) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-950/50 p-0 md:items-center md:p-4">
      <div className="flex max-h-[95dvh] w-full flex-col overflow-hidden rounded-t-xl bg-white shadow-lg md:max-w-6xl md:rounded-lg">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4 md:px-6">
          <div>
            <h3 className="text-base font-bold text-slate-900 md:text-lg">Подтверждение распределения</h3>
            <p className="mt-0.5 text-xs text-slate-500 md:text-sm">Проверь назначения перед сохранением</p>
          </div>

          <button
            onClick={onCancel}
            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-4 pt-4 md:px-6">
          <div className="flex gap-2 overflow-x-auto pb-1">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition md:text-sm ${
                  activeTab === tab.key
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {tab.label}
                {typeof tab.count === 'number' && <span className="ml-2 opacity-80">({tab.count})</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
          {activeTab === 'summary' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <div className="rounded-lg border border-emerald-100 bg-emerald-50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-emerald-700">
                    <CheckCircle2 size={16} />
                    Назначено
                  </div>
                  <div className="text-2xl font-bold text-emerald-800">{assigned.length}</div>
                </div>

                <div className="rounded-lg border border-amber-100 bg-amber-50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-amber-700">
                    <FileWarning size={16} />
                    Не назначено
                  </div>
                  <div className="text-2xl font-bold text-amber-800">{unassigned.length}</div>
                </div>

                <div className="rounded-lg border border-red-100 bg-red-50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-red-700">
                    <AlertTriangle size={16} />
                    CITO
                  </div>
                  <div className="text-2xl font-bold text-red-800">
                    {citoStats?.assigned ?? resultSummary?.cito_assigned ?? 0} / {citoStats?.total ?? resultSummary?.cito_total ?? 0}
                  </div>
                </div>

                <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm font-medium text-blue-700">
                    <Clock size={16} />
                    Просрочка осталась
                  </div>
                  <div className="text-2xl font-bold text-blue-800">{remainingOverdue}</div>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <Users size={16} />
                    Самые загруженные врачи
                  </div>
                  <div className="space-y-3">
                    {topDoctors.map((doctor) => (
                      <div key={doctor.doctor_id}>
                        <div className="mb-1 flex items-center justify-between gap-3 text-xs">
                          <span className="truncate font-medium text-slate-700">{doctor.doctor_name}</span>
                          <span className="shrink-0 text-slate-500">
                            {doctor.assigned_studies} иссл. · {doctor.load_percent.toFixed(1)}%
                          </span>
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                          <div
                            className={`h-full rounded-full ${
                              doctor.load_percent > 80
                                ? 'bg-red-500'
                                : doctor.load_percent > 50
                                ? 'bg-amber-400'
                                : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(doctor.load_percent, 100)}%` }}
                          />
                        </div>
                      </div>
                    ))}
                    {topDoctors.length === 0 && <div className="text-sm text-slate-500">Нет данных по врачам.</div>}
                  </div>
                </div>

                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
                    <BarChart3 size={16} />
                    Общая сводка
                  </div>
                  <div className="space-y-2 text-sm text-slate-600">
                    <div>
                      Врачей задействовано: <strong>{doctorSummary.length}</strong>
                    </div>
                    <div>
                      Средняя загрузка: <strong>{avgLoad.toFixed(1)}%</strong>
                    </div>
                    <div>
                      Назначений всего: <strong>{assigned.length}</strong>
                    </div>
                    <div>
                      Без назначения: <strong>{unassigned.length}</strong>
                    </div>
                    <div>
                      Доля назначений: <strong>{assignedRate.toFixed(2)}%</strong>
                    </div>
                    <div>
                      Часов просрочки осталось: <strong>{overdueHoursRemaining.toFixed(2)}ч</strong>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <BarChart3 size={16} />
                  Детализация по срочности
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[760px] text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-slate-500">
                        <th className="py-2 pr-2">Тип</th>
                        <th className="py-2 pr-2">Всего</th>
                        <th className="py-2 pr-2">Доля</th>
                        <th className="py-2 pr-2">Назначено</th>
                        <th className="py-2">Часы просрочки</th>
                      </tr>
                    </thead>
                    <tbody>
                      {priorityRows.map((row) => {
                        const data = distResult.priority_breakdown?.[row.key];
                        return (
                          <tr key={row.key} className="border-b border-slate-100 text-slate-700">
                            <td className="py-2 pr-2 font-medium">{row.label}</td>
                            <td className="py-2 pr-2">{data?.total ?? 0}</td>
                            <td className="py-2 pr-2">{(data?.share_percent ?? 0).toFixed(2)}%</td>
                            <td className="py-2 pr-2">
                              {data?.assigned ?? 0} ({(data?.assigned_rate_percent ?? 0).toFixed(2)}%)
                            </td>
                            <td className="py-2">{(data?.scheduled_overdue_hours_assigned ?? 0).toFixed(2)}ч</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'assigned' && (
            <div className="space-y-4">
              {renderFilters(true)}
              {renderAssignmentTable(
                assignedPageItems,
                'Нет назначенных исследований',
                assignedPage,
                setAssignedPage,
                totalAssignedPages
              )}
            </div>
          )}

          {activeTab === 'unassigned' && (
            <div className="space-y-4">
              {renderFilters(false)}
              {renderAssignmentTable(
                unassignedPageItems,
                'Все исследования распределены',
                unassignedPage,
                setUnassignedPage,
                totalUnassignedPages
              )}
            </div>
          )}

          {activeTab === 'doctors' && (
            <div className="overflow-hidden rounded-lg border border-slate-200">
              <div className="max-h-[60vh] overflow-auto">
                <div className="min-w-[680px]">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-slate-50">
                      <tr>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">Врач</th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">Исследований</th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">УП</th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">Лимит</th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">Загрузка</th>
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
                            <td className="px-3 py-3 font-medium text-slate-800">{doctor.doctor_name}</td>
                            <td className="px-3 py-3 text-slate-600">{doctor.assigned_studies}</td>
                            <td className="px-3 py-3 text-slate-600">{doctor.total_up}</td>
                            <td className="px-3 py-3 text-slate-600">{doctor.max_up}</td>
                            <td className="px-3 py-3">
                              <div className="flex items-center gap-2">
                                <div className="h-2 w-28 overflow-hidden rounded-full bg-slate-100">
                                  <div
                                    className={`h-full rounded-full ${
                                      doctor.load_percent > 80
                                        ? 'bg-red-500'
                                        : doctor.load_percent > 50
                                        ? 'bg-amber-400'
                                        : 'bg-emerald-500'
                                    }`}
                                    style={{ width: `${Math.min(doctor.load_percent, 100)}%` }}
                                  />
                                </div>
                                <span className="text-xs text-slate-600">{doctor.load_percent.toFixed(1)}%</span>
                              </div>
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-slate-200 px-4 py-4 md:px-6 sm:flex-row sm:justify-end">
          <button
            onClick={onCancel}
            className="inline-flex w-full items-center justify-center rounded-lg border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 sm:w-auto"
          >
            Отмена
          </button>

          <button
            onClick={onConfirm}
            disabled={confirming}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            {confirming ? 'Сохраняем...' : 'Подтвердить распределение'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDistributionModal;
