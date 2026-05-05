import { useEffect, useMemo, useState } from 'react';
import {
  Archive,
  Calendar,
  Eye,
  Filter,
  Loader2,
  UserCheck,
  Zap,
} from 'lucide-react';
import { distributionApi, doctorsApi, studiesApi, studyTypesApi } from '../../services/api';
import type {
  Assignment,
  DistResult,
  DistributionDraft,
  DoctorDistStat,
  DoctorWithLoad,
  DistributionInfo,
  DistributionObjective,
  Study,
  StudyType,
} from '../../types';

import DoctorCard from './components/DoctorCard';
import Pagination from './components/Pagination';
import ConfirmDistributionModal from './components/ConfirmDistributionModal';
import DraftsModal from './components/DraftsModal';

import { useDistributionDrafts } from './hooks/useDistributionDrafts';
import { useDoctorStudies } from './hooks/useDoctorStudies';

import {
  DOCTORS_PER_PAGE,
  ITEMS_PER_PAGE,
  PRIORITY_ORDER,
  type MobileTab,
} from './utils/distributionConstants';
import { getPriorityColor, getPriorityLabel, getTodayString } from './utils/distributionFormatters';

const OBJECTIVE_OPTIONS: Array<{ value: DistributionObjective; label: string }> = [
  {
    value: 'weighted_tardiness_lexicographic',
    label: 'Взвешенная просрочка',
  },
  {
    value: 'tardiness_lexicographic',
    label: 'Обычная просрочка',
  },
  {
    value: 'priority_tier_tardiness_multipass',
    label: 'CITO → ASAP → normal',
  },
  {
    value: 'max_assignments',
    label: 'Максимум назначений',
  },
];

