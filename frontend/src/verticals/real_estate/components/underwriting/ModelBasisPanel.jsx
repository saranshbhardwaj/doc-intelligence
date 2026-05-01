import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';
import { formatCompactCurrency, formatPercent } from './formatters';

function BasisCard({ label, value, tone = 'neutral', detail, children }) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
          <p className="mt-2 font-display text-lg font-semibold text-foreground">{value}</p>
        </div>
        <UnderwritingStatusBadge tone={tone}>{value === 'Missing' ? 'Review' : 'Basis'}</UnderwritingStatusBadge>
      </div>
      {detail ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail}</p> : null}
      {children ? <div className="mt-3">{children}</div> : null}
    </div>
  );
}

function getExpenseTone(expenseBasis) {
  if (!expenseBasis) return 'danger';
  if (expenseBasis.source === 'line_items' || expenseBasis.source === 'expense_ratio_current') return 'success';
  if (expenseBasis.source === 'expense_ratio_pro_forma' || expenseBasis.source === 'om_noi') return 'warning';
  return 'danger';
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
        detail={revenueBasis?.detail}
      />
      <BasisCard
        label="Expense basis"
        value={expenseLabel}
        tone={getExpenseTone(expenseBasis)}
        detail={expenseDetail}
      >
        {expenseBasis?.ratio != null ? (
          <p className="text-xs font-medium text-muted-foreground">Ratio used: {formatPercent(expenseBasis.ratio)}</p>
        ) : null}
      </BasisCard>
      <BasisCard
        label="NOI hierarchy"
        value={isOmNoiMode ? 'OM-stated NOI' : 'Modeled NOI'}
        tone={isOmNoiMode ? 'warning' : 'success'}
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
        detail={unitMixSource?.detail}
      />
      <BasisCard
        label="Rent comp coverage"
        value={rentCompCoverage?.label || 'No comp view'}
        tone={rentCompCoverage?.tone || 'neutral'}
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
