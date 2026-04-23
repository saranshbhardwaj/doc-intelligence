import { HelpCircle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export function UnderwritingStatusBadge({ tone = 'neutral', className, children }) {
  return (
    <span data-tone={tone} className={cn('underwriting-status-pill', className)}>
      {children}
    </span>
  );
}

export function UnderwritingSection({
  eyebrow,
  title,
  description,
  action = null,
  className,
  contentClassName,
  children,
}) {
  return (
    <section className={cn('underwriting-panel p-5 sm:p-6', className)}>
      {(eyebrow || title || description || action) && (
        <div className="mb-5 flex flex-col gap-3 border-b border-border/60 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            {eyebrow ? <p className="underwriting-kicker">{eyebrow}</p> : null}
            {title ? <h2 className="underwriting-section-heading mt-1">{title}</h2> : null}
            {description ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{description}</p> : null}
          </div>
          {action ? <div className="shrink-0">{action}</div> : null}
        </div>
      )}
      <div className={cn(contentClassName)}>{children}</div>
    </section>
  );
}

export function UnderwritingEmptyState({
  icon: Icon,
  title,
  description,
  action = null,
  className,
}) {
  return (
    <div className={cn('underwriting-empty', className)}>
      {Icon ? (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-primary">
          <Icon className="h-6 w-6" />
        </div>
      ) : null}
      <h3 className="font-display text-lg font-semibold text-foreground">{title}</h3>
      {description ? <p className="mt-2 max-w-md text-sm leading-6 text-muted-foreground">{description}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function UnderwritingMetricCard({
  label,
  value,
  detail,
  formula,
  tone = 'default',
  status = null,
  className,
}) {
  return (
    <div data-tone={tone} className={cn('underwriting-metric', className)}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
            {formula ? (
              <TooltipProvider delayDuration={200}>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button type="button" className="text-muted-foreground/60 hover:text-muted-foreground focus:outline-none">
                      <HelpCircle className="h-3.5 w-3.5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-[280px] text-xs leading-5">
                    {formula}
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : null}
          </div>
          <p className="mt-3 font-display text-2xl font-semibold tracking-tight text-foreground sm:text-[2rem]">
            {value}
          </p>
        </div>
        {status}
      </div>
      {detail ? <p className="mt-2 text-sm leading-6 text-muted-foreground">{detail}</p> : null}
    </div>
  );
}
