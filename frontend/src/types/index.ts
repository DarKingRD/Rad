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

export type ChartPoint = ChartData;

export interface KPICardProps {
  title: string;
  value: string | number;
  subtext: string;
  trend?: number;
}

// === ПРОГНОЗ СМЕН ===

export interface ForecastModalityItem {
  modality: string;
  expected_studies: number;
  expected_up: number;
  recommended_doctors: number;
}

export interface ForecastChartPoint {
  date: string;
  label: string;
  expected_studies_total: number;
  min_doctors: number;
}

export interface ForecastDay {
  date: string;
  label: string;
  weekday: string;
  scheduled_doctors: number;
  expected_studies_total: number;
  expected_up_total: number;
  min_doctors: number;
  gap_to_schedule: number;
  required_modalities: ForecastModalityItem[];
}

export interface ShiftForecastSummary {
  total_expected_studies: number;
  total_expected_up: number;
  max_min_doctors_per_shift: number;
  modalities: string[];
}

export interface ShiftForecastResponse {
  date_from: string;
  date_to: string;
  history_start_date: string | null;
  history_end_date: string | null;
  generated_at: string;
  summary: ShiftForecastSummary;
  chart: ForecastChartPoint[];
  days: ForecastDay[];
  message: string;
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
  weighted_tardiness?: number;
  baseline_tardiness_hours?: number;
  baseline_weighted_tardiness?: number;
  tardiness_reduction?: number;
  weighted_tardiness_reduction?: number;
  up_value: number;
  is_overdue: boolean;
}

export interface PriorityBreakdownStat {
  priority: 'normal' | 'asap' | 'cito' | string;
  total: number;
  assigned: number;
  unassigned: number;
  share_percent: number;
  assigned_rate_percent: number;
  overdue_total: number;
  overdue_assigned: number;
  overdue_unassigned: number;
  overdue_rate_percent: number;
  overdue_cleared?: number;
  overdue_remaining?: number;
  overdue_cleared_percent?: number;
  queue_overdue_hours_total?: number;
  queue_overdue_hours_assigned?: number;
  queue_overdue_hours_remaining?: number;
  queue_overdue_hours_cleared_percent?: number;
  scheduled_overdue_total?: number;
  scheduled_overdue_assigned?: number;
  scheduled_overdue_unassigned?: number;
  scheduled_overdue_hours_total?: number;
  scheduled_overdue_hours_assigned?: number;
  scheduled_overdue_hours_unassigned?: number;
  overdue_hours_total?: number;
  overdue_hours_avg?: number;
  projected_tardiness_total?: number;
  projected_weighted_tardiness_total?: number;
  baseline_tardiness_total?: number;
  baseline_weighted_tardiness_total?: number;
  tardiness_reduction?: number;
  weighted_tardiness_reduction?: number;
  tardiness_reduction_percent?: number;
  weighted_tardiness_reduction_percent?: number;
  tardiness_p50?: number;
  tardiness_p95?: number;
  tardiness_p99?: number;
}

export interface DistributionSummary {
  total?: number;
  assigned: number;
  unassigned: number;
  cito_assigned?: number;
  cito_total?: number;
  total_tardiness: number;
  total_weighted_tardiness: number;
  baseline_total_tardiness?: number;
  baseline_total_weighted_tardiness?: number;
  tardiness_reduction?: number;
  weighted_tardiness_reduction?: number;
  tardiness_reduction_percent?: number;
  weighted_tardiness_reduction_percent?: number;
  avg_tardiness: number;
  assignment_rate_percent?: number;
  tardiness_p50?: number;
  tardiness_p95?: number;
  tardiness_p99?: number;
  overdue_total?: number;
  overdue_assigned?: number;
  overdue_unassigned?: number;
  overdue_rate_percent?: number;
  overdue_cleared?: number;
  overdue_remaining?: number;
  overdue_cleared_percent?: number;
  queue_overdue_hours_total?: number;
  queue_overdue_hours_assigned?: number;
  queue_overdue_hours_remaining?: number;
  queue_overdue_hours_cleared_percent?: number;
  scheduled_overdue_total?: number;
  scheduled_overdue_assigned?: number;
  scheduled_overdue_unassigned?: number;
  scheduled_overdue_hours_total?: number;
  scheduled_overdue_hours_assigned?: number;
  scheduled_overdue_hours_unassigned?: number;
}

export interface DistResult extends DistributionSummary {
  summary?: DistributionSummary;
  doctor_stats: DoctorDistStat[];
  priority_breakdown?: {
    plan?: PriorityBreakdownStat;
    asap?: PriorityBreakdownStat;
    cito?: PriorityBreakdownStat;
  };
  assignments: Assignment[];
  distribution_id?: string;
  preview_mode?: boolean;
  target_date?: string;
  message?: string;
  _debug?: string[];
  _savedAt?: string;
  _savedDate?: string;
}

export type DistributionObjective =
  | 'weighted_tardiness_lexicographic'
  | 'tardiness_lexicographic'
  | 'max_assignments'
  | 'priority_tier_tardiness_multipass';

export interface DistributionPreviewPayload {
  date: string;
  preview?: boolean;
  date_from?: string;
  date_to?: string;
  use_mip?: boolean;
  objective?: DistributionObjective;
}

export interface DistributionConfirmResponse {
  status: string;
  assigned: number;
  distribution_id: string;
  message: string;
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
