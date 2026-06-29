import { useState } from 'react';
import { AlertCircle, AlertTriangle, ChevronDown, Info } from 'lucide-react';
import { UnderwritingStatusBadge } from './UnderwritingUI';
import {
  formatCompactCurrency,
  formatMultiple,
  formatPercent,
} from './formatters';

function docTone(docType) {
  if (docType === 't12' || docType === 'rent_roll') return 'success';
  if (docType === 'om_computed') return 'active';
  if (docType === 'om') return 'warning';
  if (docType === 'derived') return 'active';
  return 'neutral';
}

function docLabel(docType) {
  if (docType === 't12') return 'T-12 actual';
  if (docType === 'rent_roll') return 'Rent roll actual';
  if (docType === 'om_computed') return 'OM computed';
  if (docType === 'om') return 'OM stated';
  if (docType === 'derived') return 'Derived';
  return null;
}

function revenueBasisTone(source) {
  if (source === 't12' || source === 'rent_roll') return 'success';
  if (source === 'om' || source === 'om_noi') return 'warning';
  return 'active';
}

function SourceRow({ label, value, docType }) {
  const badge = docLabel(docType);
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/30 py-1.5 last:border-0">
      <span className="truncate text-xs text-muted-foreground">{label}</span>
      <div className="flex shrink-0 items-center gap-1.5">
        <span className="text-xs font-medium text-foreground tabular-nums">
          {value != null && value !== '—'
            ? value
            : <span className="text-muted-foreground">not stated</span>}
        </span>
        {badge ? (
          <UnderwritingStatusBadge tone={docTone(docType)} className="px-1.5 py-0.5 text-[9px]">
            {badge}
          </UnderwritingStatusBadge>
        ) : null}
      </div>
    </div>
  );
}

function MetricRow({ label, value, alert = false }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-border/30 py-1.5 last:border-0">
      <span className="truncate text-xs text-muted-foreground">{label}</span>
      <span
        className={`text-xs font-semibold tabular-nums ${
          alert ? 'text-warning' : 'text-foreground'
        }`}
      >
        {value ?? '—'}
      </span>
    </div>
  );
}

function expenseBasisDriverLabel(expenseBasis) {
  switch (expenseBasis?.source) {
    case 't12_line_items':
    case 'om_year1_line_items':
    case 'om_current_line_items':
    case 'om_pro_forma_line_items':
      return expenseBasis?.label || 'Detailed expense line items';
    case 't12_expense_ratio':
      return 'T-12 expense ratio';
    case 'om_current_expense_ratio':
      return 'Current OM expense ratio';
    case 'om_year1_expense_ratio':
      return 'Year 1 OM expense ratio';
    case 'om_pro_forma_expense_ratio':
      return 'OM pro-forma ratio';
    case 'om_noi':
      return 'OM-NOI quick screen';
    case 'missing':
      return 'Missing support';
    default:
      return expenseBasis?.label ?? null;
  }
}

function NoiBridgeMini({ bridge }) {
  const rows = Array.isArray(bridge?.rows) ? bridge.rows : [];
  if (!rows.length) return null;
  return (
    <div className="mt-2 rounded-lg border border-border/40 bg-background/50 p-2">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
        NOI bridge
      </p>
      {rows.map((row) => {
        const pct = row.delta_to_prior?.pct;
        const basisLabel = row.delta_to_prior?.basis_label;
        return (
          <div key={`${row.source_type}-${row.source_field}`} className="flex items-center justify-between gap-2 py-1">
            <span className="truncate text-[11px] text-muted-foreground">{row.label}</span>
            <div className="flex items-center gap-1.5">
              {pct != null ? (
                <span className={`text-[10px] font-semibold ${Math.abs(pct) > 0.1 ? 'text-warning' : 'text-muted-foreground'}`}>
                  {pct >= 0 ? '+' : ''}{(pct * 100).toFixed(0)}%{basisLabel ? ` vs ${basisLabel}` : ''}
                </span>
              ) : null}
              <span className="text-[11px] font-semibold text-foreground tabular-nums">
                {formatCompactCurrency(row.value)}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WarningPill({ warning }) {
  const [expanded, setExpanded] = useState(false);
  const tone = warning.severity === 'critical'
    ? 'border-destructive/30 bg-destructive/5 text-foreground'
    : warning.severity === 'warning'
    ? 'border-warning/35 bg-warning/10 text-foreground'
    : 'border-border/50 bg-muted/40 text-muted-foreground';
  const icon = warning.severity === 'critical'
    ? <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />
    : warning.severity === 'warning'
    ? <AlertTriangle className="h-3 w-3 shrink-0 text-warning" />
    : <Info className="h-3 w-3 shrink-0 text-muted-foreground" />;
  const isLong = warning.message.length > 140;
  const text = !expanded && isLong
    ? `${warning.message.slice(0, 137)}…`
    : warning.message;
  return (
    <button
      type="button"
      onClick={() => isLong && setExpanded((value) => !value)}
      className={`flex w-full items-start gap-1 rounded-lg border px-2.5 py-2 text-left text-xs leading-5 transition hover:bg-muted/30 ${tone} ${isLong ? 'cursor-pointer' : 'cursor-default'}`}
      aria-expanded={isLong ? expanded : undefined}
    >
      {icon}
      <span className="min-w-0 flex-1">{text}</span>
      {isLong ? <ChevronDown className={`mt-0.5 h-3 w-3 shrink-0 text-muted-foreground transition-transform ${expanded ? 'rotate-180' : ''}`} /> : null}
    </button>
  );
}

export default function TrustPanel({
  // Collapsed strip
  verdictTone,
  verdictLabel,
  revenueBasis,
  warningCount = 0,
  // Col 1 — source data
  persistedInputs,
  currentRentPerDoor,
  currentExpenseRatio,
  proFormaExpenseRatio,
  expenseBasis,
  capitalStructure,
  omStatedNoi,
  noiBridge,
  sourceCitations,
  rentCompCoverage,
  // Col 2 — model outputs
  currentRun,
  noiBridgeDeltaPct,
  noiBridgeAlert,
  breakEvenOccupancyPct,
  // Col 3 — warnings
  prioritizedWarnings = [],
  // Toggle state
  expanded,
  onToggle,
}) {
  const isOmNoiMode = expenseBasis?.source === 'om_noi';
  const avgRentDocType = sourceCitations?.avg_in_place_rent_per_unit_monthly?.doc_type
    ?? (currentRentPerDoor != null ? 'derived' : null);

  const modeledExpenseRatio = expenseBasis?.expense_ratio ?? expenseBasis?.ratio ?? null;
  const expenseRatioValue = modeledExpenseRatio ?? currentExpenseRatio ?? proFormaExpenseRatio;
  const expenseRatioDocType = expenseBasis?.period === 't12'
    ? 't12'
    : expenseBasis?.source?.startsWith?.('om_') && expenseBasis?.method === 'line_items'
      ? 'om_computed'
      : expenseBasis?.source?.startsWith?.('om_') || isOmNoiMode
        ? 'om'
        : modeledExpenseRatio != null
          ? 'derived'
          : null;

  const revenueBasisDocType =
    revenueBasis?.source === 't12' ? 't12'
    : revenueBasis?.source === 'rent_roll' ? 'rent_roll'
    : revenueBasis?.source === 'om' || revenueBasis?.source === 'om_noi' ? 'om'
    : null;

  const noiBridgeDisplay = noiBridgeDeltaPct != null
    ? `${noiBridgeDeltaPct > 0 ? '+' : ''}${(noiBridgeDeltaPct * 100).toFixed(0)}%`
    : null;

  return (
    <div className="-mx-4 sm:-mx-6 border-b border-border/50 bg-background/60">
      {/* Collapsed strip — always visible */}
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 sm:px-6">
        <UnderwritingStatusBadge tone={verdictTone}>{verdictLabel}</UnderwritingStatusBadge>
        {revenueBasis ? (
          <UnderwritingStatusBadge tone={revenueBasisTone(revenueBasis.source)}>
            {revenueBasis.label}
          </UnderwritingStatusBadge>
        ) : null}
        <UnderwritingStatusBadge tone={warningCount > 0 ? 'warning' : 'neutral'}>
          {`${warningCount} ${warningCount === 1 ? 'warning' : 'warnings'}`}
        </UnderwritingStatusBadge>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          className="ml-auto flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80"
        >
          {expanded ? 'Trust summary ▲' : 'Trust summary ▼'}
        </button>
      </div>

      {/* Expanded 3-column grid */}
      {expanded && (
        <div className="grid grid-cols-1 gap-3 px-4 pb-4 sm:px-6 md:grid-cols-3">

          {/* Col 1: Source support */}
          <div className="rounded-xl border border-border/50 bg-card/80 p-3">
            <p className="underwriting-kicker mb-2">Source support</p>
            <SourceRow
              label="Income basis"
              value={revenueBasis?.label}
              docType={revenueBasisDocType}
            />
            <SourceRow
              label="GPR"
              value={formatCompactCurrency(persistedInputs?.operational?.gross_potential_rent_annual)}
              docType={sourceCitations?.gross_potential_rent_annual?.doc_type}
            />
            <SourceRow
              label="Units"
              value={persistedInputs?.project?.num_units}
              docType={sourceCitations?.num_units?.doc_type}
            />
            <SourceRow
              label="Avg rent / door"
              value={formatCompactCurrency(currentRentPerDoor)}
              docType={avgRentDocType}
            />
            <SourceRow
              label="Model expense ratio"
              value={expenseRatioValue != null ? formatPercent(expenseRatioValue) : null}
              docType={expenseRatioDocType}
            />
            <SourceRow
              label="Purchase price"
              value={formatCompactCurrency(capitalStructure?.purchase_price)}
              docType={sourceCitations?.purchase_price?.doc_type}
            />
            <SourceRow
              label="Exit cap rate"
              value={
                persistedInputs?.exit?.exit_cap_rate != null
                  ? formatPercent(persistedInputs.exit.exit_cap_rate)
                  : null
              }
              docType={sourceCitations?.exit_cap_rate?.doc_type}
            />
            <SourceRow
              label="OM stated NOI"
              value={formatCompactCurrency(omStatedNoi)}
              docType={omStatedNoi != null ? 'om' : null}
            />
            <div className="flex items-center justify-between gap-2 border-b border-border/30 py-1.5 last:border-0">
              <span className="truncate text-xs text-muted-foreground">Rent comp coverage</span>
              {rentCompCoverage?.label ? (
                <UnderwritingStatusBadge tone={rentCompCoverage.tone || 'neutral'}>
                  {rentCompCoverage.label}
                </UnderwritingStatusBadge>
              ) : (
                <span className="text-muted-foreground">not stated</span>
              )}
            </div>
          </div>

          {/* Col 2: What the model used */}
          <div className="rounded-xl border border-border/50 bg-card/80 p-3">
            <p className="underwriting-kicker mb-2">What the model used</p>
            <MetricRow label="IRR" value={formatPercent(currentRun?.irr)} />
            <MetricRow label="Cash-on-cash" value={formatPercent(currentRun?.cash_on_cash)} />
            <MetricRow label="Equity multiple" value={formatMultiple(currentRun?.equity_multiple)} />
            <MetricRow label="DSCR yr 1" value={formatMultiple(currentRun?.dscr_year_one)} />
            <MetricRow label="NOI yr 1" value={formatCompactCurrency(currentRun?.noi_year_one)} />
            {noiBridge?.rows?.length ? (
              <NoiBridgeMini bridge={noiBridge} />
            ) : (
              <MetricRow
                label="NOI vs OM stated"
                value={noiBridgeDisplay}
                alert={noiBridgeAlert}
              />
            )}
            <MetricRow label="Break-even occ" value={formatPercent(breakEvenOccupancyPct)} />
            <MetricRow label="Cap rate yr 1" value={formatPercent(currentRun?.cap_rate_year_one)} />
            <MetricRow label="Expense basis" value={expenseBasisDriverLabel(expenseBasis)} />
          </div>

          {/* Col 3: What needs review */}
          <div className="rounded-xl border border-border/50 bg-card/80 p-3">
            <p className="underwriting-kicker mb-2">What needs review</p>
            {prioritizedWarnings.length === 0 ? (
              <p className="text-xs text-muted-foreground">No warnings — all checks passed.</p>
            ) : (
              <div className="flex flex-col gap-2">
                {prioritizedWarnings.map((w) => (
                  <WarningPill key={w.key} warning={w} />
                ))}
              </div>
            )}
            {prioritizedWarnings.length > 0 && (
              <p className="mt-3 text-[10px] text-muted-foreground/70">
                Go to Input tab to change assumptions and recalculate.
              </p>
            )}
          </div>

        </div>
      )}
    </div>
  );
}
