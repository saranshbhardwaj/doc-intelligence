import { useState } from 'react';
import { AlertTriangle, CheckCircle2, ChevronDown, Info } from 'lucide-react';
import { buildMemoPreflightItems } from './memoPreflightUtils';

function toneClasses(tone) {
  if (tone === 'danger') return 'border-destructive/25 bg-destructive/10 text-destructive';
  if (tone === 'warning') return 'border-warning/25 bg-warning/10 text-uw-risk';
  if (tone === 'success') return 'border-success/25 bg-success/10 text-success';
  return 'border-border/60 bg-background/70 text-muted-foreground';
}

function iconForTone(tone) {
  if (tone === 'success') return CheckCircle2;
  if (tone === 'warning' || tone === 'danger') return AlertTriangle;
  return Info;
}

export default function MemoPreflightPanel(props) {
  const [expanded, setExpanded] = useState(false);
  const items = buildMemoPreflightItems(props);
  const severityRank = { danger: 0, warning: 1, neutral: 2, success: 3 };
  const sortedItems = [...items].sort((a, b) => (severityRank[a.tone] ?? 2) - (severityRank[b.tone] ?? 2));
  const visibleItems = expanded ? sortedItems : sortedItems.slice(0, 3);

  return (
    <div className="border-b border-border/70 bg-background/50 px-5 py-3 sm:px-6">
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
              Committee review flags
            </p>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Key assumptions the committee reader will expect to see reconciled.
            </p>
          </div>
          {sortedItems.length > 3 ? (
            <button
              type="button"
              onClick={() => setExpanded((value) => !value)}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border/70 bg-background/70 px-3 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground"
            >
              {expanded ? 'Show fewer' : 'Show all flags'}
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`} />
            </button>
          ) : null}
        </div>
        {visibleItems.length ? (
          <div className={`grid gap-2 ${expanded ? 'md:grid-cols-2' : 'lg:grid-cols-3'}`}>
            {visibleItems.map((item) => {
              const Icon = iconForTone(item.tone);
              return (
                <div key={item.title} className={`rounded-xl border px-3 py-2 ${toneClasses(item.tone)}`}>
                  <div className="flex items-start gap-2">
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-foreground">{item.title}</p>
                      <p className={`mt-0.5 text-xs leading-5 text-muted-foreground ${expanded ? '' : 'line-clamp-2'}`}>
                        {item.detail}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">
            No committee review flags
          </p>
        )}
      </div>
    </div>
  );
}
