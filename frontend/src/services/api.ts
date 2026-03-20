import axios, { AxiosError, AxiosInstance, AxiosResponse } from 'axios';
import type {
  DistResult,
  Doctor,
  DoctorWithLoad,
  Schedule,
  Study,
  StudyType,
  DashboardStats,
  ChartPoint,
} from '../types';

type ApiListResponse<T> = T[] | { results: T[] };

type SchedulePayload = {
  doctor_id: number;
  work_date: string;
  time_start: string | null;
  time_end: string | null;
  break_start?: string | null;
  break_end?: string | null;
  is_day_off: number;
  planned_up: number;
};

type DoctorPayload = {
  fio_alias: string;
  position_type: string;
  max_up_per_day: number;
  is_active: boolean;
  modality: string[];
};

type StudyAssignResponse = Study;
type StudyStatusResponse = Study;

type DistributionInfo = {
  pending_studies: number;
  available_doctors: number;
  study_date_range: {
    min: string | null;
    max: string | null;
  };
  schedule_date_range: {
    min: string | null;
    max: string | null;
  };
  message: string;
};

type DistributionPreviewInfo = {
  pending_studies: number;
  available_doctors: number;
  target_date: string;
  message: string;
};

type DistributionPreviewPayload = {
  date: string;
  preview?: boolean;
  date_from?: string;
  date_to?: string;
  use_mip?: boolean;
};

type DistributionConfirmResponse = {
  status: string;
  assigned: number;
  distribution_id: string;
  message: string;
};

const API_BASE_URL = 'http://localhost:8000/api'; // Здесь потом нужно этот хардкод убрать

export class ApiClientError extends Error {
  status?: number;
  details?: unknown;

  constructor(message: string, status?: number, details?: unknown) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.details = details;
  }
}

const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response) {
      console.error('API Error Response:', error.response.data);
    } else if (error.request) {
      console.error('API Error Request:', error.request);
    } else {
      console.error('API Error Message:', error.message);
    }
    return Promise.reject(normalizeAxiosError(error));
  }
);

function normalizeAxiosError(error: unknown): ApiClientError {
  if (error instanceof ApiClientError) {
    return error;
  }

  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const details = error.response?.data;

    const detailMessage =
      typeof details === 'object' && details !== null
        ? (details as Record<string, unknown>).detail ||
          (details as Record<string, unknown>).error ||
          error.message
        : error.message;

    return new ApiClientError(String(detailMessage || 'Ошибка API'), status, details);
  }

  if (error instanceof Error) {
    return new ApiClientError(error.message);
  }

  return new ApiClientError('Неизвестная ошибка');
}

function shouldRetry(error: unknown): boolean {
  if (!(error instanceof ApiClientError)) {
    return false;
  }

  if (!error.status) {
    return true;
  }

  return error.status >= 500 || error.status === 429;
}

async function retryGetRequest<T>(
  requestFn: () => Promise<T>,
  retries = 2,
  delay = 700
): Promise<T> {
  try {
    return await requestFn();
  } catch (error) {
    if (retries > 0 && shouldRetry(error)) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      return retryGetRequest(requestFn, retries - 1, delay * 2);
    }
    throw error;
  }
}

function extractList<T>(response: AxiosResponse<ApiListResponse<T>>): T[] {
  const data = response.data;
  return Array.isArray(data) ? data : data.results;
}

async function getList<T>(url: string, params?: Record<string, unknown>): Promise<T[]> {
  const response = await retryGetRequest(() => api.get<ApiListResponse<T>>(url, { params }));
  return extractList(response);
}

async function getOne<T>(url: string, params?: Record<string, unknown>): Promise<T> {
  const response = await retryGetRequest(() => api.get<T>(url, { params }));
  return response.data;
}

async function postOne<TResponse, TPayload>(url: string, payload: TPayload): Promise<TResponse> {
  const response = await api.post<TResponse>(url, payload);
  return response.data;
}

