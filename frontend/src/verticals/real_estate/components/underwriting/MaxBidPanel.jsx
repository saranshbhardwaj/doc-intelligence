import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { UnderwritingStatusBadge } from './UnderwritingUI';
import SourceSupportActions from './SourceSupportActions';
import {
  formatCompactCurrency,
  formatCurrency,
  formatMultiple,
  formatPercent,
} from './formatters';

const DEFAULT_CRITERIA = {
  target_irr: 0.15,
  target_cash_on_cash: 0.08,
  target_equity_multiple: 2.0,
  max_ltv: 0.8,
};

function buildPriceGrid(purchasePrice) {
  if (!purchasePrice || purchasePrice <= 0) return [];
  const multipliers = [0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3];
  return [...new Set([
    ...multipliers.map((m) => Math.round((purchasePrice * m) / 50000) * 50000),
    purchasePrice,
  ])]
    .filter((price) => price > 0)
    .sort((a, b) => a - b);
}

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function safePercent(value) {
  return isFiniteNumber(value) ? formatPercent(value) : '—';
}

function safeMultiple(value) {
  return isFiniteNumber(value) ? formatMultiple(value) : '—';
}

function getPointVerdict(point, criteria) {
  if (!point) return { status: 'missing', tone: 'neutral', label: 'No data' };
  const fails = [
    !isFiniteNumber(point.irr),
    !isFiniteNumber(point.cash_on_cash),
    !isFiniteNumber(point.equity_multiple),
    !isFiniteNumber(point.dscr_year_one),
    point.irr < criteria.target_irr,
    point.cash_on_cash < criteria.target_cash_on_cash,
    point.equity_multiple < criteria.target_equity_multiple,
    point.dscr_year_one < 1.25,
  ].some(Boolean);
  return fails
    ? { status: 'below_standards', tone: 'danger', label: 'Below Screen' }
    : { status: 'worth_pursuing', tone: 'success', label: 'Passes Screen' };
}

function highestPassingPrice(points, predicate) {
  const passing = points
    .filter((point) => point.purchase_price > 0 && predicate(point))
    .sort((a, b) => b.purchase_price - a.purchase_price);
  return passing[0]?.purchase_price ?? null;
}

function interpolatedMaxPrice(points, valueKey, target) {
  const sorted = points
    .filter((point) => point.purchase_price > 0 && isFiniteNumber(point[valueKey]))
    .sort((a, b) => a.purchase_price - b.purchase_price);

  if (sorted.length === 0 || !isFiniteNumber(target)) return null;

  let previous = null;
  for (const point of sorted) {
    const value = point[valueKey];
    if (value < target && previous && previous[valueKey] >= target) {
      const prevValue = previous[valueKey];
      const ratio = (target - prevValue) / (value - prevValue);
      return previous.purchase_price + ratio * (point.purchase_price - previous.purchase_price);
    }
    previous = point;
  }

  const highest = [...sorted]
    .filter((point) => point[valueKey] >= target)
    .sort((a, b) => b.purchase_price - a.purchase_price)[0];
  return highest?.purchase_price ?? null;
}

function constraintLabel(key) {
  switch (key) {
    case 'irr':
      return 'IRR';
    case 'cash_on_cash':
      return 'cash-on-cash';
    case 'equity_multiple':
      return 'equity multiple';
    case 'dscr_year_one':
      return 'DSCR';
    default:
      return 'the tightest screen';
  }
}

function pointLabel(point, purchasePrice) {
  if (!point) return '';
  if (Math.abs(point.purchase_price - purchasePrice) < 1) return 'Current ask';
  return point.purchase_price < purchasePrice ? 'Discount' : 'Premium';
}

