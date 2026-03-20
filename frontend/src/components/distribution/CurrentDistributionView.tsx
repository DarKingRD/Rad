import React, { useEffect, useMemo, useState } from 'react';
import {
  Archive,
  Calendar,
  Eye,
  Filter,
  Loader2,
  UserCheck,
  Zap,
} from 'lucide-react';
import { distributionApi, doctorsApi, studiesApi } from '../../services/api';
import type {
  Assignment,
  DistResult,
  DistributionDraft,
  DoctorDistStat,
  DoctorWithLoad,
  DistributionInfo,
  Study,
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

const CurrentDistributionView: React.FC = () => {
  const [studiesTotal, setStudiesTotal] = useState(0);
  const [studies, setStudies] = useState<Study[]>([]);
  const [doctors, setDoctors] = useState<DoctorWithLoad[]>([]);
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

  const [mobileTab, setMobileTab] = useState<MobileTab>('studies');
  const [currentPage, setCurrentPage] = useState(1);
  const [doctorPage, setDoctorPage] = useState(1);

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
      const pendingData = await studiesApi.getPending(currentPage, ITEMS_PER_PAGE);
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-900">
            Текущее распределение
          </h2>
          <p className="text-slate-500 mt-1">
            Выбери исследование, врача и выполни ручное или автоматическое распределение
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setShowDrafts(true)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50"
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
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-red-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-blue-50 flex items-center justify-center text-blue-600">
              <UserCheck size={22} />
            </div>
            <div>
              <div className="text-sm text-slate-500">Доступно врачей</div>
              <div className="text-2xl font-bold text-slate-900">
                {loading ? '—' : distInfo?.available_doctors ?? doctors.length}
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-amber-50 flex items-center justify-center text-amber-600">
              <Filter size={22} />
            </div>
            <div>
              <div className="text-sm text-slate-500">Ожидают назначения</div>
              <div className="text-2xl font-bold text-slate-900">
                {studiesLoading ? '—' : studiesTotal}
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-xl bg-green-50 flex items-center justify-center text-green-600">
              <Calendar size={22} />
            </div>
            <div>
              <div className="text-sm text-slate-500">Дата распределения</div>
              <div className="text-2xl font-bold text-slate-900">
                {distributionDate}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 md:p-5">
        <div className="flex flex-col gap-4">
          <div className="flex flex-col lg:flex-row gap-3 lg:items-end">
            <div className="flex-1">
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Дата распределения
              </label>
              <input
                type="date"
                value={distributionDate}
                onChange={(e) => setDistributionDate(e.target.value)}
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
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
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
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
                className="w-full border border-slate-300 rounded-lg px-3 py-2"
              />
            </div>

            <label className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-300 h-[42px]">
              <input
                type="checkbox"
                checked={useMip}
                onChange={(e) => setUseMip(e.target.checked)}
              />
              <span className="text-sm text-slate-700">Использовать MIP</span>
            </label>

            <button
              onClick={handleRunDistribution}
              disabled={distributing}
              className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
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
            <div className="rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-3">
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
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  <Eye size={16} />
                  Назначить вручную
                </button>

                <button
                  onClick={() => {
                    setSelectedStudy(null);
                    setSelectedDoctor(null);
                  }}
                  className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50"
                >
                  Сбросить
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="lg:hidden flex rounded-xl border border-slate-200 bg-white p-1">
        <button
          onClick={() => setMobileTab('studies')}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium ${
            mobileTab === 'studies'
              ? 'bg-blue-600 text-white'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          Исследования
        </button>
        <button
          onClick={() => setMobileTab('doctors')}
          className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium ${
            mobileTab === 'doctors'
              ? 'bg-blue-600 text-white'
              : 'text-slate-700 hover:bg-slate-50'
          }`}
        >
          Врачи
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div
          className={`xl:col-span-5 space-y-4 ${
            mobileTab !== 'studies' ? 'hidden lg:block' : ''
          }`}
        >
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">
                  Ожидающие исследования
                </h3>
                <p className="text-sm text-slate-500 mt-0.5">
                  Выбери исследование для ручного назначения
                </p>
              </div>

              {studiesLoading && <Loader2 size={18} className="animate-spin text-slate-400" />}
            </div>

            <div className="divide-y divide-slate-100 max-h-[720px] overflow-y-auto">
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
                      className={`w-full text-left px-5 py-4 hover:bg-slate-50 transition ${
                        isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : ''
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

            <div className="px-5 py-4 border-t border-slate-200">
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
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">Доступные врачи</h3>
                <p className="text-sm text-slate-500 mt-0.5">
                  Раскрой врача, чтобы посмотреть его текущие исследования
                </p>
              </div>
            </div>

            <div className="p-4 space-y-3 max-h-[720px] overflow-y-auto">
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

            <div className="px-5 py-4 border-t border-slate-200">
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