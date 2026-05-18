import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileWarning,
  Search,
  Users,
  X,
  Clock,
  BarChart3,
} from 'lucide-react';
import type { DoctorWithLoad, Assignment, DistResult } from '../../../types';
import type {
  ConfirmTab,
  AssignmentFilter,
} from '../utils/distributionConstants';
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

  useEffect(() => {
    if (isOpen) {
      setActiveTab('summary');
      setAssignedPage(1);
      setSearch('');
      setPriorityFilter('all');
      setSelectedDoctorFilter('all');
    }
  }, [isOpen, distResult?.distribution_id]);

  const assignments = distResult?.assignments || [];
  const assigned = assignments.filter(
  (item) => item.doctor_id !== null && item.doctor_id !== undefined
);
  const unassignedAssignments = assignments.filter(
  (item) => item.doctor_id === null || item.doctor_id === undefined
);
  const doctorSummary = distResult?.doctor_stats || [];

  const filteredAssigned = useMemo(() => {
    let data = [...assigned];

    const q = search.trim().toLowerCase();
    if (q) {
      data = data.filter(
        (item) =>
          item.study_number?.toLowerCase().includes(q) ||
          item.doctor_name?.toLowerCase().includes(q)
      );
    }

    if (priorityFilter !== 'all') {
      data = data.filter((item) => item.priority === priorityFilter);
    }

    if (selectedDoctorFilter !== 'all') {
      data = data.filter((item) => item.doctor_id === selectedDoctorFilter);
    }

    return data;
  }, [assigned, search, priorityFilter, selectedDoctorFilter]);

  const totalAssignedPages = Math.max(1, Math.ceil(filteredAssigned.length / PAGE_SIZE));
  const assignedStart = (assignedPage - 1) * PAGE_SIZE;
  const assignedPageItems = filteredAssigned.slice(
    assignedStart,
    assignedStart + PAGE_SIZE
  );

  const topDoctors = useMemo(
    () =>
      [...doctorSummary]
        .sort((a, b) => (b.load_percent || 0) - (a.load_percent || 0))
        .slice(0, 5),
    [doctorSummary]
  );

  const avgLoad = useMemo(() => {
    if (!doctorSummary.length) return 0;
    return (
      doctorSummary.reduce((sum, item) => sum + (item.load_percent || 0), 0) /
      doctorSummary.length
    );
  }, [doctorSummary]);

  const priorityBreakdownRows = useMemo(
    () => [
      { key: 'plan', label: 'Плановые', data: distResult?.priority_breakdown?.plan },
      { key: 'asap', label: 'Срочные', data: distResult?.priority_breakdown?.asap },
      { key: 'cito', label: 'CITO', data: distResult?.priority_breakdown?.cito },
    ],
    [distResult?.priority_breakdown]
  );
  const resultSummary = distResult?.summary ?? distResult;
  const citoStats = distResult?.priority_breakdown?.cito;
  const assignedRate = resultSummary?.assignment_rate_percent ?? (
    assignments.length ? (assigned.length / assignments.length) * 100 : 0
  );
  const overdueClearedPercent =
    resultSummary?.queue_overdue_hours_cleared_percent ??
    resultSummary?.overdue_cleared_percent ??
    0;
  const remainingOverdue =
    resultSummary?.overdue_remaining ?? resultSummary?.overdue_unassigned ?? 0;

  const handleReassignChange = (assignment: Assignment, value: string) => {
    const doctorId = Number(value);
    if (!Number.isNaN(doctorId)) {
      onReassign(assignment, doctorId);
    }
  };

  const tabs: { key: ConfirmTab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Итог решения' },
    { key: 'assigned', label: 'Назначено', count: assigned.length },
    { key: 'unassigned', label: 'Осталось', count: unassignedAssignments.length },
    { key: 'doctors', label: 'Нагрузка врачей', count: doctorSummary.length },
  ];

  if (!isOpen || !distResult) return null;

  return (
    <div className="fixed inset-0 z-[80] flex items-end justify-center bg-slate-950/50 p-0 backdrop-blur-sm md:items-center md:p-4">
      <div className="flex max-h-[95dvh] w-full flex-col overflow-hidden rounded-t-3xl bg-white shadow-2xl md:max-w-6xl md:rounded-3xl">
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-4 md:px-6">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              Предпросмотр распределения
            </h3>
            <p className="text-sm text-slate-500 mt-0.5">
              Проверь результат расчёта перед сохранением назначений
            </p>
          </div>

          <button
            onClick={onCancel}
            className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </div>

        <div className="px-4 pt-4 md:px-6">
          <div className="flex gap-2 overflow-x-auto border-b border-slate-200 pb-4">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`shrink-0 rounded-xl px-3 py-2 text-sm font-semibold transition ${
                  activeTab === tab.key
                    ? 'bg-blue-600 text-white shadow-sm shadow-blue-200'
                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                }`}
              >
                {tab.label}
                {typeof tab.count === 'number' && (
                  <span className="ml-2 opacity-80">({tab.count})</span>
                )}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-4 md:p-6">
          {activeTab === 'summary' && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <div className="rounded-2xl border border-blue-100 bg-blue-50 p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-blue-700 mb-2">
                    <CheckCircle2 size={18} />
                    <span className="font-medium">Назначено</span>
                  </div>
                  <div className="text-2xl font-bold text-blue-800">
                    {distResult.assigned ?? assigned.length}
                  </div>
                </div>

                <div className="rounded-2xl border border-amber-100 bg-amber-50 p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-amber-700 mb-2">
                    <FileWarning size={18} />
                    <span className="font-medium">Не назначено</span>
                  </div>
                  <div className="text-2xl font-bold text-amber-800">
                    {distResult.unassigned ?? unassignedAssignments.length}
                  </div>
                </div>

                <div className="rounded-2xl border border-amber-100 bg-amber-50 p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-amber-700 mb-2">
                    <AlertTriangle size={18} />
                    <span className="font-medium">CITO</span>
                  </div>
                  <div className="text-2xl font-bold text-amber-800">
                    {citoStats?.assigned ?? resultSummary?.cito_assigned ?? 0} / {citoStats?.total ?? resultSummary?.cito_total ?? 0}
                  </div>
                </div>

                <div className="rounded-2xl border border-blue-100 bg-blue-50 p-3 sm:p-4">
                  <div className="flex items-center gap-2 text-blue-700 mb-2">
                    <Clock size={18} />
                    <span className="font-medium">Осталось просрочки</span>
                  </div>
                  <div className="text-2xl font-bold text-blue-800">
                    {remainingOverdue}
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
                <div className="mb-2 flex items-center gap-2 font-semibold">
                  <CheckCircle2 size={18} />
                  Пояснение решения
                </div>
                <p className="leading-6">
                  Алгоритм назначил <strong>{assigned.length}</strong> исследований из{' '}
                  <strong>{assignments.length}</strong> ({assignedRate.toFixed(1)}%).
                  Срочных CITO закрыто <strong>{citoStats?.assigned ?? resultSummary?.cito_assigned ?? 0}</strong> из{' '}
                  <strong>{citoStats?.total ?? resultSummary?.cito_total ?? 0}</strong>.
                  Просроченных исследований после расчёта остаётся <strong>{remainingOverdue}</strong>,
                  закрыто <strong>{overdueClearedPercent.toFixed(1)}%</strong> часов просрочки в очереди.
                </p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
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
                              {doctor.assigned_studies} иссл. ·{' '}
                              {doctor.load_percent.toFixed(1)}%
                            </span>
                          </div>
                          <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                            <div
                              className={`h-full rounded-full ${
                                doctor.load_percent > 80
                                  ? 'bg-amber-500'
                                  : doctor.load_percent > 50
                                  ? 'bg-amber-400'
                                  : 'bg-blue-500'
                              }`}
                              style={{ width: `${Math.min(doctor.load_percent, 100)}%` }}
                            />
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center gap-2 text-slate-800 font-medium mb-3">
                    <BarChart3 size={18} />
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
                      Без назначения: <strong>{unassignedAssignments.length}</strong>
                    </div>
                     <div>
                      Доля назначений: <strong>{assignedRate.toFixed(2)}%</strong>
                    </div>
                    <div>
                      Просроченных было:{' '}
                      <strong>
                        {resultSummary?.overdue_total ?? 0} ({(resultSummary?.overdue_rate_percent ?? 0).toFixed(2)}% от очереди)
                      </strong>
                    </div>
                    <div>
                      Часов просрочки в очереди:{' '}
                      <strong>{(resultSummary?.queue_overdue_hours_total ?? 0).toFixed(2)}ч</strong>
                    </div>
                    <div>
                      Просроченных назначено:{' '}
                      <strong>{resultSummary?.overdue_assigned ?? 0}</strong>
                    </div>
                    <div>
                      Назначено часов просрочки:{' '}
                      <strong>{(resultSummary?.queue_overdue_hours_assigned ?? 0).toFixed(2)}ч</strong>
                    </div>
                    <div>
                      Просроченных осталось:{' '}
                      <strong>{remainingOverdue}</strong>
                    </div>
                    <div>
                      Осталось часов просрочки:{' '}
                      <strong>{(resultSummary?.queue_overdue_hours_remaining ?? 0).toFixed(2)}ч</strong>
                    </div>
                    <div>
                      Просрочка закрыта:{' '}
                      <strong>
                        {resultSummary?.overdue_cleared ?? resultSummary?.overdue_assigned ?? 0} иссл. / {(resultSummary?.queue_overdue_hours_assigned ?? 0).toFixed(2)}ч ({overdueClearedPercent.toFixed(2)}%)
                      </strong>
                    </div>
                    <div>
                      Завершатся с просрочкой:{' '}
                      <strong>
                        {resultSummary?.scheduled_overdue_total ?? 0} иссл. / {(resultSummary?.scheduled_overdue_hours_total ?? 0).toFixed(2)}ч
                      </strong>
                    </div>
                    <div>
                      Назначено с просрочкой:{' '}
                      <strong>
                        {resultSummary?.scheduled_overdue_assigned ?? 0} иссл. / {(resultSummary?.scheduled_overdue_hours_assigned ?? 0).toFixed(2)}ч
                      </strong>
                    </div>
                  </div>
                </div>
              </div>
              
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center gap-2 text-slate-800 font-medium mb-3">
                  <BarChart3 size={18} />
                  Детализация по срочности
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[980px] text-sm">
                    <thead>
                      <tr className="text-left text-slate-500 border-b border-slate-200">
                        <th className="py-2 pr-2">Тип</th>
                        <th className="py-2 pr-2">Всего</th>
                        <th className="py-2 pr-2">Доля</th>
                        <th className="py-2 pr-2">Назначено</th>
                        <th className="py-2 pr-2">Просрочено до расчёта</th>
                        <th className="py-2 pr-2">Будет с просрочкой</th>
                        <th className="py-2 pr-2">Назначено с просрочкой</th>
                        <th className="py-2 pr-2">Часы у назначенных</th>
                        <th className="py-2 pr-2">Осталось с просрочкой</th>
                        <th className="py-2">Часы у оставшихся</th>
                      </tr>
                    </thead>
                    <tbody>
                      {priorityBreakdownRows.map((row) => (
                        <tr key={row.key} className="border-b border-slate-100 text-slate-700">
                          <td className="py-2 pr-2 font-medium">{row.label}</td>
                          <td className="py-2 pr-2">{row.data?.total ?? 0}</td>
                          <td className="py-2 pr-2">{(row.data?.share_percent ?? 0).toFixed(2)}%</td>
                          <td className="py-2 pr-2">
                            {row.data?.assigned ?? 0} ({(row.data?.assigned_rate_percent ?? 0).toFixed(2)}%)
                          </td>
                          <td className="py-2 pr-2">
                            {row.data?.overdue_total ?? 0} / {row.data?.total ?? 0} ({(row.data?.overdue_rate_percent ?? 0).toFixed(2)}%)
                          </td>
                          <td className="py-2 pr-2">
                            {row.data?.scheduled_overdue_total ?? 0}
                          </td>
                          <td className="py-2 pr-2">
                            {row.data?.scheduled_overdue_assigned ?? 0}
                          </td>
                          <td className="py-2 pr-2">
                            {(row.data?.scheduled_overdue_hours_assigned ?? 0).toFixed(2)}ч
                          </td>
                          <td className="py-2 pr-2">
                            {row.data?.scheduled_overdue_unassigned ?? 0}
                          </td>
                          <td className="py-2">
                            {(row.data?.scheduled_overdue_hours_unassigned ?? 0).toFixed(2)}ч
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
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
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setAssignedPage(1);
                    }}
                    placeholder="Поиск по исследованию или врачу"
                    className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-9 pr-3 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                  />
                </div>

                <select
                  value={priorityFilter}
                  onChange={(e) => {
                    setPriorityFilter(e.target.value as AssignmentFilter);
                    setAssignedPage(1);
                  }}
                  className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
                  <option value="all">Все приоритеты</option>
                  <option value="cito">CITO</option>
                  <option value="asap">Срочные</option>
                  <option value="normal">Обычные</option>
                </select>

                <select
                  value={selectedDoctorFilter}
                  onChange={(e) => {
                    setSelectedDoctorFilter(
                      e.target.value === 'all' ? 'all' : Number(e.target.value)
                    );
                    setAssignedPage(1);
                  }}
                  className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm outline-none transition focus:border-blue-400 focus:bg-white focus:ring-4 focus:ring-blue-100"
                >
                  <option value="all">Все врачи</option>
                  {doctors.map((doctor) => (
                    <option key={doctor.id} value={doctor.id}>
                      {doctor.fio_alias}
                    </option>
                  ))}
                </select>
              </div>

              <div className="overflow-hidden rounded-2xl border border-slate-200">
                <div className="max-h-[52vh] overflow-auto"><div className="min-w-[860px]">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 sticky top-0">
                      <tr>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Исследование
                        </th>
                        <th className="px-3 py-3 text-left font-medium text-slate-600">
                          Модальность
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
                          Действие
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignedPageItems.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                            Нет назначенных исследований
                          </td>
                        </tr>
                      ) : (
                        assignedPageItems.map((assignment) => (
                          <tr
                            key={`${assignment.study_number}-${assignment.doctor_id}`}
                            className="border-t border-slate-100"
                          >
                            <td className="px-3 py-3 font-medium text-slate-800">
                              {assignment.study_number}
                            </td>
                            <td className="px-3 py-3 text-slate-700">
                              {assignment.study_modality}
                            </td>
                            <td className="px-3 py-3">
                              <span
                                className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${getPriorityColor(
                                  assignment.priority
                                )}`}
                              >
                                {getPriorityLabel(assignment.priority)}
                              </span>
                            </td>
                            <td className="px-3 py-3 text-slate-700">
                              {assignment.doctor_name || '—'}
                            </td>
                            <td className="px-3 py-3 text-slate-700">
                              {assignment.up_value ?? '—'}
                            </td>
                            <td className="px-3 py-3">
                              <select
                                value={assignment.doctor_id ?? ''}
                                onChange={(e) =>
                                  handleReassignChange(assignment, e.target.value)
                                }
                                className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                              >
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
                </div></div>

                <div className="px-4 pb-3 pt-3">
                  <Pagination
                    page={assignedPage}
                    setPage={setAssignedPage}
                    totalPages={totalAssignedPages}
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === 'unassigned' && (
            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <div className="max-h-[60vh] overflow-auto"><div className="min-w-[680px]">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        Исследование
                      </th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        Модальность
                      </th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        Приоритет
                      </th>
                      <th className="px-3 py-3 text-left font-medium text-slate-600">
                        УП
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {unassignedAssignments.length === 0 ? (
                      <tr>
                        <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                          Все исследования распределены
                        </td>
                      </tr>
                    ) : (
                      unassignedAssignments.map((assignment) => (
                        <tr
                          key={assignment.study_number}
                          className="border-t border-slate-100"
                        >
                          <td className="px-3 py-3 font-medium text-slate-800">
                            {assignment.study_number}
                          </td>
                          <td className="px-3 py-3 text-slate-700">
                            {assignment.study_modality}
                          </td>
                          <td className="px-3 py-3">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border ${getPriorityColor(
                                assignment.priority
                              )}`}
                            >
                              {getPriorityLabel(assignment.priority)}
                            </span>
                          </td>
                          <td className="px-3 py-3 text-slate-600">
                            {assignment.up_value ?? '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div></div>
            </div>
          )}

          {activeTab === 'doctors' && (
            <div className="overflow-hidden rounded-2xl border border-slate-200">
              <div className="max-h-[60vh] overflow-auto"><div className="min-w-[680px]">
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
                                      ? 'bg-amber-500'
                                      : doctor.load_percent > 50
                                      ? 'bg-amber-400'
                                      : 'bg-blue-500'
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
              </div></div>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 px-4 py-4 md:px-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          <button
            onClick={onCancel}
            className="inline-flex w-full items-center justify-center rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 sm:w-auto"
          >
            Отмена
          </button>

          <button
            onClick={onConfirm}
            disabled={confirming}
            className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-blue-200 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
          >
            {confirming ? 'Сохраняем...' : 'Сохранить назначения'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDistributionModal;
