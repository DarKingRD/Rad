import { useState } from 'react';
import { studiesApi } from '../../../services/api';
import type { Study } from '../../../types';

export interface DoctorStudiesState {
  loading: boolean;
  studies: Study[];
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
      [doctorId]: { loading: true, studies: [], error: null },
    }));

    try {
      const studiesData = await studiesApi.getAll({
        diagnostician_id: doctorId,
        status: 'confirmed',
      });

      setDoctorStudies((prev) => ({
        ...prev,
        [doctorId]: {
          loading: false,
          studies: studiesData || [],
          error: null,
        },
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

  return {
    expandedDoctor,
    doctorStudies,
    handleToggleExpand,
  };
};