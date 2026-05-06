import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import { formatCompactCurrency, formatPercent } from './formatters';

function BasisCard({ label, value, tone = 'neutral', badge, detail, children }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className="mt-2 font-display text-lg font-semibold text-foreground">{value}</p>
        </div>
        <UnderwritingStatusBadge tone={tone}>{badge || (value === 'Missing' ? 'Review' : 'Basis')}</UnderwritingStatusBadge>
      </div>
      {detail ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail}</p> : null}
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}

function getExpenseTone(expenseBasis) {
  if (!expenseBasis) return 'danger';
  if (expenseBasis.source === 't12_line_items' || expenseBasis.source === 'om_year1_line_items') return 'success';
  if (expenseBasis.method === 'line_items') return 'active';
  if (expenseBasis.source === 't12_expense_ratio') return 'success';
  if (expenseBasis.source?.includes?.('expense_ratio') || expenseBasis.source === 'om_noi') return 'warning';
  return 'danger';
}

function getRevenueBadge(revenueBasis) {
  if (!revenueBasis || revenueBasis.source === 'missing') return 'Review';
  if (revenueBasis.source === 'om' || revenueBasis.source === 'om_noi') return 'OM support';
  if (revenueBasis.source === 't12') return 'T-12 actuals';
  if (revenueBasis.source === 'rent_roll') return 'Rent roll';
  return 'Saved input';
}

function getUnitMixBadge(unitMixSource) {
  if (!unitMixSource || unitMixSource.source === 'missing') return 'Review';
  if (unitMixSource.source === 'rent_roll') return 'Rent roll';
  if (unitMixSource.source === 'om' || unitMixSource.source === 'om_partial' || unitMixSource.source === 'extracted') return 'OM extracted';
  if (unitMixSource.source === 'manual') return 'Saved input';
  return 'Source';
}

function getRentCoverageBadge(rentCompCoverage) {
  if (!rentCompCoverage || rentCompCoverage.totalBuckets === 0) return 'No comp view';
  if (rentCompCoverage.unmatchedCount > 0) return 'Partial match';
  return 'Matched';
}

function getExpenseRatioLabel(expenseBasis) {
  if (expenseBasis?.method === 'expense_ratio') return 'Ratio used';
  if (expenseBasis?.method === 'line_items') return 'Implied ratio';
  return 'Expense ratio';
}

export default function ModelBasisPanel({
  revenueBasis,
  expenseBasis,
  noiBasis,
  isOmNoiMode = false,
  unitMixSource,
  rentCompCoverage,
}) {
  const expenseLabel = expenseBasis?.label || 'Missing';
  const expenseDetail = expenseBasis?.reason || 'No line-item or ratio-based expense support was found.';
  const rentCoverageDetail = rentCompCoverage?.unmatchedCount > 0 && rentCompCoverage.unmatchedLabels.length > 0
    ? `${rentCompCoverage.detail} Unmatched: ${rentCompCoverage.unmatchedLabels.join(', ')}.`
    : rentCompCoverage?.detail;

  return (
    <UnderwritingSection
      eyebrow="Trust review"
      title="Model basis and source hierarchy"
      description="What the source says, what the model used, and where analyst judgment is still required."
      className="underwriting-panel-strong mt-4"
      contentClassName="grid gap-3 md:grid-cols-2 xl:grid-cols-5"
    >
      <BasisCard
        label="Revenue basis"
        value={revenueBasis?.label || 'Missing'}
        tone={revenueBasis?.tone || 'danger'}
        badge={getRevenueBadge(revenueBasis)}
        detail={revenueBasis?.detail}
      />
      <BasisCard
        label="Expense basis"
        value={expenseLabel}
        tone={getExpenseTone(expenseBasis)}
        badge={expenseBasis?.source === 'missing' ? 'Review' : 'Drives model'}
        detail={expenseDetail}
      >
        {(expenseBasis?.expense_ratio ?? expenseBasis?.ratio) != null ? (
          <p className="text-xs font-medium text-muted-foreground">
            {getExpenseRatioLabel(expenseBasis)}: {formatPercent(expenseBasis.expense_ratio ?? expenseBasis.ratio)}
          </p>
        ) : null}
      </BasisCard>
      <BasisCard
        label="NOI hierarchy"
        value={isOmNoiMode ? 'OM-stated NOI' : 'Modeled NOI'}
        tone={isOmNoiMode ? 'warning' : 'success'}
        badge="Model used"
        detail={isOmNoiMode
          ? 'OM-stated NOI is used for valuation in quick-screen mode. Upload a T-12 for income and expense support.'
          : 'Modeled NOI is used for valuation. OM-stated NOI is a reference benchmark only.'}
      >
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div>
            <p className="text-muted-foreground">{isOmNoiMode ? 'OM basis' : 'Modeled'}</p>
            <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(noiBasis?.modeledNoi)}</p>
          </div>
          <div>
            <p className="text-muted-foreground">{isOmNoiMode ? 'OM stated' : 'OM reference'}</p>
            <p className="mt-1 font-semibold text-foreground">{formatCompactCurrency(noiBasis?.omStatedNoi)}</p>
          </div>
        </div>
      </BasisCard>
      <BasisCard
        label="Unit mix source"
        value={unitMixSource?.label || 'Missing'}
        tone={unitMixSource?.tone || 'danger'}
        badge={getUnitMixBadge(unitMixSource)}
        detail={unitMixSource?.detail}
      />
      <BasisCard
        label="Rent comp coverage"
        value={rentCompCoverage?.label || 'No comp view'}
        tone={rentCompCoverage?.tone || 'neutral'}
        badge={getRentCoverageBadge(rentCompCoverage)}
        detail={rentCoverageDetail}
      >
        <p className="text-xs font-medium text-muted-foreground">
          {rentCompCoverage?.compRows ?? 0} comp rows reviewed
          {rentCompCoverage?.unmatchedCount != null ? ` · ${rentCompCoverage.unmatchedCount} unmatched` : ''}
        </p>
      </BasisCard>
    </UnderwritingSection>
  );
}
