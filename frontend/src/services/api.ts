import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// === DOCTORS ===
export const doctorsApi = {
  getAll: () => api.get('/doctors/'),
  getWithLoad: () => api.get('/doctors/with_load/'),
  getById: (id: number) => api.get(`/doctors/${id}/`),
  create: (data: any) => api.post('/doctors/', data),
  update: (id: number, data: any) => api.put(`/doctors/${id}/`, data),
  delete: (id: number) => api.delete(`/doctors/${id}/`),
};

// === STUDY TYPES ===
export const studyTypesApi = {
  getAll: () => api.get('/study-types/'),
};

// === SCHEDULES ===
export const schedulesApi = {
  getAll: (params?: { date_from?: string; date_to?: string; doctor_id?: number }) => 
    api.get('/schedules/', { params }),
  getByDate: (date: string) => api.get('/schedules/by_date/', { params: { date } }),
  getById: (id: number) => api.get(`/schedules/${id}/`),
  create: (data: any) => api.post('/schedules/', data),
  update: (id: number, data: any) => api.put(`/schedules/${id}/`, data),
  delete: (id: number) => api.delete(`/schedules/${id}/`),
};

// === STUDIES ===
export const studiesApi = {
  getAll: (params?: { status?: string; priority?: string; date_from?: string; date_to?: string }) => 
    api.get('/studies/', { params }),
  getPending: () => api.get('/studies/pending/'),
  getCito: () => api.get('/studies/cito/'),
  getAsap: () => api.get('/studies/asap/'),
  assign: (id: number, doctor_id: number) => api.post(`/studies/${id}/assign/`, { doctor_id }),
  updateStatus: (id: number, status: string) => api.put(`/studies/${id}/update_status/`, { status }),
};

// === DASHBOARD ===
export const dashboardApi = {
  getStats: (date?: string) => api.get('/dashboard/stats/', { params: { date } }),
  getChartData: (date_from: string, date_to: string) => 
    api.get('/dashboard/chart/', { params: { date_from, date_to } }),
};