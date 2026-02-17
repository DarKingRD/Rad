import { Doctor, Schedule, Study, StudyType, Patient, Device, Organization, DoctorWithLoad, DashboardStats } from '../types';

// === DOCTORS (из doctors_202602162104.csv) ===
export const MOCK_DOCTORS: Doctor[] = [
  { id: 26, fio_alias: 'Заболотских Д.М.', snils: '604-510-251 33', gender: 1, position_type: 'radiologist', work_start: '2024-10-23', work_end: '9999-12-31', is_chief: false, is_active: true },
  { id: 27, fio_alias: 'Островская Е.Б.', snils: '122-572-431 30', gender: 0, position_type: 'diagnostician', work_start: '2024-09-02', work_end: '9999-12-31', is_chief: false, is_active: true },
  { id: 28, fio_alias: 'Спиранова Е.В.', snils: '441-487-167 88', gender: 0, position_type: 'radiologist', work_start: '2024-03-01', work_end: '9999-12-31', is_chief: true, is_active: true },
  { id: 29, fio_alias: 'Елагина М.С.', snils: '317-951-187 92', gender: 0, position_type: 'radiologist', work_start: '2024-10-14', work_end: '9999-12-31', is_chief: false, is_active: true },
  { id: 30, fio_alias: 'Лапин В.С.', snils: '225-896-432 11', gender: 1, position_type: 'radiologist', work_start: '2024-05-20', work_end: '9999-12-31', is_chief: false, is_active: true },
];

// === SCHEDULES (из schedules_202602162104.csv) ===
export const MOCK_SCHEDULES: Schedule[] = [
  { id: 2862, doctor_id: 26, work_date: '2025-10-17', time_start: '09:00:00', time_end: '14:00:00', break_start: '12:00:00', break_end: '13:00:00', work_duration: '04:00:00', is_day_off: 0, created_at: '2024-12-09 10:08:09.881 +0300', updated_at: '2025-01-28 11:04:33.464 +0300' },
  { id: 2863, doctor_id: 27, work_date: '2025-10-17', time_start: '09:00:00', time_end: '17:00:00', break_start: '12:00:00', break_end: '13:00:00', work_duration: '07:00:00', is_day_off: 0, created_at: '2024-12-09 10:08:09.881 +0300', updated_at: '2025-01-28 11:04:33.464 +0300' },
  { id: 2864, doctor_id: 28, work_date: '2025-10-17', time_start: '08:00:00', time_end: '14:00:00', break_start: '00:00:00', break_end: '00:00:00', work_duration: '06:00:00', is_day_off: 0, created_at: '2024-12-09 10:08:09.881 +0300', updated_at: '2025-01-28 11:04:33.464 +0300' },
  { id: 2865, doctor_id: 29, work_date: '2025-10-17', time_start: '14:00:00', time_end: '20:00:00', break_start: '00:00:00', break_end: '00:00:00', work_duration: '06:00:00', is_day_off: 0, created_at: '2024-12-09 10:08:09.881 +0300', updated_at: '2025-01-28 11:04:33.464 +0300' },
  { id: 2866, doctor_id: 30, work_date: '2025-10-18', time_start: '09:00:00', time_end: '17:00:00', break_start: '12:00:00', break_end: '13:00:00', work_duration: '07:00:00', is_day_off: 0, created_at: '2024-12-09 10:08:09.881 +0300', updated_at: '2025-01-28 11:04:33.464 +0300' },
];

// === STUDIES (из studies_202602162120.csv) ===
export const MOCK_STUDIES: Study[] = [
  { id: 48548, research_number: '251017-164622080', patient_id: 48548, study_type_id: 74, device_id: 48, organization_id: 87, diagnostician_id: 25, referring_doctor_id: 18, icd10_code: 'J04.1', status: 'confirmed', priority: 'cito', created_at: '2025-10-17 19:48:41.000 +0300', planned_at: '2025-10-17 19:44:12.000 +0300', completed_at: null },
  { id: 21879, research_number: '251105-115037592', patient_id: 21879, study_type_id: 20, device_id: 15, organization_id: 196, diagnostician_id: 25, referring_doctor_id: 5, icd10_code: 'N13.3', status: 'signed', priority: 'cito', created_at: '2025-11-05 14:59:42.000 +0300', planned_at: '2025-11-05 00:00:00.000 +0300', completed_at: null },
  { id: 33908, research_number: '251028-055005206', patient_id: 33908, study_type_id: 286, device_id: 6, organization_id: 206, diagnostician_id: 25, referring_doctor_id: 4, icd10_code: 'J20.9', status: 'signed', priority: 'cito', created_at: '2025-10-28 08:58:28.000 +0300', planned_at: '2025-10-28 00:00:00.000 +0300', completed_at: null },
  { id: 881, research_number: '251117-072747172', patient_id: 882, study_type_id: 146, device_id: 48, organization_id: 217, diagnostician_id: 27, referring_doctor_id: 18, icd10_code: 'C50.4', status: 'confirmed', priority: 'cito', created_at: '2025-11-17 10:29:40.000 +0300', planned_at: '2025-11-17 10:16:46.000 +0300', completed_at: null },
  { id: 33922, research_number: '251028-054300727', patient_id: 33922, study_type_id: 68, device_id: 6, organization_id: 206, diagnostician_id: 25, referring_doctor_id: 7, icd10_code: 'S42.2', status: 'signed', priority: 'cito', created_at: '2025-10-28 08:48:25.000 +0300', planned_at: '2025-10-28 00:00:00.000 +0300', completed_at: null },
];

