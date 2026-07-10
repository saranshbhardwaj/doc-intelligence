import { AlertCircle, CheckCircle2, FileText, Library, Trash2, UploadCloud } from 'lucide-react';
import {
  formatCandidateLocation,
  getCandidateConfidence,
  getExistingUnderwritingRunId,
  getReadinessAction,
  getUnderwritingReadiness,
  isLibraryDocumentReady,
  labelFromSnake,
} from '../../utils/acquisitionWorkspace';

function formatMoney(value) {
  if (value == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

function formatPct(value) {
  if (value == null) return '—';
  return `${(value * 100).toFixed(2)}%`;
}

function badgeToneClass(tone) {
  if (tone === 'strong') return 'border-primary/25 bg-primary/5 text-primary';
  if (tone === 'likely' || tone === 'ready') return 'border-green-500/20 bg-green-500/10 text-green-600';
  if (tone === 'review' || tone === 'warning') return 'border-amber-500/20 bg-amber-500/10 text-amber-700';
  return 'border-border/70 bg-muted text-muted-foreground';
}

export default function CandidateDetailPanel({
  candidate,
  onCreateCandidate,
  onDetachDocument,
  onOpenHandoff,
  onOpenLibrary,
  onOpenUnderwritingRun,
  detachingDocumentId = null,
  isPrototype = false,
}) {
  if (!candidate) {
    return (
      <section className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Select a candidate to review source evidence and handoff readiness.
      </section>
    );
  }

  const confidence = getCandidateConfidence(candidate);
  const readiness = getUnderwritingReadiness(candidate, { isPrototype });
  const readinessAction = getReadinessAction(readiness);
  const showDocumentLibraryAction = !['attach_library', 'view_library_status'].includes(readinessAction.intent);
  const handlePrimaryAction = () => {
    switch (readinessAction.intent) {
      case 'create_candidate':
        onCreateCandidate?.();
        return;
      case 'attach_library':
      case 'view_library_status':
        onOpenLibrary?.();
        return;
      case 'open_underwriting_run': {
        const runId = getExistingUnderwritingRunId(candidate);
        if (runId) {
          onOpenUnderwritingRun?.(runId);
        }
        return;
      }
      case 'create_underwriting_run':
      case 'review_candidate':
      default:
        onOpenHandoff?.();
    }
  };

  return (
    <section className="rounded-lg border border-border bg-card p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Selected Candidate</p>
          <h2 className="mt-1 text-xl font-semibold text-foreground">{candidate.name}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{formatCandidateLocation(candidate)} · {candidate.sourceName}</p>
        </div>
        <div className="flex flex-wrap gap-1.5 sm:justify-end">
          <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${badgeToneClass(confidence.tone)}`}>
            {confidence.label} · {confidence.percent}%
          </span>
          <span className={`w-fit rounded-full border px-3 py-1 text-xs font-semibold ${badgeToneClass(readiness.tone)}`}>
            {readiness.label}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        <section className="rounded-md border border-border/70 bg-background/70 p-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Candidate Confidence</h3>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${badgeToneClass(confidence.tone)}`}>
              {confidence.label}
            </span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{confidence.detail}</p>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {confidence.reasons.map((reason) => <li key={reason}>• {reason}</li>)}
          </ul>
        </section>

        <section className="rounded-md border border-border/70 bg-background/70 p-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Underwriting Readiness</h3>
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${badgeToneClass(readiness.tone)}`}>
              {readiness.label}
            </span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{readiness.detail}</p>
          <p className="mt-2 text-xs font-medium text-foreground">Next: {readiness.nextAction}</p>
        </section>
      </div>

      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <DetailBlock title="Facts" rows={[
          ['Purchase price', formatMoney(candidate.facts?.price)],
          ['Units/spaces', candidate.facts?.units ?? '—'],
          ['Storage units', candidate.facts?.storageUnits ?? '—'],
          ['Non-storage', candidate.facts?.nonStorageUnits ?? '—'],
          ['Rentable sqft', candidate.facts?.rentableSqft?.toLocaleString() ?? '—'],
          ['Going-in cap', formatPct(candidate.facts?.capRate)],
        ]} />
        <div className="rounded-md border border-border/70 bg-background/70 p-3">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-foreground">Documents</h3>
            <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Library linked</span>
          </div>
          <div className="mt-2 space-y-2">
            {candidate.documents.map((doc) => {
              const ready = doc.status === 'available' || isLibraryDocumentReady(doc);
              const Icon = ready ? CheckCircle2 : AlertCircle;
              const activeDocumentId = doc.document_id || doc.documentId || doc.id;
              const isDetaching = detachingDocumentId === activeDocumentId;
              return (
                <div key={doc.id} className="flex items-start gap-2 text-xs">
                  <Icon className={`mt-0.5 h-4 w-4 ${ready ? 'text-success' : 'text-uw-risk'}`} />
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-foreground">{labelFromSnake(doc.type || doc.doc_type)}</p>
                    <p className="truncate text-muted-foreground">{doc.name}</p>
                  </div>
                  {onDetachDocument ? (
                    <button
                      type="button"
                      onClick={() => onDetachDocument(doc)}
                      disabled={isPrototype || isDetaching}
                      title={`Remove ${doc.name || 'document'}`}
                      aria-label={`Remove ${doc.name || 'document'}`}
                      className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
            {showDocumentLibraryAction ? (
              <button
                type="button"
                onClick={onOpenLibrary}
                className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-muted-foreground"
              >
                <Library className="h-3.5 w-3.5" /> Attach from Library
              </button>
            ) : null}
            <button
              type="button"
              disabled
              title="Upload-to-Library will use the existing Library upload, Azure Document Intelligence parsing, chunking, and embedding pipeline."
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-border bg-muted/50 px-2.5 py-1.5 text-xs font-medium text-muted-foreground opacity-75"
            >
              <UploadCloud className="h-3.5 w-3.5" /> Upload to Library
            </button>
          </div>
        </div>
        <div className="rounded-md border border-border/70 bg-background/70 p-3">
          <h3 className="text-sm font-semibold text-foreground">Evidence</h3>
          <div className="mt-2 space-y-2">
            {candidate.evidence.map((item) => (
              <div key={`${item.label}-${item.source}`} className="flex gap-2 text-xs">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div>
                  <p className="font-medium text-foreground">{item.label} · {(item.confidence * 100).toFixed(0)}%</p>
                  <p className="leading-5 text-muted-foreground">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={handlePrimaryAction} className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground">
          {readinessAction.label}
        </button>
        <button type="button" className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
          Request Missing Docs
        </button>
        <button type="button" className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
          Watch
        </button>
        <button type="button" className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
          Archive
        </button>
      </div>
    </section>
  );
}

function DetailBlock({ title, rows }) {
  return (
    <div className="rounded-md border border-border/70 bg-background/70 p-3">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <dl className="mt-2 space-y-1.5 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-3">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-right font-medium text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}