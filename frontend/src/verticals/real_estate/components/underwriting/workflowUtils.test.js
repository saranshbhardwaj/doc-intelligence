import { describe, expect, it } from 'vitest';
import { getBlockingGateSummary, sortGateFindings } from './workflowUtils';

describe('workflowUtils', () => {
  it('sorts critical findings before warnings and info', () => {
    const findings = [
      { id: 'w', severity: 'warning' },
      { id: 'i', severity: 'info' },
      { id: 'c', severity: 'critical' },
    ];

    expect(sortGateFindings(findings).map((item) => item.id)).toEqual(['c', 'w', 'i']);
  });

  it('summarizes blocking gate ids from workflow state', () => {
    const workflow = {
      gates: [
        { id: 'data_quality', label: 'Data Quality', status: 'passed' },
        { id: 'investment_screen', label: 'Investment Screen', status: 'blocked' },
      ],
      memo_generation: { blocking_gate_ids: ['investment_screen'] },
    };

    expect(getBlockingGateSummary(workflow)).toEqual(['Investment Screen']);
  });
});