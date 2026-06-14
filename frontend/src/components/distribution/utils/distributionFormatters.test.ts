import { describe, expect, it } from 'vitest';

import {
  formatDate,
  formatTime,
  getPriorityColor,
  getPriorityLabel,
  getStatusColor,
  getStatusLabel,
} from './distributionFormatters';

describe('distributionFormatters', () => {
  it.each([
    ['cito', 'CITO'],
    ['asap', 'Срочное'],
    ['normal', 'План'],
    ['', 'План'],
  ])('returns a readable priority label for %s', (priority, expected) => {
    expect(getPriorityLabel(priority)).toBe(expected);
  });

  it('returns fallback status label for empty values', () => {
    expect(getStatusLabel('')).toBe('—');
  });

  it.each([
    ['pending', 'Ожидает'],
    ['confirmed', 'Назначено'],
    ['signed', 'Выполнено'],
    ['custom', 'custom'],
  ])('returns a readable status label for %s', (status, expected) => {
    expect(getStatusLabel(status)).toBe(expected);
  });

  it('keeps known priority classes stable', () => {
    expect(getPriorityColor('cito')).toContain('amber');
    expect(getPriorityColor('asap')).toContain('blue');
    expect(getPriorityColor('normal')).toContain('slate');
  });

  it('keeps known status classes stable', () => {
    expect(getStatusColor('confirmed')).toContain('blue');
    expect(getStatusColor('signed')).toContain('blue');
    expect(getStatusColor('pending')).toContain('slate');
  });

  it('formats empty dates and times as dash', () => {
    expect(formatDate(null)).toBe('—');
    expect(formatTime(undefined)).toBe('—');
  });
});
