import { describe, expect, it } from 'vitest';
import { buildMemoPreflightItems, sourceLabel } from './MemoPreflightPanel';

describe('sourceLabel', () => {
  it('uses analyst-facing labels for missing and default sources', () => {
    expect(sourceLabel(null)).toBe('Default assumption');
    expect(sourceLabel({ is_default: true })).toBe('Default assumption');
    expect(sourceLabel({ doc_type: 'om' })).toBe('OM stated');
    expect(sourceLabel({ doc_type: 'om', is_computed: true })).toBe('OM computed');
  });
});

describe('buildMemoPreflightItems', () => {
  it('labels uncited exit cap and rent growth as default assumptions', () => {
    const items = buildMemoPreflightItems({
      persistedInputs: {
        exit: { exit_cap_rate: 0.0861 },
        operational: { rent_growth_pct: 0.03 },
      },
      artifact: {},
      currentRun: { irr: 0.133 },
      sourceCitations: {},
      unitMixSummary: {},
      stressTests: [],
      prioritizedWarnings: [],
    });

    expect(items.find((item) => item.title.startsWith('Exit cap source'))?.title).toBe('Exit cap source: Default assumption');
    expect(items.find((item) => item.title.startsWith('Rent growth source'))?.title).toBe('Rent growth source: Default assumption');
  });
});