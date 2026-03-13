import { useCallback, useState } from 'react';
import type { DistResult, DistributionDraft } from '../../../types';
import { DRAFTS_STORAGE_KEY } from '../utils/distributionConstants';

const safelyReadDrafts = (): DistributionDraft[] => {
  try {
    const raw = localStorage.getItem(DRAFTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
};

const saveDrafts = (drafts: DistributionDraft[]) => {
  localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(drafts.slice(0, 20)));
};

export const useDistributionDrafts = () => {
  const [drafts, setDrafts] = useState<DistributionDraft[]>([]);

  const loadDrafts = useCallback(() => {
    setDrafts(safelyReadDrafts());
  }, []);

  const persistDraft = useCallback((result: DistResult) => {
    if (!result?.distribution_id) return;

    const now = new Date();
    const nextDraft: DistributionDraft = {
      ...result,
      _savedAt: now.toISOString(),
      _savedDate: result.target_date || now.toISOString().split('T')[0],
    };

    const prev = safelyReadDrafts().filter(
      (item) => item.distribution_id !== result.distribution_id
    );

    const next = [nextDraft, ...prev].slice(0, 20);
    saveDrafts(next);
    setDrafts(next);
  }, []);

  const removeDraft = useCallback((distributionId: string) => {
    const next = safelyReadDrafts().filter(
      (item) => item.distribution_id !== distributionId
    );
    saveDrafts(next);
    setDrafts(next);
  }, []);

  return {
    drafts,
    loadDrafts,
    persistDraft,
    removeDraft,
  };
};