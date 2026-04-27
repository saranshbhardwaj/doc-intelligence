/**
 * StressTestTable
 * Stress scenario comparison table with DSCR highlighting
 */
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
  rent_growth_zero: 'Rent Growth → 0%',
  opex_plus_10pct: 'OpEx +10%',
  exit_cap_plus_25bps: 'Exit Cap +25bps',
};

export default function StressTestTable({ stressTests }) {
  if (!stressTests || stressTests.length === 0) {
    return <div className="text-sm text-muted-foreground">No stress tests available</div>;
  }

  const formatPercent = (value) => {
    if (value === null || value === undefined) return '—';
    return `${(value * 100).toFixed(1)}%`;
  };

  const formatX = (value) => {
    if (value === null || value === undefined) return '—';
    return `${value.toFixed(2)}×`;
  };

  const getDscrCellClass = (dscr) => {
    if (dscr === null || dscr === undefined) return '';
    if (dscr < 1.15) return 'bg-destructive/20 font-bold text-destructive';
    if (dscr < 1.25) return 'bg-destructive/10 text-destructive';
    return '';
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead className="text-xs uppercase tracking-wide">Scenario</TableHead>
            <TableHead className="text-xs uppercase tracking-wide text-right">IRR</TableHead>
            <TableHead className="text-xs uppercase tracking-wide text-right">CoC</TableHead>
            <TableHead className="text-xs uppercase tracking-wide text-right">DSCR</TableHead>
            <TableHead className="text-xs uppercase tracking-wide text-right">EM</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {stressTests.map((scenario) => {
            const isBase = scenario.scenario_key === 'base';
            return (
              <TableRow
                key={scenario.scenario_key}
                className={isBase ? 'font-semibold bg-muted/30' : ''}
              >
                <TableCell className="text-sm">
                  {SCENARIO_LABELS[scenario.scenario_key] ||
                    scenario.label}
                </TableCell>
                <TableCell className="text-sm text-right">
                  {formatPercent(scenario.irr)}
                </TableCell>
                <TableCell className="text-sm text-right">
                  {formatPercent(scenario.cash_on_cash)}
                </TableCell>
                <TableCell
                  className={`text-sm text-right ${getDscrCellClass(
                    scenario.dscr_year_one
                  )}`}
                >
                  {formatX(scenario.dscr_year_one)}
                </TableCell>
                <TableCell className="text-sm text-right">
                  {formatX(scenario.equity_multiple)}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
