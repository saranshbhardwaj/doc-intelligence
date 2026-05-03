import { AlertTriangle } from 'lucide-react';
import { UnderwritingSection } from './UnderwritingUI';
import SourceSupportActions from './SourceSupportActions';
import { formatCompactCurrency, formatPercent } from './formatters';

const DOC_LABELS = {
  om: 'OM',
  t12: 'T-12',
  rent_roll: 'Rent roll',
  derived: 'Derived',
};

function formatDiscrepancyValue(field, value) {
  if (value == null) return 'not stated';
  if (Array.isArray(value)) return `${value.length} rows`;
  if (typeof value === 'object') return 'source table';
  if (typeof value !== 'number') return String(value);
  if (field.includes('occupancy') || field.includes('ratio') || field.includes('pct')) {
    return formatPercent(value);
  }
  if (
    field.includes('rent')
    || field.includes('gpr')
    || field.includes('noi')
    || field.includes('income')
    || field.includes('expense')
    || field.includes('tax')
    || field.includes('insurance')
    || field.includes('payroll')
    || field.includes('utilities')
    || field.includes('marketing')
  ) {
    return formatCompactCurrency(value);
  }
  return Number.isInteger(value) ? value.toLocaleString() : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function SourceComparison({ discrepancy }) {
  const sources = discrepancy.sources || [];
  return (
    <div className="mt-3 rounded-xl border border-border/40 bg-background/55 p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {sources.map((source, sourceIndex) => (
          <div key={`${source.doc_type}-${sourceIndex}`} className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              {DOC_LABELS[source.doc_type] || source.doc_type || 'Source'}
            </p>
            <p className="mt-0.5 truncate text-sm font-semibold text-foreground tabular-nums">
              {formatDiscrepancyValue(discrepancy.field, source.value)}
            </p>
          </div>
        ))}
        {discrepancy.model_used != null ? (
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-primary">
              Model used
            </p>
            <p className="mt-0.5 truncate text-sm font-semibold text-foreground tabular-nums">
              {formatDiscrepancyValue(discrepancy.field, discrepancy.model_used)}
            </p>
          </div>
        ) : null}
        {discrepancy.preferred_source ? (
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
              Preferred source
            </p>
            <p className="mt-0.5 truncate text-sm font-semibold text-foreground">
              {DOC_LABELS[discrepancy.preferred_source] || discrepancy.preferred_source}
            </p>
          </div>
        ) : null}
      </div>
      {discrepancy.reason ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">{discrepancy.reason}</p>
      ) : null}
    </div>
  );
}

export default function DiscrepanciesSection({ discrepancies, discrepancySupportByField, onOpenSource }) {
  if (!discrepancies.length) return null;

  return (
    <UnderwritingSection
      eyebrow="Review flags"
      title="Cross-document discrepancies"
      description="These mismatches do not change the verdict directly, but they are worth reconciling before final approval."
      className="underwriting-panel-strong"
    >
      <div className="grid gap-3 md:grid-cols-2">
        {discrepancies.map((discrepancy, index) => (
          <div
            key={`${discrepancy.field}-${index}`}
            className={`underwriting-panel p-4 ${
              discrepancy.severity === 'error'
                ? 'border-destructive/25 bg-destructive/10'
                : discrepancy.severity === 'warning'
                  ? 'border-warning/25 bg-warning/10'
                  : ''
            }`}
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-uw-risk" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-foreground">{discrepancy.field}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{discrepancy.note}</p>
                <SourceComparison discrepancy={discrepancy} />
                <SourceSupportActions
                  citations={discrepancySupportByField[discrepancy.field] || []}
                  onOpenSource={onOpenSource}
                  title="Trace to source"
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </UnderwritingSection>
  );
}
