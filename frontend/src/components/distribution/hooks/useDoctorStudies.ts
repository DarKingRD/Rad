import { useState } from 'react';
import { studiesApi } from '../../../services/api';
import type { Study } from '../../../types';

export interface DoctorStudiesState {
  loading: boolean;
  assignedStudies: Study[];
  completedStudies: Study[];
  error: string | null;
}

export const useDoctorStudies = () => {
  const [expandedDoctor, setExpandedDoctor] = useState<number | null>(null);
  const [doctorStudies, setDoctorStudies] = useState<
    Record<number, DoctorStudiesState>
  >({});

  const handleToggleExpand = async (doctorId: number) => {
    if (expandedDoctor === doctorId) {
      setExpandedDoctor(null);
      return;
    }

    setExpandedDoctor(doctorId);

    if (doctorStudies[doctorId]) {
      return;
    }

    setDoctorStudies((prev) => ({
      ...prev,
      [doctorId]: { loading: true, assignedStudies: [], completedStudies: [], error: null },
    }));

    try {
      const now = new Date();
      const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
      const nextMonthStart = new Date(now.getFullYear(), now.getMonth() + 1, 1);
      const formatDate = (date: Date) => {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
      };

      const [assignedData, completedData] = await Promise.all([
        studiesApi.getAll({
          diagnostician_id: doctorId,
          status: 'confirmed',
          date_from: formatDate(monthStart),
          date_to: formatDate(nextMonthStart),
        }),
        studiesApi.getAll({
          diagnostician_id: doctorId,
          status: 'signed',
          date_from: formatDate(monthStart),
          date_to: formatDate(nextMonthStart),
        }),
      ]);

      const isCurrentMonthStudy = (study: Study) => {
        const createdAt = study.created_at ? new Date(study.created_at) : null;
        return Boolean(createdAt && createdAt >= monthStart && createdAt < nextMonthStart);
      };

      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: {
          loading: false,
          assignedStudies: (assignedData || []).filter(isCurrentMonthStudy),
          completedStudies: (completedData || []).filter(isCurrentMonthStudy),
          error: null,
        },
      }));
    } catch {
      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: {
          loading: false,
          assignedStudies: [],
          completedStudies: [],
          error: 'Не удалось загрузить исследования врача',
        },
      }));
    }
  };

  return {
    expandedDoctor,
    doctorStudies,
    handleToggleExpand,
  };
};