// === STUDY TYPES ===
export const MOCK_STUDY_TYPES: StudyType[] = [
  { id: 7003734, code: '7003734', name: 'Рентгенография таза', modality: 'XRAY', duration_min: 15, complexity: 1, base_up: 1.0 },
  { id: 7003908, code: '7003908', name: 'Рентгенография кисти', modality: 'XRAY', duration_min: 10, complexity: 1, base_up: 0.8 },
  { id: 7003007, code: '7003007', name: 'Рентгенография черепа', modality: 'XRAY', duration_min: 15, complexity: 2, base_up: 1.2 },
  { id: 7002892, code: '7002892', name: 'Рентгенография грудной клетки', modality: 'XRAY', duration_min: 10, complexity: 1, base_up: 0.8 },
  { id: 7003338, code: '7003338', name: 'Рентгенография ребер', modality: 'XRAY', duration_min: 15, complexity: 2, base_up: 1.2 },
];

// === PATIENTS ===
export const MOCK_PATIENTS: Patient[] = [
  { id: 1, full_name: 'ФИО ПАЦИЕНТА', birth_date: '19.10.1958', gender: 1, phone: '+7XXX', snils: 'XXX-XXX-XXX XX' },
  { id: 2, full_name: 'ФИО ПАЦИЕНТА', birth_date: '15.11.1958', gender: 0, phone: '+7XXX', snils: 'XXX-XXX-XXX XX' },
];

// === DEVICES ===
export const MOCK_DEVICES: Device[] = [
  { id: 1, name: 'ЗАО НИПК Электрон', model: 'Электрон', manufacturer: 'ЗАО НИПК', organization_id: 1, modality: 'XRAY' },
  { id: 2, name: '«РЕНЕКС-РЦ»', model: 'РЕНЕКС', manufacturer: 'РЕНЕКС', organization_id: 1, modality: 'XRAY' },
  { id: 3, name: '4101240000412', model: 'КТ', manufacturer: 'Siemens', organization_id: 2, modality: 'CT' },
];

// === ORGANIZATIONS ===
export const MOCK_ORGANIZATIONS: Organization[] = [
  { id: 1, name: 'ГБУЗ АО "МИАЦ"', inn: '2901234567', type: 'diagnostic_center' },
  { id: 2, name: 'ГБУЗ АО "АОДКБ"', inn: '2902345678', type: 'hospital' },
  { id: 3, name: 'ГБУЗ " АГКБ № 7"', inn: '2903456789', type: 'hospital' },
];

// === DOCTORS WITH LOAD ===
export const MOCK_DOCTORS_WITH_LOAD: DoctorWithLoad[] = MOCK_DOCTORS.map((doc, index) => ({
  ...doc,
  currentLoad: 60 + index * 15,
  maxLoad: 120,
  activeStudies: 3 + index,
  specialty: doc.position_type === 'radiologist' ? 'Рентгенолог' : 'КТ-диагност',
}));

// === DASHBOARD STATS ===
export const MOCK_DASHBOARD_STATS: DashboardStats = {
  totalStudies: 487,
  completedStudies: 412,
  pendingStudies: 75,
  activeDoctors: 5,
  avgLoadPerDoctor: 89,
  citoStudies: 156,
  asapStudies: 48,
};

// === CHART DATA ===
export const CHART_DATA = [
  { name: '01.10', plan: 400, actual: 380 },
  { name: '02.10', plan: 300, actual: 320 },
  { name: '03.10', plan: 450, actual: 410 },
  { name: '04.10', plan: 350, actual: 340 },
  { name: '05.10', plan: 400, actual: 390 },
  { name: '06.10', plan: 300, actual: 280 },
  { name: '07.10', plan: 420, actual: 400 },
];