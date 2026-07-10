import { Search } from 'lucide-react';
import {
  formatCandidateLocation,
  getCandidateConfidence,
  getUnderwritingReadiness,
  labelFromSnake,
} from '../../utils/acquisitionWorkspace';

function formatMoney(value) {
  if (value == null) return 'Price n/a';
  return `$${(value / 1_000_000).toFixed(value >= 10_000_000 ? 1 : 2)}M`;
}

function formatCap(value) {
  if (value == null) return 'cap n/a';
  return `${(value * 100).toFixed(2)} cap`;
}

function confidenceToneClass(tone) {
  if (tone === 'strong') return 'border-primary/25 bg-primary/5 text-primary';
  if (tone === 'likely') return 'border-green-500/20 bg-green-500/10 text-green-600';
  if (tone === 'review') return 'border-amber-500/20 bg-amber-500/10 text-amber-700';
  return 'border-border/70 bg-muted text-muted-foreground';
}

function readinessToneClass(tone) {
  if (tone === 'ready') return 'border-green-500/20 bg-green-500/10 text-green-600';
  if (tone === 'warning') return 'border-amber-500/20 bg-amber-500/10 text-amber-700';
  return 'border-border/70 bg-muted text-muted-foreground';
}

export default function CandidateQueue({ candidates, filters, onFiltersChange, selectedId, onSelect, isPrototype = false }) {
  return (
    <section className="rounded-lg border border-border bg-card p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Prioritized Candidates</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">Ranked by readiness, confidence, and priority.</p>
        </div>
        <span className="text-xs text-muted-foreground">{candidates.length} visible</span>
      </div>
      <div className="mb-3 grid gap-2 md:grid-cols-3">
        <label className="relative md:col-span-3">
          <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <input
            value={filters.query}
            onChange={(event) => onFiltersChange({ ...filters, query: event.target.value })}
            placeholder="Search deal, market, broker..."
            className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-3 text-sm text-foreground outline-none"
          />
        </label>
        <select
          value={filters.sourceType}
          onChange={(event) => onFiltersChange({ ...filters, sourceType: event.target.value })}
          className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          <option value="all">All sources</option>
          <option value="gmail">Gmail</option>
          <option value="outlook">Outlook</option>
          <option value="public_api">Public API</option>
          <option value="private_api">Private API</option>
          <option value="manual_upload">Manual upload</option>
        </select>
        <select
          value={filters.status}
          onChange={(event) => onFiltersChange({ ...filters, status: event.target.value })}
          className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          <option value="all">All statuses</option>
          <option value="ready_to_underwrite">Ready</option>
          <option value="needs_docs">Needs docs</option>
          <option value="needs_review">Needs review</option>
          <option value="watchlist">Watchlist</option>
          <option value="in_underwriting">In underwriting</option>
          <option value="not_relevant">Not relevant</option>
        </select>
        <select
          value={filters.minConfidence}
          onChange={(event) => onFiltersChange({ ...filters, minConfidence: Number(event.target.value) })}
          className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
        >
          <option value={0}>Any confidence</option>
          <option value={70}>70%+</option>
          <option value={80}>80%+</option>
          <option value={90}>90%+</option>
        </select>
      </div>
      <div className="space-y-2">
        {candidates.map((candidate) => {
          const confidence = getCandidateConfidence(candidate);
          const readiness = getUnderwritingReadiness(candidate, { isPrototype });
          return (
          <button
            key={candidate.id}
            type="button"
            onClick={() => onSelect(candidate.id)}
            className={`w-full rounded-md border p-3 text-left transition-colors ${
              selectedId === candidate.id
                ? 'border-primary/40 bg-primary/5'
                : 'border-border/70 bg-background/70 hover:border-primary/25'
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-foreground">{candidate.name}</p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{candidate.sourceName} · {formatCandidateLocation(candidate)}</p>
              </div>
              <div className="flex shrink-0 flex-col items-end gap-1">
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${confidenceToneClass(confidence.tone)}`}>
                  {confidence.label}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${readinessToneClass(readiness.tone)}`}>
                  {readiness.label}
                </span>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-muted-foreground">
              <span className="rounded-full bg-muted px-2 py-0.5">SS {confidence.percent}%</span>
              <span className="rounded-full bg-muted px-2 py-0.5">{labelFromSnake(candidate.status)}</span>
              <span className="rounded-full bg-muted px-2 py-0.5">{formatMoney(candidate.facts?.price)}</span>
              <span className="rounded-full bg-muted px-2 py-0.5">{candidate.facts?.units || 'units n/a'} units/spaces</span>
              <span className="rounded-full bg-muted px-2 py-0.5">{formatCap(candidate.facts?.capRate)}</span>
            </div>
          </button>
          );
        })}
      </div>
    </section>
  );
}