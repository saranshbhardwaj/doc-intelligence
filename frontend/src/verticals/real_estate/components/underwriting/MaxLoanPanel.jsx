import { useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UnderwritingStatusBadge } from './UnderwritingUI';
import { calculateMaxLoan } from '../../../../api/re-underwriting';
import { formatCompactCurrency } from './formatters';

const CONSTRAINT_LABELS = {
  dscr: 'DSCR',
  ltv: 'LTV',
  debt_yield: 'Debt Yield',
  noi_unavailable: 'NOI unavailable',
  rate_or_amort_missing: 'Rate / amortization missing',
  none: 'No active constraint',
};

function readDefaults(persistedInputs) {
  return {
    dscr_floor: persistedInputs?.criteria?.dscr_year_one_floor ?? 1.25,
    max_ltv: persistedInputs?.criteria?.max_ltv ?? 0.65,
    debt_yield_floor: 0.08,
  };
}

function toApiConstraints(values) {
  const payload = {};
  if (Number.isFinite(values.dscr_floor)) payload.dscr_floor = values.dscr_floor;
  if (Number.isFinite(values.max_ltv)) payload.max_ltv = values.max_ltv / 100;
  if (Number.isFinite(values.debt_yield_floor)) payload.debt_yield_floor = values.debt_yield_floor / 100;
  return payload;
}

export default function MaxLoanPanel({ runId, getToken, persistedInputs }) {
  const defaults = readDefaults(persistedInputs);
  const [values, setValues] = useState({
    dscr_floor: defaults.dscr_floor,
    max_ltv: defaults.max_ltv * 100,
    debt_yield_floor: defaults.debt_yield_floor * 100,
  });
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  const fetchResult = useCallback(async (next) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await calculateMaxLoan(getToken, runId, toApiConstraints(next));
      setResult(data);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || 'Max-loan calculation failed');
    } finally {
      setIsLoading(false);
    }
  }, [getToken, runId]);

  useEffect(() => {
    fetchResult(values);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleChange = useCallback((field, raw) => {
    const parsed = raw === '' ? NaN : Number(raw);
    setValues((prev) => {
      const next = { ...prev, [field]: parsed };
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => fetchResult(next), 400);
      return next;
    });
  }, [fetchResult]);

  const handleReset = useCallback(() => {
    const reset = {
      dscr_floor: defaults.dscr_floor,
      max_ltv: defaults.max_ltv * 100,
      debt_yield_floor: defaults.debt_yield_floor * 100,
    };
    setValues(reset);
    fetchResult(reset);
  }, [defaults.dscr_floor, defaults.max_ltv, defaults.debt_yield_floor, fetchResult]);

  const bindingLabel = result ? (CONSTRAINT_LABELS[result.binding_constraint] || result.binding_constraint) : '—';
  const bindingTone =
    !result ? 'neutral'
    : result.binding_constraint === 'noi_unavailable' || result.binding_constraint === 'rate_or_amort_missing' ? 'warning'
    : result.binding_constraint === 'none' ? 'neutral'
    : 'active';
  const deltaTone =
    !result ? 'neutral'
    : result.delta_vs_current < 0 ? 'danger'
    : 'success';
  const deltaText =
    !result ? '—'
    : result.delta_vs_current >= 0
      ? `+${formatCompactCurrency(result.delta_vs_current)} cushion vs. current loan`
      : `${formatCompactCurrency(result.delta_vs_current)} short of current loan`;

  return (
    <div className="underwriting-data-card p-4 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">Max Loan Sizing</p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Maximum supportable loan given lender constraints.
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={handleReset} className="gap-1.5 h-7 px-3 text-xs">
          <RefreshCw className="h-3.5 w-3.5" />
          Reset
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">DSCR floor</span>
          <div className="mt-1 flex items-center gap-1">
            <input
              type="number"
              step="0.01"
              min="0"
              value={Number.isFinite(values.dscr_floor) ? values.dscr_floor : ''}
              onChange={(e) => handleChange('dscr_floor', e.target.value)}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm tabular-nums"
            />
            <span className="text-xs text-muted-foreground">×</span>
          </div>
        </label>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">Max LTV</span>
          <div className="mt-1 flex items-center gap-1">
            <input
              type="number"
              step="0.5"
              min="0"
              max="100"
              value={Number.isFinite(values.max_ltv) ? values.max_ltv : ''}
              onChange={(e) => handleChange('max_ltv', e.target.value)}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm tabular-nums"
            />
            <span className="text-xs text-muted-foreground">%</span>
          </div>
        </label>
        <label className="block">
          <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">Debt yield floor</span>
          <div className="mt-1 flex items-center gap-1">
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={Number.isFinite(values.debt_yield_floor) ? values.debt_yield_floor : ''}
              onChange={(e) => handleChange('debt_yield_floor', e.target.value)}
              className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm tabular-nums"
            />
            <span className="text-xs text-muted-foreground">%</span>
          </div>
        </label>
      </div>

      <div className="flex flex-wrap items-baseline justify-between gap-3 mb-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">Max supportable loan</p>
          <p className="mt-0.5 font-display text-2xl font-semibold tracking-tight text-foreground tabular-nums">
            {isLoading
              ? <Loader2 className="inline h-5 w-5 animate-spin" aria-label="Calculating" />
              : result ? formatCompactCurrency(result.max_loan) : '—'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <UnderwritingStatusBadge tone={bindingTone}>{`Binding: ${bindingLabel}`}</UnderwritingStatusBadge>
          <UnderwritingStatusBadge tone={deltaTone}>{deltaText}</UnderwritingStatusBadge>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">
        {[
          { key: 'dscr', label: `DSCR @ ${Number.isFinite(values.dscr_floor) ? values.dscr_floor.toFixed(2) : '—'}×`, value: result?.max_loan_by_dscr },
          { key: 'ltv', label: `LTV @ ${Number.isFinite(values.max_ltv) ? `${values.max_ltv.toFixed(0)}%` : '—'}`, value: result?.max_loan_by_ltv },
          { key: 'debt_yield', label: `DY @ ${Number.isFinite(values.debt_yield_floor) ? `${values.debt_yield_floor.toFixed(1)}%` : '—'}`, value: result?.max_loan_by_debt_yield },
        ].map((row) => {
          const isBinding = result?.binding_constraint === row.key;
          return (
            <div
              key={row.key}
              className={`rounded-xl border px-3 py-2 ${isBinding ? 'border-primary/60 bg-primary/5' : 'border-border/50 bg-background/50'}`}
            >
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">{row.label}</p>
              <p className="mt-1 text-sm font-semibold text-foreground tabular-nums">
                {row.value == null ? '—' : formatCompactCurrency(row.value)}
                {isBinding ? <span className="ml-2 text-[10px] font-bold uppercase text-primary">← binding</span> : null}
              </p>
            </div>
          );
        })}
      </div>

      {result ? (
        <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
          <div>
            <span className="font-semibold text-foreground">{formatCompactCurrency(result.equity_required)}</span>
            <span className="ml-1">equity required at max loan</span>
          </div>
          <div>
            <span className="font-semibold text-foreground">{formatCompactCurrency(result.current_loan)}</span>
            <span className="ml-1">current loan in deal</span>
          </div>
        </div>
      ) : null}

      {result?.notes?.length ? (
        <div className="mt-3 rounded-lg border border-border/50 bg-muted/30 p-3">
          <div className="flex items-start gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <ul className="space-y-1">
              {result.notes.map((note, i) => <li key={i}>{note}</li>)}
            </ul>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      ) : null}
    </div>
  );
}