async function putOne<TResponse, TPayload>(url: string, payload: TPayload): Promise<TResponse> {
  const response = await api.put<TResponse>(url, payload);
  return response.data;
}

async function patchOne<TResponse, TPayload>(url: string, payload: TPayload): Promise<TResponse> {
  const response = await api.patch<TResponse>(url, payload);
  return response.data;
}

async function deleteOne(url: string): Promise<void> {
  await api.delete(url);
}

export const doctorsApi = {
  getAll: () => getList<Doctor>('/doctors/'),
  getWithLoad: () => getList<DoctorWithLoad>('/doctors/with_load/'),
  getById: (id: number) => getOne<Doctor>(`/doctors/${id}/`),
  create: (data: DoctorPayload) => postOne<Doctor, DoctorPayload>('/doctors/', data),
  update: (id: number, data: DoctorPayload) =>
    putOne<Doctor, DoctorPayload>(`/doctors/${id}/`, data),
  delete: (id: number) => deleteOne(`/doctors/${id}/`),
};

export const studyTypesApi = {
  getAll: () => getList<StudyType>('/study-types/'),
};

export const schedulesApi = {
  getAll: (params?: { date_from?: string; date_to?: string; doctor_id?: number }) =>
    getList<Schedule>('/schedules/', params),
  getByDate: (date: string) => getList<Schedule>('/schedules/by_date/', { date }),
  getById: (id: number) => getOne<Schedule>(`/schedules/${id}/`),
  create: (data: SchedulePayload) => postOne<Schedule, SchedulePayload>('/schedules/', data),
  update: (id: number, data: SchedulePayload) =>
    putOne<Schedule, SchedulePayload>(`/schedules/${id}/`, data),
  delete: (id: number) => deleteOne(`/schedules/${id}/`),
};

export const studiesApi = {
  getAll: (params?: {
    status?: string;
    priority?: string;
    date_from?: string;
    date_to?: string;
    diagnostician_id?: number;
  }) => getList<Study>('/studies/', params),

  getPending: async (page = 1, pageSize = 100) => {
    const response = await retryGetRequest(() =>
      api.get<{
        results: Study[];
        total: number;
        page: number;
        page_size: number;
        total_pages: number;
      }>('/studies/pending/', {
        params: { page, page_size: pageSize },
      })
    );
    return response.data;
  },

  getCito: (limit = 100) => getList<Study>('/studies/cito/', { limit }),
  getAsap: (limit = 100) => getList<Study>('/studies/asap/', { limit }),

  assign: (id: string, doctor_id: number) =>
    postOne<StudyAssignResponse, { doctor_id: number }>(
      `/studies/${id}/assign/`,
      { doctor_id }
    ),

  updateStatus: (id: string, status: string) =>
    putOne<StudyStatusResponse, { status: string }>(
      `/studies/${id}/update_status/`,
      { status }
    ),
};

export const dashboardApi = {
  getStats: (dateFrom?: string, dateTo?: string) =>
    getOne<DashboardStats>('/dashboard/stats/', {
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    }),

  getChartData: (dateFrom?: string, dateTo?: string) =>
    getOne<ChartPoint[]>('/dashboard/chart/', {
      ...(dateFrom ? { date_from: dateFrom } : {}),
      ...(dateTo ? { date_to: dateTo } : {}),
    }),
};

export const distributionApi = {
  getInfo: () => getOne<DistributionInfo>('/distribute/'),

  preview: (payload: DistributionPreviewPayload) =>
    postOne<DistResult, DistributionPreviewPayload>('/distribute/', payload),

  confirm: (distribution_id: string) =>
    postOne<DistributionConfirmResponse, { distribution_id: string }>(
      '/distribute/confirm/',
      { distribution_id }
    ),

  quickPreview: (date?: string) =>
    getOne<DistributionPreviewInfo>('/distribute/preview/', date ? { date } : undefined),
};

export { api };