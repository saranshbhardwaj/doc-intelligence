import { ChevronDown, ChevronUp } from 'lucide-react';
import { UnderwritingStatusBadge } from './UnderwritingUI';
import {
  formatCompactCurrency,
  formatMultiple,
  formatPercent,
} from './formatters';

function docTone(docType) {
  if (docType === 't12' || docType === 'rent_roll') return 'success';
  if (docType === 'om') return 'warning';
  if (docType === 'derived') return 'active';
  return 'neutral';
}

function docLabel(docType) {
  if (docType === 't12') return 'T-12';
  if (docType === 'rent_roll') return 'Rent Roll';
  if (docType === 'om') return 'OM';
  if (docType === 'derived') return 'Derived';
  return null;
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
            : <span className="italic text-muted-foreground/60">not stated</span>}
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
          alert ? 'text-uw-risk' : 'text-foreground'
        }`}
      >
        {value ?? '—'}
      </span>
    </div>
  );
}

function WarningPill({ warning }) {
  const tone = warning.severity === 'critical'
    ? 'border-destructive/30 bg-destructive/5 text-destructive'
    : warning.severity === 'warning'
    ? 'border-uw-risk/30 bg-uw-risk/5 text-uw-risk'
    : 'border-border/50 bg-muted/40 text-muted-foreground';
  const text = warning.message.length > 100
    ? `${warning.message.slice(0, 97)}…`
    : warning.message;
  return (
    <div className={`rounded-lg border px-2.5 py-2 text-xs leading-5 ${tone}`}>
      {text}
    </div>
  );
}

export default function TrustPanel({
  // Collapsed strip
  verdictTone,
  verdictLabel,
  revenueBasis,
  warningCount,
  // Col 1 — source data
  persistedInputs,
  artifact,
  currentRentPerDoor,
  currentExpenseRatio,
  proFormaExpenseRatio,
  expenseBasis,
  capitalStructure,
  omStatedNoi,
  sourceCitations,
  rentCompCoverage,
  // Col 2 — model outputs
  currentRun,
  noiBridgeDeltaPct,
  noiBridgeAlert,
  breakEvenOccupancyPct,
  // Col 3 — warnings
  prioritizedWarnings,
  // Toggle state
  expanded,
  onToggle,
}) {
  const occupancy = artifact?.rent_roll_data?.summary?.occupancy_pct;

  const expenseRatioValue = currentExpenseRatio ?? proFormaExpenseRatio;
  const expenseRatioDocType =
    currentExpenseRatio != null
      ? expenseBasis?.source === 'expense_ratio_current' || expenseBasis?.source === 'line_items'
        ? 't12'
        : 'derived'
      : 'om';

  const revenueBasisDocType =
    revenueBasis?.source === 't12' ? 't12'
    : revenueBasis?.source === 'rent_roll' ? 'rent_roll'
    : revenueBasis?.source === 'om' ? 'om'
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
          <UnderwritingStatusBadge tone={revenueBasis.tone}>
            {revenueBasis.label}
          </UnderwritingStatusBadge>
        ) : null}
        <UnderwritingStatusBadge tone={warningCount > 0 ? 'warning' : 'neutral'}>
          {warningCount > 0
            ? `⚠ ${warningCount} warning${warningCount === 1 ? '' : 's'}`
            : 'No warnings'}
        </UnderwritingStatusBadge>
        <button
          type="button"
          onClick={onToggle}
          className="ml-auto flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80"
        >
          Trust summary
          {expanded
            ? <ChevronUp className="h-3.5 w-3.5" />
            : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Expanded 3-column grid */}
      {expanded && (
        <div className="grid grid-cols-1 gap-3 px-4 pb-4 sm:px-6 md:grid-cols-3">

          {/* Col 1: What came from docs */}
          <div className="rounded-xl border border-border/50 bg-card/80 p-3">
            <p className="underwriting-kicker mb-2">What came from docs</p>
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
              label="Occupancy"
              value={occupancy != null ? formatPercent(occupancy) : null}
              docType={occupancy != null ? 'rent_roll' : null}
            />
            <SourceRow
              label="Avg rent / door"
              value={formatCompactCurrency(currentRentPerDoor)}
              docType={sourceCitations?.avg_in_place_rent_per_unit_monthly?.doc_type}
            />
            <SourceRow
              label="Expense ratio"
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
            <SourceRow
              label="Rent comp coverage"
              value={rentCompCoverage?.label ?? null}
              docType={
                rentCompCoverage?.tone === 'success' ? 't12'
                : rentCompCoverage?.tone === 'warning' ? 'om'
                : null
              }
            />
          </div>

          {/* Col 2: What the model used */}
          <div className="rounded-xl border border-border/50 bg-card/80 p-3">
            <p className="underwriting-kicker mb-2">What the model used</p>
            <MetricRow label="IRR" value={formatPercent(currentRun?.irr)} />
            <MetricRow label="Cash-on-cash" value={formatPercent(currentRun?.cash_on_cash)} />
            <MetricRow label="Equity multiple" value={formatMultiple(currentRun?.equity_multiple)} />
            <MetricRow label="DSCR yr 1" value={formatMultiple(currentRun?.dscr_year_one)} />
            <MetricRow label="NOI yr 1" value={formatCompactCurrency(currentRun?.noi_year_one)} />
            <MetricRow
              label="NOI vs OM stated"
              value={noiBridgeDisplay}
              alert={noiBridgeAlert}
            />
            <MetricRow label="Break-even occ" value={formatPercent(breakEvenOccupancyPct)} />
            <MetricRow label="Cap rate yr 1" value={formatPercent(currentRun?.cap_rate_year_one)} />
            <MetricRow label="Expense basis" value={expenseBasis?.label ?? null} />
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
