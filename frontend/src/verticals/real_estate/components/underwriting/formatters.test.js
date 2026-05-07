import { describe, expect, it } from 'vitest';
import { getRentCompCoverage } from './formatters';

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
