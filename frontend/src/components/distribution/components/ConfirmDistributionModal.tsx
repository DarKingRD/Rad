import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Edit2,
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

const ConfirmDistributionModal: React.FC<ConfirmDistributionModalProps> = ({
  isOpen,
  distResult,
  doctors,
  onConfirm,
  onCancel,
  onReassign,
  confirming,
}) => {
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
  const assigned = assignments.filter((item) => item.doctor_id);
  const unassignedAssignments = assignments.filter((item) => !item.doctor_id);
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

  const handleReassignChange = (assignment: Assignment, value: string) => {
    const doctorId = Number(value);
    if (!Number.isNaN(doctorId)) {
      onReassign(assignment, doctorId);
    }
  };

  const tabs: { key: ConfirmTab; label: string; count?: number }[] = [
    { key: 'summary', label: 'Сводка' },
    { key: 'assigned', label: 'Назначенные', count: assigned.length },
    { key: 'unassigned', label: 'Неназначенные', count: unassignedAssignments.length },
    { key: 'doctors', label: 'Врачи', count: doctorSummary.length },
  ];

  if (!isOpen || !distResult) return null;

  return (
    <div className="fixed inset-0 z-[80] bg-black/50 flex items-end md:items-center justify-center p-0 md:p-4">
      <div className="bg-white w-full md:max-w-6xl md:rounded-2xl shadow-2xl max-h-[95vh] overflow-hidden rounded-t-2xl md:rounded-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 md:px-6 py-4">
          <div>
            <h3 className="text-lg font-bold text-slate-900">
              Подтверждение распределения
            </h3>
            <p className="text-sm text-slate-500 mt-0.5">
              Проверь назначения перед сохранением
            </p>
          </div>

          <button
            onClick={onCancel}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700"
          >
            <X size={20} />
          </button>
        </div>

        <div className="px-4 md:px-6 pt-4">
          <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-4">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition ${
                  activeTab === tab.key
                    ? 'bg-blue-600 text-white'
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

        <div className="p-4 md:p-6 overflow-y-auto max-h-[calc(95vh-170px)] space-y-4">
          {activeTab === 'summary' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="border rounded-xl p-4 bg-green-50">
                  <div className="flex items-center gap-2 text-green-700 mb-2">
                    <CheckCircle2 size={18} />
                    <span className="font-medium">Назначено</span>
                  </div>
                  <div className="text-2xl font-bold text-green-800">
                    {distResult.assigned ?? assigned.length}
                  </div>
                </div>

                <div className="border rounded-xl p-4 bg-amber-50">
                  <div className="flex items-center gap-2 text-amber-700 mb-2">
                    <FileWarning size={18} />
                    <span className="font-medium">Не назначено</span>
                  </div>
                  <div className="text-2xl font-bold text-amber-800">
                    {distResult.unassigned ?? unassignedAssignments.length}
                  </div>
                </div>

                <div className="border rounded-xl p-4 bg-red-50">
                  <div className="flex items-center gap-2 text-red-700 mb-2">
                    <AlertTriangle size={18} />
                    <span className="font-medium">CITO</span>
                  </div>
                  <div className="text-2xl font-bold text-red-800">
                    {distResult.cito_assigned ?? 0} / {distResult.cito_total ?? 0}
                  </div>
                </div>

                <div className="border rounded-xl p-4 bg-blue-50">
                  <div className="flex items-center gap-2 text-blue-700 mb-2">
                    <Clock size={18} />
                    <span className="font-medium">Средняя просрочка</span>
                  </div>
                  <div className="text-2xl font-bold text-blue-800">
                    {distResult.avg_tardiness ?? 0} ч
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
                              {doctor.assigned_studies} иссл. ·{' '}
                              {doctor.load_percent.toFixed(1)}%
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

                <div className="border rounded-xl p-4">
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
                  </div>
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
                    className="w-full border border-slate-300 rounded-lg pl-9 pr-3 py-2 text-sm"
                  />
                </div>

                <select
                  value={priorityFilter}
                  onChange={(e) => {
                    setPriorityFilter(e.target.value as AssignmentFilter);
                    setAssignedPage(1);
                  }}
                  className="border border-slate-300 rounded-lg px-3 py-2 text-sm"
                >
                  <option value="all">Все приоритеты</option>
                  <option value="cito">CITO</option>
                  <option value="asap">ASAP</option>
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
                          Действие
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignedPageItems.length === 0 ? (
                        <tr>
                          <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
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
                                className="border border-slate-300 rounded-lg px-2 py-1 text-xs"
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
                </div>

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
            <div className="border rounded-xl overflow-hidden">
              <div className="max-h-[60vh] overflow-auto">
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
                        УП
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {unassignedAssignments.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-4 py-8 text-center text-slate-500">
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
        </div>

        <div className="border-t border-slate-200 px-4 md:px-6 py-4 flex flex-col sm:flex-row gap-3 sm:justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50"
          >
            Отмена
          </button>

          <button
            onClick={onConfirm}
            disabled={confirming}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
          >
            {confirming ? 'Сохраняем...' : 'Подтвердить распределение'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmDistributionModal;