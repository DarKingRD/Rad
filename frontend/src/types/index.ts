// === ОСНОВНЫЕ ТИПЫ ДАННЫХ ===

export interface Doctor {
  id: number;
  fio_alias: string;
  position_type: string;
  max_up_per_day: number;
  modality?: string[];
  is_active: boolean;
  specialty: string;
}

export interface DoctorWithLoad extends Doctor {
  current_load: number;
  max_load: number;
  active_studies: number;
}

export interface StudyType {
  id: number;
  name: string;
  modality: string;
  up_value: number;
}

export interface Schedule {
  id: number;
  doctor_id: number;
  work_date: string;
  time_start: string;
  time_end: string;
  is_day_off: number;
  planned_up: number;
  doctor_name?: string;
  doctor?: Doctor;
}

export interface Study {
  id: number;
  research_number: string;
  study_type_id: number;
  status: string;
  priority: 'normal' | 'cito' | 'asap';
  created_at: string;
  planned_at: string;
  diagnostician_id: number | null;
  study_type?: StudyType;
  diagnostician?: Doctor;
}

export interface DashboardStats {
  total_studies: number;
  completed_studies: number;
  pending_studies: number;
  active_doctors: number;
  avg_load_per_doctor: number;
  cito_studies: number;
  asap_studies: number;
}

export interface ChartData {
  name: string;
  plan: number;
  actual: number;
}

export interface KPICardProps {
  title: string;
  value: string | number;
  subtext: string;
  trend?: number;
}