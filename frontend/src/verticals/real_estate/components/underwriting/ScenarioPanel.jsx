import { Loader2, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function ScenarioPanel({
  baseScenario,
  scenarioValues,
  onValueChange,
  onReset,
  scenarioResult,
  isScenarioLoading,
  currentRun,
}) {
  const fields = [
    { field: 'exit_cap_rate', label: 'Exit cap rate', unit: '%', min: 1, max: 15, step: 0.1 },
    { field: 'vacancy_credit_loss_pct', label: 'Vacancy & credit loss', unit: '%', min: 0, max: 40, step: 0.5 },
    { field: 'rent_growth_pct', label: 'Rent growth / yr', unit: '%', min: -5, max: 15, step: 0.25 },
    { field: 'interest_rate_pct', label: 'Interest rate', unit: '%', min: 2, max: 12, step: 0.1 },
    {
      field: 'purchase_price',
      label: 'Purchase price',
      unit: '$',
      min: Math.round((baseScenario.purchase_price || 1_000_000) * 0.5),
      max: Math.round((baseScenario.purchase_price || 10_000_000) * 1.5),
      step: 50000,
    },
  ];

  const resultMetrics = [
    { label: 'IRR', base: currentRun?.irr, scenario: scenarioResult?.irr, fmt: (v) => `${(v * 100).toFixed(1)}%`, unit: 'pp', scale: 100 },
    { label: 'Cash-on-Cash', base: currentRun?.cash_on_cash, scenario: scenarioResult?.cash_on_cash, fmt: (v) => `${(v * 100).toFixed(1)}%`, unit: 'pp', scale: 100 },
    { label: 'Equity Multiple', base: currentRun?.equity_multiple, scenario: scenarioResult?.equity_multiple, fmt: (v) => `${v.toFixed(2)}×`, unit: 'x', scale: 1 },
    { label: 'DSCR Year 1', base: currentRun?.dscr_year_one, scenario: scenarioResult?.dscr_year_one, fmt: (v) => `${v.toFixed(2)}×`, unit: 'x', scale: 1 },
    { label: 'NOI Year 1', base: currentRun?.noi_year_one, scenario: scenarioResult?.noi_year_one, fmt: (v) => `$${(v / 1000).toFixed(0)}K`, unit: '$', scale: 1 },
  ];

  return (
    <div className="mt-4 underwriting-panel p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Assumption what-if</p>
          <p className="mt-1 text-sm text-muted-foreground">Adjust assumptions to preview updated returns. Changes are not saved.</p>
        </div>
        <div className="flex items-center gap-2">
          {isScenarioLoading ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
          <Button variant="ghost" size="sm" onClick={onReset} disabled={Object.keys(scenarioValues).length === 0}>
            <RotateCcw className="mr-1.5 h-4 w-4" />
            Reset
          </Button>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1.4fr,1fr]">
        <div className="space-y-4">
          {fields.map(({ field, label, unit, min, max, step }) => {
            const baseVal = baseScenario[field];
            const currentVal = scenarioValues[field] ?? baseVal ?? (min + max) / 2;
            const isOverridden = scenarioValues[field] != null;
            return (
              <div key={field}>
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <label className="text-sm text-muted-foreground">
                    {label}
                    {isOverridden ? <span className="ml-2 text-xs font-medium text-primary">modified</span> : null}
                  </label>
                  <div className="flex items-center gap-1.5">
                    <input
                      type="number"
                      value={currentVal}
                      step={step}
                      min={min}
                      max={max}
                      onChange={(e) => {
                        const v = parseFloat(e.target.value);
                        if (!Number.isNaN(v)) onValueChange(field, v);
                      }}
                      className="w-24 rounded-lg border border-border bg-background px-2 py-1 text-right text-sm font-semibold text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <span className="text-sm text-muted-foreground">{unit}</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={currentVal}
                  onChange={(e) => onValueChange(field, parseFloat(e.target.value))}
                  className="underwriting-range"
                />
                <div className="mt-0.5 flex justify-between text-[11px] text-muted-foreground">
                  <span>{unit === '$' ? `$${(min / 1_000_000).toFixed(1)}M` : `${min}%`}</span>
                  {baseVal != null ? <span className="text-primary">base: {unit === '$' ? `$${(baseVal / 1_000_000).toFixed(1)}M` : `${baseVal.toFixed(1)}%`}</span> : null}
                  <span>{unit === '$' ? `$${(max / 1_000_000).toFixed(1)}M` : `${max}%`}</span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="space-y-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            {scenarioResult ? 'Scenario vs base' : 'Adjust sliders to preview'}
          </p>
          {resultMetrics.map(({ label, base, scenario, fmt, unit, scale }) => {
            const hasScenario = scenarioResult != null;
            const delta = hasScenario && base != null && scenario != null ? (scenario - base) * scale : null;
            const deltaStr = delta != null
              ? `${delta >= 0 ? '▲' : '▼'}${Math.abs(delta).toFixed(unit === '$' ? 0 : 2)}${unit === 'pp' ? 'pp' : ''}`
              : null;
            const deltaTone = delta == null ? '' : delta > 0 ? 'text-success' : delta < 0 ? 'text-destructive' : 'text-muted-foreground';
            return (
              <div key={label} className="flex items-center justify-between gap-3 rounded-2xl border border-border/60 bg-background/60 px-4 py-3">
                <span className="text-sm text-muted-foreground">{label}</span>
                <div className="text-right">
                  <span className="font-semibold text-foreground">
                    {hasScenario && scenario != null ? fmt(scenario) : base != null ? fmt(base) : '—'}
                  </span>
                  {deltaStr ? <span className={`ml-2 text-xs font-medium ${deltaTone}`}>{deltaStr}</span> : null}
                </div>
              </div>
            );
          })}
          {scenarioResult?.verdict_status ? (
            <div className={`rounded-2xl border px-4 py-3 text-sm font-semibold ${
              scenarioResult.verdict_status === 'worth_pursuing'
                ? 'border-success/25 bg-success/10 text-success'
                : scenarioResult.verdict_status === 'needs_review'
                  ? 'border-amber-500/25 bg-amber-500/10 text-amber-700 dark:text-amber-300'
                  : 'border-destructive/25 bg-destructive/10 text-destructive'
            }`}>
              Scenario verdict: {
                scenarioResult.verdict_status === 'worth_pursuing' ? 'Passes Screen'
                : scenarioResult.verdict_status === 'needs_review' ? 'Review Needed'
                : 'Below Screen'
              }
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
