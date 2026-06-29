import { AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { flattenGateFindings, getBlockingGateSummary } from './workflowUtils';

export default function MemoReadinessGatePanel({ workflow, onFindingClick }) {
  if (!workflow) return null;

  const findings = flattenGateFindings(workflow.gates || []).slice(0, 5);
  const blockers = getBlockingGateSummary(workflow);
  const requiresOverride = workflow.memo_generation?.requires_override;
  const disabled = !workflow.memo_generation?.allowed && !requiresOverride;

  return (
    <aside className="rounded-lg border border-border/70 bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Memo readiness</p>
          <h3 className="mt-1 text-sm font-semibold text-foreground">
            {requiresOverride ? 'Override required' : disabled ? 'Not ready' : 'Ready to generate'}
          </h3>
        </div>
        {requiresOverride ? <AlertTriangle className="h-4 w-4 text-warning" /> : disabled ? <XCircle className="h-4 w-4 text-destructive" /> : <CheckCircle2 className="h-4 w-4 text-success" />}
      </div>

      {blockers.length ? (
        <p className="mt-2 text-xs text-muted-foreground">Blocking gates: {blockers.join(', ')}</p>
      ) : null}

      <div className="mt-3 space-y-2">
        {findings.map((finding) => (
          <button
            key={`${finding.gate_id}-${finding.id}`}
            type="button"
            onClick={() => onFindingClick?.(finding)}
            className="w-full rounded-md border border-border/70 bg-background/70 p-2 text-left text-xs hover:bg-muted/40"
          >
            <div className="font-semibold text-foreground">{finding.gate_label}</div>
            <div className={finding.severity === 'critical' ? 'text-destructive' : 'text-muted-foreground'}>
              {finding.message}
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}