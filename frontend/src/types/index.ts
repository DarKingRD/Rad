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
  load_percentage: number;
  today_shift_start: string | null;
  today_shift_end: string | null;
  today_break_start: string | null;
  today_break_end: string | null;
  today_break_minutes: number;
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
  break_start: string | null;
  break_end: string | null;
  break_duration_minutes: number;
  is_day_off: number;
  planned_up: number;
  doctor_name?: string;
  doctor?: Doctor;
}

export interface Study {
  research_number: string;
  study_type_id: number | null;
  status: 'pending' | 'confirmed' | 'signed';
  priority: 'normal' | 'cito' | 'asap';
  created_at: string;
  planned_at: string | null;
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
  plan: string | number;
  actual: string | number;
}

export interface KPICardProps {
  title: string;
  value: string | number;
  subtext: string;
  trend?: number;
}

// === РАСПРЕДЕЛЕНИЕ ===

export interface DoctorDistStat {
  doctor_id: number;
  doctor_name: string;
  assigned_studies: number;
  total_up: number;
  max_up: number;
  load_percent: number;
  remaining_up: number;
}

export interface Assignment {
  study_number: string;
  study_modality?: string[];
  doctor_id: number;
  doctor_name: string;
  doctor_modality?: string[];
  priority: 'normal' | 'cito' | 'asap' | string;
  deadline: string;
  completion_time: string;
  tardiness_hours: number;
  up_value: number;
  is_overdue: boolean;
}

export interface DistResult {
  doctor_stats: DoctorDistStat[];
  assigned: number;
  unassigned: number;
  cito_assigned?: number;
  cito_total?: number;
  total_tardiness: number;
  total_weighted_tardiness: number;
  avg_tardiness: number;
  assignments: Assignment[];
  distribution_id?: string;
  preview_mode?: boolean;
  target_date?: string;
  message?: string;
  _debug?: string[];
  _savedAt?: string;
  _savedDate?: string;
}

export interface DateRange {
  min: string | null;
  max: string | null;
}

export interface DistributionInfo {
  pending_studies: number;
  available_doctors: number;
  study_date_range: DateRange;
  schedule_date_range: DateRange;
  message: string;
}

export interface DistributionDraft extends DistResult {
  distribution_id: string;
  _savedAt: string;
  _savedDate: string;
}