import { AlertTriangle } from 'lucide-react';
import { UnderwritingSection } from './UnderwritingUI';
import SourceSupportActions from './SourceSupportActions';

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
        {discrepancies.map((discrepancy) => (
          <div
            key={discrepancy.field}
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