export default function MaxBidPanel({
  purchasePrice,
  currentVerdictLabel,
  currentVerdictTone,
  currentNoi,
  criteria,
  getToken,
  runId,
  runSensitivityAnalysis,
  purchasePriceCitation,
  onOpenSource,
}) {
  const [points, setPoints] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  const normalizedCriteria = useMemo(() => ({
    ...DEFAULT_CRITERIA,
    ...(criteria || {}),
  }), [criteria]);

  const priceGrid = useMemo(() => buildPriceGrid(purchasePrice), [purchasePrice]);

  async function loadSensitivity() {
    if (!runId || priceGrid.length === 0) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await runSensitivityAnalysis(getToken, runId, priceGrid);
      setPoints(result.sensitivity_points || []);
    } catch (err) {
      console.error('Max bid sensitivity failed:', err);
      setError('Could not refresh purchase price sensitivity. Existing underwriting results are unchanged.');
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadSensitivity();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, priceGrid.join('|')]);

  const enrichedPoints = useMemo(() => points.map((point) => {
    const capRate = currentNoi && point.purchase_price > 0 ? currentNoi / point.purchase_price : null;
    const verdict = getPointVerdict(point, normalizedCriteria);
    return {
      ...point,
      cap_rate_year_one: capRate,
      verdict_status: verdict.status,
      verdict_label: verdict.label,
      verdict_tone: verdict.tone,
      price_label: pointLabel(point, purchasePrice),
    };
  }), [currentNoi, normalizedCriteria, points, purchasePrice]);

  const currentPoint = enrichedPoints.find((point) => Math.abs(point.purchase_price - purchasePrice) < 1);
  const currentReturnScreen = getPointVerdict(currentPoint, normalizedCriteria);
  const maxByIrr = interpolatedMaxPrice(enrichedPoints, 'irr', normalizedCriteria.target_irr);
  const maxByCashOnCash = interpolatedMaxPrice(enrichedPoints, 'cash_on_cash', normalizedCriteria.target_cash_on_cash);
  const maxByEquityMultiple = interpolatedMaxPrice(enrichedPoints, 'equity_multiple', normalizedCriteria.target_equity_multiple);
  const debtConstrainedPrice = interpolatedMaxPrice(enrichedPoints, 'dscr_year_one', 1.25);
  const constraints = [
    { key: 'irr', price: maxByIrr },
    { key: 'cash_on_cash', price: maxByCashOnCash },
    { key: 'equity_multiple', price: maxByEquityMultiple },
    { key: 'dscr_year_one', price: debtConstrainedPrice },
  ].filter((constraint) => constraint.price != null);
  const tightestConstraint = constraints.sort((a, b) => a.price - b.price)[0] ?? null;
  const suggestedMax = tightestConstraint?.price ?? null;
  const suggestedMin = suggestedMax ? Math.round((suggestedMax * 0.95) / 50000) * 50000 : null;

  if (!purchasePrice || purchasePrice <= 0) {
    return (
      <div className="underwriting-panel p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 text-warning" />
          <div>
            <p className="underwriting-kicker">Max bid</p>
            <p className="mt-1 font-display text-xl font-semibold text-foreground">Not enough data</p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Add a purchase price to calculate purchase-price sensitivity and max-bid guidance.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="underwriting-panel p-4 sm:p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <p className="underwriting-kicker">Max bid</p>
          <h2 className="underwriting-section-heading mt-1">Where does the deal still work?</h2>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
            Uses the same extracted and saved underwriting inputs, changing only purchase price.
            This does not overwrite assumptions.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UnderwritingStatusBadge tone={currentReturnScreen.tone}>Return screen: {currentReturnScreen.label}</UnderwritingStatusBadge>
          {isLoading ? <UnderwritingStatusBadge tone="active">Refreshing</UnderwritingStatusBadge> : null}
          <Button variant="outline" size="sm" onClick={loadSensitivity} disabled={isLoading || priceGrid.length === 0}>
            {isLoading ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-1.5 h-3.5 w-3.5" />}
            Refresh
          </Button>
        </div>
      </div>

      {error ? (
        <div className="mt-4 rounded-2xl border border-warning/25 bg-warning/10 px-4 py-3 text-sm text-warning">
          {error}
        </div>
      ) : null}

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Current ask</p>
          <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(purchasePrice)}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {currentPoint ? `${safePercent(currentPoint.irr)} IRR at ask` : 'Current price point queued'}
          </p>
        </div>
        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Break-even to target IRR</p>
          <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(maxByIrr)}</p>
          <p className="mt-1 text-xs text-muted-foreground">Approx. target {formatPercent(normalizedCriteria.target_irr)}</p>
        </div>
        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Break-even to target CoC</p>
          <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(maxByCashOnCash)}</p>
          <p className="mt-1 text-xs text-muted-foreground">Approx. target {formatPercent(normalizedCriteria.target_cash_on_cash)}</p>
        </div>
        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Debt-constrained price</p>
          <p className="mt-2 font-display text-2xl font-semibold text-foreground">{formatCompactCurrency(debtConstrainedPrice)}</p>
          <p className="mt-1 text-xs text-muted-foreground">Approx. DSCR ≥ 1.25×</p>
        </div>
        <div className={`rounded-2xl border p-4 ${suggestedMax && suggestedMax < purchasePrice ? 'border-warning/25 bg-warning/10' : 'border-success/25 bg-success/10'}`}>
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Suggested review range</p>
          <p className="mt-2 font-display text-2xl font-semibold text-foreground">
            {suggestedMin && suggestedMax ? `${formatCompactCurrency(suggestedMin)}-${formatCompactCurrency(suggestedMax)}` : '—'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {tightestConstraint ? `Constrained by ${constraintLabel(tightestConstraint.key)}` : 'Constrained by the tightest screen'}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-[0.9fr,1.6fr]">
        <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">Bid curve</p>
          {enrichedPoints.length > 0 ? (
            <div className="mt-3 h-[190px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={enrichedPoints}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                  <XAxis dataKey="purchase_price" tickFormatter={(v) => `$${(v / 1_000_000).toFixed(1)}M`} tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} tick={{ fontSize: 11 }} />
                  <ReferenceLine
                    y={normalizedCriteria.target_irr}
                    stroke="hsl(var(--muted-foreground))"
                    strokeDasharray="4 4"
                    label={{ value: `Target IRR ${formatPercent(normalizedCriteria.target_irr)}`, position: 'insideTopRight', fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                  />
                  <Tooltip
                    labelFormatter={(v) => formatCurrency(v)}
                    formatter={(v, name) => [name === 'irr' ? safePercent(v) : safeMultiple(v), name === 'irr' ? 'IRR' : 'Equity Multiple']}
                  />
                  <Bar dataKey="irr" radius={[4, 4, 0, 0]} name="IRR">
                    {enrichedPoints.map((entry) => (
                      <Cell
                        key={entry.purchase_price}
                        fill={entry.verdict_status === 'worth_pursuing' ? 'hsl(var(--uw-success))' : 'hsl(var(--uw-risk))'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="underwriting-empty py-10 text-sm text-muted-foreground">
              {isLoading ? 'Calculating price sensitivity...' : 'Sensitivity has not been calculated yet.'}
            </div>
          )}
        </div>

        <div className="overflow-x-auto rounded-2xl border border-border/60 bg-background/60 p-4">
          <table className="underwriting-table min-w-[820px]">
            <thead>
              <tr className="border-b border-border/70 text-left text-[11px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                <th className="pb-3">Price</th>
                <th className="pb-3">Read</th>
                <th className="pb-3 text-right">IRR</th>
                <th className="pb-3 text-right">Cash-on-Cash</th>
                <th className="pb-3 text-right">Equity Multiple</th>
                <th className="pb-3 text-right">DSCR Y1</th>
                <th className="pb-3 text-right">Cap Rate Y1</th>
                <th className="pb-3 text-right">Return Screen</th>
              </tr>
            </thead>
            <tbody>
              {enrichedPoints.map((point) => (
                <tr key={point.purchase_price} className="border-b border-border/50 last:border-b-0">
                  <td className="py-3 font-medium text-foreground">{formatCompactCurrency(point.purchase_price)}</td>
                  <td className="py-3 text-muted-foreground">{point.price_label || 'Scenario'}</td>
                  <td className="py-3 text-right font-medium text-foreground">{safePercent(point.irr)}</td>
                  <td className="py-3 text-right">{safePercent(point.cash_on_cash)}</td>
                  <td className="py-3 text-right">{safeMultiple(point.equity_multiple)}</td>
                  <td className="py-3 text-right">{safeMultiple(point.dscr_year_one)}</td>
                  <td className="py-3 text-right">{safePercent(point.cap_rate_year_one)}</td>
                  <td className="py-3 text-right">
                    <UnderwritingStatusBadge tone={point.verdict_tone}>{point.verdict_label}</UnderwritingStatusBadge>
                  </td>
                </tr>
              ))}
              {enrichedPoints.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-sm text-muted-foreground">
                    {isLoading ? 'Calculating purchase price sensitivity...' : 'No sensitivity points available.'}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mt-4">
        <SourceSupportActions
          citations={[purchasePriceCitation]}
          onOpenSource={onOpenSource}
          title="Purchase price support"
        />
      </div>
    </div>
  );
}
