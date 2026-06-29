import { useState } from 'react';
import { AlertTriangle, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UnderwritingSection, UnderwritingStatusBadge } from './UnderwritingUI';

export default function EvidenceSection({ show, onToggle, evidenceItems, onOpenSource }) {
  const [collapsedGroups, setCollapsedGroups] = useState({});
  const groupedEvidence = evidenceItems.reduce((groups, item) => {
    const category = item.category || 'Other';
    const existing = groups.find((group) => group.category === category);
    if (existing) {
      existing.items.push(item);
    } else {
      groups.push({ category, items: [item] });
    }
    return groups;
  }, []);
  const toggleGroup = (category) => {
    setCollapsedGroups((current) => ({
      ...current,
      [category]: !current[category],
    }));
  };

  return (
    <UnderwritingSection
      eyebrow="Source Audit"
      title="Core assumptions and extraction evidence"
      className="underwriting-panel-strong"
      action={
        <Button variant="ghost" size="sm" onClick={onToggle} className="gap-1.5 h-7 px-3 text-xs text-muted-foreground">
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${show ? '' : '-rotate-90'}`} />
          {show ? 'Collapse' : 'Expand'}
        </Button>
      }
    >
      {show && evidenceItems.length > 0 ? (
        <div className="space-y-4">
          {groupedEvidence.map((group) => {
            const isCollapsed = collapsedGroups[group.category] === true;

            return (
              <div key={group.category} className="rounded-2xl border border-border/60 bg-background/50 p-3 sm:p-4">
                <button
                  type="button"
                  onClick={() => toggleGroup(group.category)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{group.category}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{group.items.length} supported assumption{group.items.length === 1 ? '' : 's'}</p>
                  </div>
                  <ChevronDown className={`h-4 w-4 shrink-0 text-muted-foreground transition-transform ${isCollapsed ? '-rotate-90' : ''}`} />
                </button>

                {!isCollapsed ? (
                  <div className="mt-3 grid gap-3 lg:grid-cols-2">
                    {group.items.map((item) => {
                      const confidence = Number(item.citation?.confidence);
                      const confidenceLabel = Number.isFinite(confidence) && confidence > 0
                        ? `Extraction confidence ${Math.round(confidence * 100)}%`
                        : 'Cited input';
                      const isDerived = item.citation?.is_derived;
                      const isDefault = item.citation?.is_default;
                      const docTypeLabel = isDefault
                        ? 'Default assumption'
                        : isDerived
                        ? 'Derived from unit mix'
                        : ({ om: 'Offering Memo', rent_roll: 'Rent Roll', t12: 'T-12' }[item.citation?.doc_type] || item.citation?.doc_type || 'Document');
                      const subtitleText = item.note ?? (isDefault ? 'Defaulted assumption' : isDerived ? 'Computed from extracted fields' : confidenceLabel);
                      const badgeTone = isDefault || isDerived ? 'warning' : 'active';

                      return (
                        <div key={item.key} className="underwriting-quote-card">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{item.label}</p>
                              <p className="mt-2 font-display text-2xl font-semibold tracking-tight text-foreground">{item.value}</p>
                            </div>
                            <UnderwritingStatusBadge tone={badgeTone}>{docTypeLabel}</UnderwritingStatusBadge>
                          </div>

                          <p className="mt-3 text-xs font-medium uppercase tracking-[0.16em] text-uw-citation">{subtitleText}</p>
                          {isDefault ? (
                            <p className="mt-2 text-sm leading-6 text-muted-foreground">
                              {item.citation.selection_note || item.citation.formula || 'No source value was available; the model used its default assumption.'}
                            </p>
                          ) : isDerived && item.citation?.formula
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
                ) : null}
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
