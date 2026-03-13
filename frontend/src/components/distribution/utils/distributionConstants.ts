export const DRAFTS_STORAGE_KEY = 'distribution_preview_drafts_v1';
export const ITEMS_PER_PAGE = 20;
export const DOCTORS_PER_PAGE = 8;

export const PRIORITY_ORDER: Record<string, number> = {
  cito: 1,
  asap: 2,
  normal: 3,
};

export type ConfirmTab = 'summary' | 'assigned' | 'unassigned' | 'doctors';
export type AssignmentFilter = 'all' | 'cito' | 'asap' | 'normal';
export type MobileTab = 'studies' | 'doctors';