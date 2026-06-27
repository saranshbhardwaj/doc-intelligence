import { describe, expect, it } from 'vitest';
import { buildPropertyTaxSupportRows, formatFailureGap, getRentCompCoverage } from './formatters';

describe('formatFailureGap', () => {
  it('formats return metric gaps with the right unit for the metric', () => {
    expect(formatFailureGap('cash_on_cash', -0.0037)).toBe('-37 bps');
    expect(formatFailureGap('irr', 0.0042)).toBe('+42 bps');
    expect(formatFailureGap('equity_multiple', -0.258)).toBe('-0.26×');
    expect(formatFailureGap('dscr_year_one', -0.07)).toBe('-0.07×');
    expect(formatFailureGap('ltv', 0.025)).toBe('+250 bps');
  });
});

describe('getRentCompCoverage', () => {
  it('separates exact size support from bucket-level support in size-only matching', () => {
    const unitMix = [
      { size: '5 x 10', standard_sqft: 50, climate_type: 'NC', unit_category: 'storage' },
      { size: '10 x 10', standard_sqft: 100, climate_type: 'NC', unit_category: 'storage' },
      { size: '8 x 15', standard_sqft: 120, climate_type: 'NC', unit_category: 'storage' },
      { size: '10 x 20', standard_sqft: 200, climate_type: 'NC', unit_category: 'storage' },
      { size: '10 x 30', standard_sqft: 300, climate_type: 'NC', unit_category: 'storage' },
    ];
    const rentComps = [
      { size: '5 x 10', asking_rent: 58 },
      { size: '10 x 10', asking_rent: 94 },
      { size: '10 x 15', asking_rent: 107 },
      { size: '10 x 20', asking_rent: 134 },
      { size: '5 x 10', asking_rent: 58, is_broker_market_average: true },
    ];
    const rentPositionAnalysis = [
      { bucket: 'small', climate_type: 'Mixed', match_basis: 'size_only', comp_count: 7, comp_average_rent: 58 },
      { bucket: 'medium', climate_type: 'Mixed', match_basis: 'size_only', comp_count: 7, comp_average_rent: 94 },
      { bucket: 'large', climate_type: 'Mixed', match_basis: 'size_only', comp_count: 12, comp_average_rent: 134 },
      { bucket: 'xlarge', climate_type: 'Mixed', match_basis: 'size_only', comp_count: 0, comp_average_rent: null },
    ];

    const coverage = getRentCompCoverage(unitMix, rentComps, rentPositionAnalysis);

    expect(coverage.label).toBe('3/4 rent buckets supported');
    expect(coverage.bucketMatched).toBe(3);
    expect(coverage.bucketTotal).toBe(4);
    expect(coverage.exactMatchedSizes).toBe(3);
    expect(coverage.exactTotalSizes).toBe(5);
    expect(coverage.exactLabel).toBe('3/5 exact sizes supported');
    expect(coverage.exactUnmatchedLabels).toEqual(['8 x 15', '10 x 30']);
    expect(coverage.compRows).toBe(4);
    expect(coverage.brokerBenchmarkRows).toBe(1);
  });
});

describe('buildPropertyTaxSupportRows', () => {
  it('treats mislabeled assessed value as value basis when tax mechanics require assessment ratio', () => {
    const rows = buildPropertyTaxSupportRows({
      property_tax_assessed_value: 1_250_000,
      property_tax_assessment_ratio: 0.11,
      property_tax_rate_per_assessed_dollar: 0.11161,
    }, 15_346);

    expect(rows.find((row) => row.key === 'property_tax_value_basis_amount')).toMatchObject({
      label: 'Appraised / tax value basis',
      value: '$1,250,000',
    });
    expect(rows.find((row) => row.key === 'property_tax_assessed_value')).toMatchObject({
      label: 'Implied taxable assessed value',
      value: '$137,500',
    });
    expect(rows.find((row) => row.key === 'implied_property_tax')).toMatchObject({
      rawValue: 15346.375,
      value: '$15,346',
      prefix: '$',
      help: 'Reconciles to the OM tax bill within rounding tolerance.',
    });
  });
});
