import { X } from 'lucide-react';
import { getEffectiveMissingItems, getHandoffBlockers, getReadinessAction, getUnderwritingReadiness, isLibraryDocumentReady } from '../../utils/acquisitionWorkspace';

function formatMoney(value) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export default function HandoffPreviewDialog({ open, candidate, onClose, onCreate, isCreating = false, error = null, isPrototype = true }) {
  if (!open || !candidate) return null;
  const blockers = getHandoffBlockers(candidate, { isPrototype });
  const canCreate = blockers.length === 0;
  const readiness = getUnderwritingReadiness(candidate, { isPrototype });
  const readinessAction = getReadinessAction(readiness);
  const effectiveMissingItems = getEffectiveMissingItems(candidate);

  const rows = [
    ['Deal name', candidate.name],
    ['Asset type', 'Self-storage'],
    ['Address', candidate.address || '—'],
    ['Purchase price', formatMoney(candidate.facts?.price)],
    ['Units/spaces', candidate.facts?.units ?? '—'],
    ['Rentable sqft', candidate.facts?.rentableSqft?.toLocaleString() ?? '—'],
    ['Going-in cap', candidate.facts?.capRate == null ? '—' : `${(candidate.facts.capRate * 100).toFixed(2)}%`],
  ];

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
      <div className="absolute inset-x-4 top-8 mx-auto max-w-3xl rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Create Self-Storage Underwrite</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Preview the underwriting run that will be created from this sourced candidate.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close handoff preview">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="grid max-h-[75vh] gap-4 overflow-y-auto p-4 md:grid-cols-2">
          <section className="rounded-md border border-border/70 bg-background/70 p-3">
            <h3 className="text-sm font-semibold text-foreground">Candidate</h3>
            <p className="mt-2 text-sm font-medium text-foreground">{candidate.name}</p>
            <p className="text-sm text-muted-foreground">{candidate.address || 'Address not detected'}</p>
            <p className="mt-2 text-xs text-muted-foreground">Source: {candidate.sourceName}</p>
            <p className="text-xs text-muted-foreground">Self-storage confidence: {candidate.assetClassConfidence}%</p>
          </section>
          <section className="rounded-md border border-border/70 bg-background/70 p-3">
            <h3 className="text-sm font-semibold text-foreground">Underwriting Readiness</h3>
            <p className="mt-2 text-sm text-muted-foreground">{readiness.detail}</p>
            <p className="mt-2 text-xs font-medium text-foreground">Next: {readiness.nextAction}</p>
            {blockers.length ? (
              <ul className="mt-2 space-y-1 text-sm text-uw-risk">
                {blockers.map((blocker) => <li key={blocker}>Needs action: {blocker}</li>)}
              </ul>
            ) : null}
            {error ? <p className="mt-2 text-sm text-destructive">{error}</p> : null}
          </section>
          <section className="rounded-md border border-border/70 bg-background/70 p-3 md:col-span-2">
            <h3 className="text-sm font-semibold text-foreground">Prefilled Run Fields</h3>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              {rows.map(([label, value]) => (
                <div key={label} className="flex justify-between gap-3 rounded-md bg-muted/40 px-2 py-1.5 text-sm">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="text-right font-medium text-foreground">{value}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section className="rounded-md border border-border/70 bg-background/70 p-3">
            <h3 className="text-sm font-semibold text-foreground">Documents</h3>
            <div className="mt-2 space-y-2 text-sm">
              {candidate.documents.map((doc) => (
                <div key={doc.id} className="flex justify-between gap-3">
                  <span className="text-muted-foreground">{doc.name}</span>
                  <span className="font-medium text-foreground">{doc.status === 'available' || isLibraryDocumentReady(doc) ? 'Ready' : 'Processing'}</span>
                </div>
              ))}
            </div>
          </section>
          <section className="rounded-md border border-border/70 bg-background/70 p-3">
            <h3 className="text-sm font-semibold text-foreground">Source Evidence</h3>
            <ul className="mt-2 space-y-1.5 text-sm text-muted-foreground">
              {candidate.evidence.map((item) => (
                <li key={`${item.label}-${item.source}`}>✓ {item.detail}</li>
              ))}
              {effectiveMissingItems.length ? <li>! Missing: {effectiveMissingItems.join(', ')}</li> : null}
            </ul>
          </section>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <button type="button" onClick={onClose} className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
            Close
          </button>
          <button
            type="button"
            disabled={!canCreate || isCreating}
            onClick={onCreate}
            className={`rounded-md px-3 py-2 text-sm font-medium ${
              !canCreate
                ? 'bg-muted text-muted-foreground opacity-70'
                : 'bg-primary text-primary-foreground disabled:opacity-70'
            }`}
          >
            {isCreating ? 'Creating Run...' : readinessAction.label}
          </button>
        </div>
      </div>
    </div>
  );
}