import { AlertTriangle, CheckCircle2, Circle, Clock3, XCircle } from 'lucide-react';

const STATUS_ICON = {
  passed: CheckCircle2,
  in_progress: Clock3,
  needs_review: AlertTriangle,
  blocked: XCircle,
  not_started: Circle,
};

const STATUS_CLASS = {
  passed: 'border-success/30 bg-success/10 text-success',
  in_progress: 'border-primary/30 bg-primary/10 text-primary',
  needs_review: 'border-warning/35 bg-warning/10 text-warning',
  blocked: 'border-destructive/35 bg-destructive/10 text-destructive',
  not_started: 'border-border bg-muted/35 text-muted-foreground',
};

export default function WorkflowPhaseTracker({ workflow, onPhaseClick }) {
  if (!workflow?.phases?.length) return null;

  return (
    <section className="rounded-lg border border-border/70 bg-card/80 p-3 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Workflow</p>
          <h2 className="font-display text-sm font-semibold text-foreground">{workflow.workflow_name}</h2>
        </div>
        <span className="rounded-full border border-border bg-background px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          {workflow.overall_status?.replace(/_/g, ' ') || 'in review'}
        </span>
      </div>
      <div className="grid gap-1.5 md:grid-cols-4 xl:grid-cols-8">
        {workflow.phases.map((phase, index) => {
          const Icon = STATUS_ICON[phase.status] || Circle;
          return (
            <button
              key={phase.id}
              type="button"
              onClick={() => onPhaseClick?.(phase)}
              className={`min-h-16 rounded-md border px-2 py-2 text-left transition hover:bg-muted/35 ${STATUS_CLASS[phase.status] || STATUS_CLASS.not_started}`}
              title={phase.summary || phase.label}
            >
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide">
                <Icon className="h-3.5 w-3.5" />
                {index + 1}
              </div>
              <div className="mt-1 text-xs font-semibold leading-tight text-foreground">{phase.label}</div>
            </button>
          );
        })}
      </div>
    </section>
  );
}