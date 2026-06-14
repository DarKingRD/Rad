import { describe, expect, it } from 'vitest';

import { getCalendarDays, getMonthBounds, localDateString, monthStartString, todayString } from './doctorPortalUtils';

describe('doctorPortalUtils', () => {
  it('formats local dates as YYYY-MM-DD', () => {
    expect(localDateString(new Date(2026, 4, 9))).toBe('2026-05-09');
  });

  it('returns month bounds for the selected month', () => {
    expect(getMonthBounds(new Date(2026, 1, 15))).toEqual({
      date_from: '2026-02-01',
      date_to: '2026-02-28',
    });
  });

  it('builds a Monday-first calendar grid', () => {
    const days = getCalendarDays(new Date(2026, 4, 20));

    expect(days).toHaveLength(35);
    expect(localDateString(days[0])).toBe('2026-04-27');
    expect(localDateString(days[days.length - 1])).toBe('2026-05-31');
  });

  it('allows current-date helpers to be tested with injected dates', () => {
    const date = new Date(Date.UTC(2026, 4, 22, 10, 0, 0));

    expect(todayString(date)).toBe('2026-05-22');
    expect(monthStartString(date)).toBe('2026-05-01');
  });
});
