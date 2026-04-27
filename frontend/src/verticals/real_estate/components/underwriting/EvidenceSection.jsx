import { AlertTriangle, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';

export default function EvidenceSection({ show, onToggle, evidenceItems, onOpenSource }) {
  return (
    <UnderwritingSection
      eyebrow="Source evidence"
      title="Key assumptions and source support"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && evidenceItems.length > 0 ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {evidenceItems.map((item) => {
            const confidence = Number(item.citation?.confidence);
            const confidenceLabel = Number.isFinite(confidence) && confidence > 0
              ? `${Math.round(confidence * 100)}% confidence`
              : 'Cited input';
            const isDerived = item.citation?.is_derived;
            const docTypeLabel = isDerived
              ? 'Derived'
              : ({ om: 'Offering Memo', rent_roll: 'Rent Roll', t12: 'T-12' }[item.citation?.doc_type] || item.citation?.doc_type || 'Document');
            const subtitleText = item.note ?? (isDerived ? 'Computed from extracted fields' : confidenceLabel);

            return (
              <div key={item.key} className="underwriting-quote-card">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{item.label}</p>
                    <p className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground">{item.value}</p>
                  </div>
                  <UnderwritingStatusBadge tone={isDerived ? 'warning' : 'active'}>{docTypeLabel}</UnderwritingStatusBadge>
                </div>

                <p className="mt-3 text-xs font-medium uppercase tracking-[0.16em] text-uw-citation">{subtitleText}</p>
                {isDerived && item.citation?.formula
                  ? <p className="mt-2 font-mono text-sm leading-6 text-muted-foreground">{item.citation.formula}</p>
                  : item.citation?.source_text
                    ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{'"'}{item.citation.source_text}{'"'}</p>
                    : null}

                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {item.citation?.entries?.map((entry, index) => (
                    <Button
                      key={`${item.key}-${entry.citation}-${index}`}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 rounded-full px-3 text-xs"
                      onClick={() => onOpenSource(entry)}
                    >
                      {entry.page ? `Open page ${entry.page}` : 'Open source'}
                    </Button>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      ) : show ? (
        <div className="underwriting-empty py-12">
          <AlertTriangle className="h-6 w-6 text-primary" />
          <p className="mt-3 text-sm text-muted-foreground">
            This run does not have extracted field citations yet. Run AI extraction on an OM, rent roll, or T-12 to populate source-backed assumptions.
          </p>
        </div>
      ) : null}
    </UnderwritingSection>
  );
}
