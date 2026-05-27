/**
 * StressTestTable
 * Stress scenario comparison table with row-level assumption detail.
 */
import { Fragment, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

const SCENARIO_LABELS = {
  base: 'Base Case',
  vacancy_plus_500bps: 'Vacancy +500bps',
  rent_growth_zero: 'Rent Growth -> 0%',
  opex_plus_10pct: 'OpEx +10%',
  exit_cap_plus_25bps: 'Exit Cap +25bps',
  exit_cap_plus_50bps: 'Exit Cap +0.50%',
  interest_rate_plus_100bps: 'Interest Rate +1.00%',
};

function formatPercent(value) {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function formatX(value) {
  if (value === null || value === undefined) return '—';
  return `${value.toFixed(2)}x`;
}

function formatAssumptionPercent(value) {
  if (value == null || !Number.isFinite(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function getDscrCellClass(dscr) {
  if (dscr === null || dscr === undefined) return '';
  if (dscr < 1.15) return 'bg-destructive/20 font-bold text-destructive';
  if (dscr < 1.25) return 'bg-destructive/10 text-destructive';
  return '';
}

function getScenarioDetail(scenarioKey, baseAssumptions) {
  const base = baseAssumptions || {};
  const rowsByKey = {
    base: [
      ['Changed', 'No stressed assumption. This is the saved underwriting case.'],
    ],
    vacancy_plus_500bps: [
      ['Changed', `Vacancy / credit loss from ${formatAssumptionPercent(base.vacancy_credit_loss_pct)} to ${formatAssumptionPercent((base.vacancy_credit_loss_pct ?? 0) + 0.05)}.`],
      ['Unchanged', 'Debt terms, exit cap, rent growth, and operating expense assumptions.'],
    ],
    rent_growth_zero: [
      ['Changed', `Recurring annual rent growth from ${formatAssumptionPercent(base.rent_growth_pct)} to 0.00%.`],
      ['Unchanged', 'Year-1 NOI, debt service, vacancy, expense load, and exit cap.'],
    ],
    opex_plus_10pct: [
      ['Changed', 'Operating expense load increased by 10%, including line items and selected expense-ratio inputs.'],
      ['Unchanged', 'Revenue, debt terms, and exit cap.'],
    ],
    exit_cap_plus_25bps: [
      ['Changed', `Exit cap from ${formatAssumptionPercent(base.exit_cap_rate)} to ${formatAssumptionPercent((base.exit_cap_rate ?? 0) + 0.0025)}.`],
      ['Unchanged', 'Year-1 cash flow and DSCR because only terminal sale value changes.'],
    ],
    exit_cap_plus_50bps: [
      ['Changed', `Exit cap from ${formatAssumptionPercent(base.exit_cap_rate)} to ${formatAssumptionPercent((base.exit_cap_rate ?? 0) + 0.005)}.`],
      ['Unchanged', 'Year-1 cash flow and DSCR because only terminal sale value changes.'],
    ],
    interest_rate_plus_100bps: [
      ['Changed', `Interest rate from ${formatAssumptionPercent(base.interest_rate_pct)} to ${formatAssumptionPercent((base.interest_rate_pct ?? 0) + 0.01)}.`],
      ['Unchanged', 'NOI, exit cap, vacancy, and rent growth.'],
    ],
  };
  return rowsByKey[scenarioKey] || [['Changed', 'See scenario label for the stressed assumption.']];
}

export default function StressTestTable({ stressTests, baseAssumptions }) {
  const [expandedKey, setExpandedKey] = useState(null);

  if (!stressTests || stressTests.length === 0) {
    return <div className="text-sm text-muted-foreground">No stress tests available</div>;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead className="text-xs uppercase tracking-wide">Scenario</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide">IRR</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide">CoC</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide">DSCR</TableHead>
            <TableHead className="text-right text-xs uppercase tracking-wide">EM</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {stressTests.map((scenario) => {
            const isBase = scenario.scenario_key === 'base';
            const isExpanded = expandedKey === scenario.scenario_key;
            const detailRows = getScenarioDetail(scenario.scenario_key, baseAssumptions);
            return (
              <Fragment key={scenario.scenario_key}>
                <TableRow className={isBase ? 'bg-muted/30 font-semibold' : ''}>
                  <TableCell className="text-sm">
                    <button
                      type="button"
                      className="flex items-center gap-1.5 text-left font-medium hover:text-primary"
                      onClick={() => setExpandedKey(isExpanded ? null : scenario.scenario_key)}
                    >
                      <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform ${isExpanded ? 'rotate-180' : '-rotate-90'}`} />
                      {SCENARIO_LABELS[scenario.scenario_key] || scenario.label}
                    </button>
                  </TableCell>
                  <TableCell className="text-right text-sm">{formatPercent(scenario.irr)}</TableCell>
                  <TableCell className="text-right text-sm">{formatPercent(scenario.cash_on_cash)}</TableCell>
                  <TableCell className={`text-right text-sm ${getDscrCellClass(scenario.dscr_year_one)}`}>
                    {formatX(scenario.dscr_year_one)}
                  </TableCell>
                  <TableCell className="text-right text-sm">{formatX(scenario.equity_multiple)}</TableCell>
                </TableRow>
                {isExpanded ? (
                  <TableRow className="bg-muted/20">
                    <TableCell colSpan={5} className="px-4 py-3">
                      <div className="grid gap-2 text-xs leading-5 text-muted-foreground sm:grid-cols-2">
                        {detailRows.map(([label, value]) => (
                          <div key={label} className="rounded-xl border border-border/60 bg-background/70 px-3 py-2">
                            <span className="font-semibold text-foreground">{label}: </span>
                            {value}
                          </div>
                        ))}
                      </div>
                    </TableCell>
                  </TableRow>
                ) : null}
              </Fragment>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
