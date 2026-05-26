import { describe, expect, it } from 'vitest';
import {
  canDownloadMemo,
  canDeleteMemo,
  formatMemoDate,
  getLatestMemo,
  getMemoStatusTone,
  getMemoWarningLabel,
} from './memoHistoryUtils';

describe('memoHistoryUtils', () => {
  it('selects the highest version as the latest memo', () => {
    const memos = [
      { id: 'memo-1', version: 1 },
      { id: 'memo-4', version: 4 },
      { id: 'memo-2', version: 2 },
    ];

    expect(getLatestMemo(memos)).toEqual({ id: 'memo-4', version: 4 });
  });

  it('formats memo metadata for history rows', () => {
    expect(formatMemoDate('2026-05-22T14:30:00Z')).toBe('May 22, 2026');
    expect(getMemoWarningLabel(['missing sponsor', 'market note omitted'])).toBe('2 warnings');
    expect(getMemoWarningLabel([])).toBeNull();
  });

  it('maps memo status to visual tones and download eligibility', () => {
    expect(getMemoStatusTone('complete')).toBe('success');
    expect(getMemoStatusTone('failed')).toBe('danger');
    expect(getMemoStatusTone('running')).toBe('active');
    expect(getMemoStatusTone('queued')).toBe('neutral');

    expect(canDownloadMemo({ status: 'complete' })).toBe(true);
    expect(canDownloadMemo({ status: 'failed' })).toBe(false);
  });

  it('allows delete only for terminal memos', () => {
    expect(canDeleteMemo({ status: 'complete' })).toBe(true);
    expect(canDeleteMemo({ status: 'failed' })).toBe(true);
    expect(canDeleteMemo({ status: 'pending' })).toBe(false);
    expect(canDeleteMemo({ status: 'generating' })).toBe(false);
  });
});
