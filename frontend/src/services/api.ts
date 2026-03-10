import axios from 'axios';
import type { DistResult } from '../types';

const API_BASE_URL = 'http://localhost:8000/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      console.error('API Error Response:', error.response.data);
    } else if (error.request) {
      console.error('API Error Request:', error.request);
    } else {
      console.error('API Error Message:', error.message);
    }
    return Promise.reject(error);
  }
);

const retryRequest = async <T>(
  requestFn: () => Promise<T>,
  retries = 3,
  delay = 1000
): Promise<T> => {
  try {
    return await requestFn();
  } catch (error) {
    if (retries > 0) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      return retryRequest(requestFn, retries - 1, delay * 2);
    }
    throw error;
  }
};

export const doctorsApi = {
  getAll: () => retryRequest(() => api.get('/doctors/')),
  getWithLoad: () => retryRequest(() => api.get('/doctors/with_load/')),
  getById: (id: number) => retryRequest(() => api.get(`/doctors/${id}/`)),
  create: (data: any) => retryRequest(() => api.post('/doctors/', data)),
  update: (id: number, data: any) => retryRequest(() => api.put(`/doctors/${id}/`, data)),
  delete: (id: number) => retryRequest(() => api.delete(`/doctors/${id}/`)),
};

export const studyTypesApi = {
  getAll: () => retryRequest(() => api.get('/study-types/')),
};

export const schedulesApi = {
  getAll: (params?: { date_from?: string; date_to?: string; doctor_id?: number }) =>
    retryRequest(() => api.get('/schedules/', { params })),
  getByDate: (date: string) =>
    retryRequest(() => api.get('/schedules/by_date/', { params: { date } })),
  getById: (id: number) => retryRequest(() => api.get(`/schedules/${id}/`)),
  create: (data: any) => retryRequest(() => api.post('/schedules/', data)),
  update: (id: number, data: any) => retryRequest(() => api.put(`/schedules/${id}/`, data)),
  delete: (id: number) => retryRequest(() => api.delete(`/schedules/${id}/`)),
};

export const studiesApi = {
  getAll: (params?: {
    status?: string;
    priority?: string;
    date_from?: string;
    date_to?: string;
    diagnostician_id?: number;
  }) => retryRequest(() => api.get('/studies/', { params })),

  getPending: (page = 1, pageSize = 100) =>
    retryRequest(() =>
      api.get('/studies/pending/', {
        params: { page, page_size: pageSize },
      })
    ),

  getCito: () => retryRequest(() => api.get('/studies/cito/')),
  getAsap: () => retryRequest(() => api.get('/studies/asap/')),

  assign: (id: string, doctor_id: number) =>
    retryRequest(() => api.post(`/studies/${id}/assign/`, { doctor_id })),

  updateStatus: (id: string, status: string) =>
    retryRequest(() => api.put(`/studies/${id}/update_status/`, { status })),
};

export const dashboardApi = {
  getStats: (date?: string) =>
    retryRequest(() => api.get('/dashboard/stats/', { params: { date } })),

  getChartData: (date_from: string, date_to: string) =>
    retryRequest(() =>
      api.get('/dashboard/chart/', {
        params: { date_from, date_to },
      })
    ),
};

export const distributionApi = {
  getInfo: () => retryRequest(() => api.get('/distribute/')),

  preview: (payload: {
    date: string;
    preview?: boolean;
    date_from?: string;
    date_to?: string;
    use_mip?: boolean;
  }) => retryRequest(() => api.post<DistResult>('/distribute/', payload)),

  confirm: (distribution_id: string) =>
    retryRequest(() =>
      api.post('/distribute/confirm/', { distribution_id })
    ),
};