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
  current_load: number;     // фактические УП за текущий месяц
  max_load: number;         // месячная норма = max_up_per_day × рабочие дни месяца
  active_studies: number;
  load_percentage: number;  // current_load / max_load * 100
  // Расписание на сегодня
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
  research_number: string;  // PK — строка, не число
  study_type_id: number | null;
  status: 'pending' | 'confirmed' | 'signed';  // строгий union вместо string
  priority: 'normal' | 'cito' | 'asap';
  created_at: string;
  planned_at: string | null;  // может быть null если ещё не назначено
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