const CurrentDistributionView = () => {
  const formatModalityOptionLabel = (value: string) =>
    value.length > 28 ? `${value.slice(0, 28)}...` : value;
  const [studiesTotal, setStudiesTotal] = useState(0);
  const [studies, setStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
  const [studyTypes, setStudyTypes] = useState<StudyType[]>([]);
  const [loading, setLoading] = useState(true);
  const [studiesLoading, setStudiesLoading] = useState(false);
  const [distributing, setDistributing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedStudy, setSelectedStudy] = useState<Study | null>(null);
  const [selectedDoctor, setSelectedDoctor] = useState<number | null>(null);

  const [distInfo, setDistInfo] = useState<DistributionInfo | null>(null);
  const [distResult, setDistResult] = useState<DistResult | null>(null);

  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [showDrafts, setShowDrafts] = useState(false);

  const [distributionDate, setDistributionDate] = useState(getTodayString());
  const [distributionDateFrom, setDistributionDateFrom] = useState('');
  const [distributionDateTo, setDistributionDateTo] = useState('');
  const [useMip, setUseMip] = useState(true);
  const [objective, setObjective] = useState<DistributionObjective>('weighted_tardiness_lexicographic');

  const [mobileTab, setMobileTab] = useState<MobileTab>('studies');
  const [currentPage, setCurrentPage] = useState(1);
  const [doctorPage, setDoctorPage] = useState(1);
  const [priorityFilter, setPriorityFilter] = useState<'all' | 'cito' | 'asap' | 'normal'>('all');
  const [createdFromFilter, setCreatedFromFilter] = useState('');
  const [createdToFilter, setCreatedToFilter] = useState('');
  const [modalityFilter, setModalityFilter] = useState('');

  const { drafts, loadDrafts, persistDraft, removeDraft } = useDistributionDrafts();
  const { expandedDoctor, doctorStudies, handleToggleExpand } = useDoctorStudies();

  const totalPages = Math.max(1, Math.ceil(studiesTotal / ITEMS_PER_PAGE));
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

  const loadStudies = async () => {
    setStudiesLoading(true);
    setError(null);

    try {
      const pendingData = await studiesApi.getPending(currentPage, ITEMS_PER_PAGE, {
        ...(priorityFilter !== 'all' ? { priority: priorityFilter } : {}),
        ...(createdFromFilter ? { date_from: createdFromFilter } : {}),
        ...(createdToFilter ? { date_to: createdToFilter } : {}),
        ...(modalityFilter ? { modality: modalityFilter } : {}),
      });
      const pendingResults = pendingData.results || [];

      const sortedStudies = [...pendingResults].sort((a, b) => {
        const priorityDiff =
          (PRIORITY_ORDER[a.priority] || 999) - (PRIORITY_ORDER[b.priority] || 999);

        if (priorityDiff !== 0) return priorityDiff;

        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      });

      setStudies(sortedStudies);
      setStudiesTotal(pendingData.total || pendingResults.length);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Ошибка загрузки исследований';
      setError(message);
    } finally {
      setStudiesLoading(false);
    }
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const [doctorsData, infoData, studyTypesData] = await Promise.all([
        doctorsApi.getWithLoad(),
        distributionApi.getInfo(),
        studyTypesApi.getAll(),
      ]);

      setDoctors(doctorsData || []);
      setDistInfo(infoData || null);
      setStudyTypes(studyTypesData || []);
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
  }, [currentPage, priorityFilter, createdFromFilter, createdToFilter, modalityFilter]);

  useEffect(() => {
    setCurrentPage(1);
  }, [priorityFilter, createdFromFilter, createdToFilter, modalityFilter]);

  const handleSelectForAssign = (doctorId: number) => {
    setSelectedDoctor((prev) => (prev === doctorId ? null : doctorId));
  };

  const handleAssign = async () => {
    if (!selectedStudy || !selectedDoctor) return;

    try {
      await studiesApi.assign(selectedStudy.research_number, selectedDoctor);
      setSelectedStudy(null);
      setSelectedDoctor(null);
      await loadStudies();
      await loadData();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Ошибка назначения исследования';
      setError(message);
    }
  };

  const handleRunDistribution = async () => {
    setDistributing(true);
    setError(null);

    try {
      const result = await distributionApi.preview({
        date: distributionDate,
        preview: true,
        date_from: distributionDateFrom || undefined,
        date_to: distributionDateTo || undefined,
        use_mip: useMip,
        objective,
      });

      setDistResult(result);
      persistDraft(result);
      setShowConfirmModal(true);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Ошибка запуска распределения';
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
      const message =
        err instanceof Error ? err.message : 'Ошибка подтверждения распределения';
      setError(message);
    } finally {
      setConfirming(false);
    }
  };

  const handleReassign = (assignment: Assignment, newDoctorId: number) => {
    if (!distResult) return;

    const nextAssignments = (distResult.assignments || []).map((item) =>
      item.study_number === assignment.study_number
        ? {
            ...item,
            doctor_id: newDoctorId,
            doctor_name:
              doctors.find((doctor) => doctor.id === newDoctorId)?.fio_alias ||
              item.doctor_name,
          }
        : item
    );

    setDistResult({
      ...distResult,
      assignments: nextAssignments,
    });
  };

  const openDraft = (draft: DistributionDraft) => {
    setDistResult(draft);
    setShowDrafts(false);
    setShowConfirmModal(true);
  };

  const selectedDoctorObject = doctors.find((doctor) => doctor.id === selectedDoctor);
  const modalityOptions = useMemo(
    () =>
      Array.from(
        new Set(
          studyTypes
            .map((studyType) => studyType.name?.trim())
            .filter((value): value is string => Boolean(value))
        )
      ).sort((a, b) => a.localeCompare(b, 'ru')),
    [studyTypes]
  );
  return (
    <div className="space-y-5 md:space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-950">
            Текущее распределение
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">
            Выбери исследование, врача и выполни ручное или автоматическое распределение
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowDrafts(true)}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50"
          >
            <Archive size={16} />
            Черновики
            {drafts.length > 0 && (
              <span className="inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-slate-200 text-xs font-medium">
                {drafts.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 md:gap-4">
        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 md:p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-600">
              <UserCheck size={22} />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Доступно врачей</div>
              <div className="text-2xl font-bold tracking-tight text-slate-950">
                {loading ? '—' : distInfo?.available_doctors ?? doctors.length}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 md:p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-amber-50 text-amber-600">
              <Filter size={22} />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ожидают назначения</div>
              <div className="text-2xl font-bold tracking-tight text-slate-950">
                {studiesLoading ? '—' : studiesTotal}
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 md:p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
              <Calendar size={22} />
            </div>
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Дата распределения</div>
              <div className="text-2xl font-bold tracking-tight text-slate-950">
                {distributionDate}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-4 shadow-sm shadow-slate-200/60 md:p-5">
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_auto_240px_auto] xl:items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Дата распределения
              </label>
              <input
                type="date"
                value={distributionDate}
                onChange={(e) => setDistributionDate(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>

            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Период от
              </label>
              <input
                type="date"
                value={distributionDateFrom}
                onChange={(e) => setDistributionDateFrom(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>

            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Период до
              </label>
              <input
                type="date"
                value={distributionDateTo}
                onChange={(e) => setDistributionDateTo(e.target.value)}
                className="w-full rounded-xl border border-slate-300 px-3 py-2.5 text-sm transition focus:border-blue-500 focus:outline-none focus:ring-4 focus:ring-blue-100"
              />
            </div>

            <label className="inline-flex h-[42px] items-center gap-2 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm xl:mb-0">
              <input
                type="checkbox"
                checked={useMip}
                onChange={(e) => setUseMip(e.target.checked)}
              />
              <span className="text-sm font-medium text-slate-700">MIP</span>
            </label>

            <div className="min-w-0">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Objective
              </label>
              <select
                value={objective}
                onChange={(e) => setObjective(e.target.value as DistributionObjective)}
                className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
              >
                {OBJECTIVE_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <button
              onClick={handleRunDistribution}
              disabled={distributing}
              className="inline-flex h-[42px] items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm shadow-blue-600/20 transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60 sm:col-span-2 xl:col-span-1"
            >
              {distributing ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Распределяем...
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Запустить preview
                </>
              )}
            </button>
          </div>

          {selectedStudy && (
            <div className="flex flex-col gap-3 rounded-2xl border border-blue-200 bg-blue-50 px-4 py-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-sm text-blue-700">Выбрано исследование</div>
                <div className="font-medium text-blue-900">
                  {selectedStudy.research_number}
                </div>
                <div className="text-xs text-blue-700 mt-1">
                  {selectedStudy.study_type?.name || 'Тип не указан'}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {selectedDoctorObject && (
                  <div className="text-sm text-slate-700">
                    Врач: <span className="font-medium">{selectedDoctorObject.fio_alias}</span>
                  </div>
                )}

                <button
                  onClick={handleAssign}
                  disabled={!selectedDoctor}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Eye size={16} />
                  Назначить вручную
                </button>

                <button
                  onClick={() => {
                    setSelectedStudy(null);
                    setSelectedDoctor(null);
                  }}
                  className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Сбросить
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="sticky top-2 z-20 flex rounded-2xl border border-slate-200 bg-white/95 p-1 shadow-sm backdrop-blur lg:hidden">
        <button
          onClick={() => setMobileTab('studies')}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium ${
            mobileTab === 'studies'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          Исследования
        </button>
        <button
          onClick={() => setMobileTab('doctors')}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium ${
            mobileTab === 'doctors'
              ? 'bg-blue-600 text-white shadow-sm'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          Врачи
        </button>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <div
          className={`xl:col-span-5 space-y-4 ${
            mobileTab !== 'studies' ? 'hidden lg:block' : ''
          }`}
        >
          <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm shadow-slate-200/60">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4 md:px-5">
              <div>
                <h3 className="font-semibold text-slate-950">
                  Ожидающие исследования
                </h3>
                <p className="mt-0.5 text-sm text-slate-500">
                  Выбери исследование для ручного назначения
                </p>
              </div>

              {studiesLoading && <Loader2 size={18} className="animate-spin text-slate-400" />}
            </div>

            <div className="max-h-[calc(100dvh-300px)] divide-y divide-slate-100 overflow-y-auto xl:max-h-[720px]">
              <div className="border-b border-slate-100 bg-slate-50/80 px-4 py-4 md:px-5">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <select
                    value={priorityFilter}
                    onChange={(e) => setPriorityFilter(e.target.value as typeof priorityFilter)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
                  >
                    <option value="all">Все приоритеты</option>
                    <option value="cito">CITO</option>
                    <option value="asap">ASAP</option>
                    <option value="normal">Плановые</option>
                  </select>
                  <select
                    value={modalityFilter}
                    onChange={(e) => setModalityFilter(e.target.value)}
                    className="min-w-0 max-w-full overflow-hidden text-ellipsis whitespace-nowrap rounded-xl border border-slate-300 bg-white px-3 py-2.5 pr-8 text-sm"
                  >
                    <option value="">Все модальности</option>
                    {modalityOptions.map((modality) => (
                      <option key={modality} value={modality} title={modality}>
                        {formatModalityOptionLabel(modality)}
                      </option>
                    ))}
                  </select>
                  <input
                    type="date"
                    value={createdFromFilter}
                    onChange={(e) => setCreatedFromFilter(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
                  />
                  <input
                    type="date"
                    value={createdToFilter}
                    onChange={(e) => setCreatedToFilter(e.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm"
                  />
                </div>
              </div>
              {studies.length === 0 && !studiesLoading ? (
                <div className="px-5 py-12 text-center text-slate-500">
                  Нет исследований для распределения
                </div>
              ) : (
                studies.map((study) => {
                  const isSelected = selectedStudy?.research_number === study.research_number;
                  return (
                    <button
                      key={study.research_number}
                      onClick={() => setSelectedStudy(study)}
                      className={`w-full px-4 py-4 text-left transition hover:bg-slate-50 md:px-5 ${
                        isSelected ? 'border-l-4 border-blue-500 bg-blue-50' : ''
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-medium text-slate-900 truncate">
                            {study.research_number}
                          </div>
                          <div className="text-sm text-slate-500 mt-1 truncate">
                            {study.study_type?.name || 'Тип исследования не указан'}
                          </div>
                        </div>

                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border shrink-0 ${getPriorityColor(
                            study.priority
                          )}`}
                        >
                          {getPriorityLabel(study.priority)}
                        </span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>

            <div className="border-t border-slate-200 px-4 py-4 md:px-5">
              <Pagination
                page={currentPage}
                setPage={setCurrentPage}
                totalPages={totalPages}
              />
            </div>
          </div>
        </div>

        <div
          className={`xl:col-span-7 space-y-4 ${
            mobileTab !== 'doctors' ? 'hidden lg:block' : ''
          }`}
        >
          <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm shadow-slate-200/60">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4 md:px-5">
              <div>
                <h3 className="font-semibold text-slate-950">Доступные врачи</h3>
                <p className="mt-0.5 text-sm text-slate-500">
                  Раскрой врача, чтобы посмотреть его текущие исследования
                </p>
              </div>
            </div>

            <div className="max-h-[calc(100dvh-250px)] space-y-3 overflow-y-auto p-3 md:p-4 xl:max-h-[720px]">
              {paginatedDoctors.length === 0 && !loading ? (
                <div className="text-center py-12 text-slate-500">Врачи не найдены</div>
              ) : (
                paginatedDoctors.map((doc) => (
                  <DoctorCard
                    key={doc.id}
                    doc={doc}
                    distStat={distStatMap[doc.id]}
                    isSelectedForAssign={selectedDoctor === doc.id}
                    isExpanded={expandedDoctor === doc.id}
                    studiesState={doctorStudies[doc.id]}
                    hasSelectedStudy={Boolean(selectedStudy)}
                    onToggleExpand={handleToggleExpand}
                    onSelectForAssign={handleSelectForAssign}
                  />
                ))
              )}
            </div>

            <div className="border-t border-slate-200 px-4 py-4 md:px-5">
              <Pagination
                page={doctorPage}
                setPage={setDoctorPage}
                totalPages={totalDoctorPages}
              />
            </div>
          </div>
        </div>
      </div>

      <ConfirmDistributionModal
        isOpen={showConfirmModal}
        distResult={distResult}
        doctors={doctors}
        onConfirm={handleConfirmDistribution}
        onCancel={() => setShowConfirmModal(false)}
        onReassign={handleReassign}
        confirming={confirming}
      />

      <DraftsModal
        isOpen={showDrafts}
        drafts={drafts}
        onClose={() => setShowDrafts(false)}
        onOpenDraft={openDraft}
        onRemoveDraft={removeDraft}
      />
    </div>
  );
};

export default CurrentDistributionView;
