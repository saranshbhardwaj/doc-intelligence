/**
 * DiscrepancyBanner
 * Amber warning banner for cross-document discrepancies
 */
import { useState } from 'react';
import { AlertTriangle, X } from 'lucide-react';

export default function DiscrepancyBanner({ discrepancy }) {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  return (
    <div className="underwriting-panel border-warning/25 bg-warning/10 p-3.5">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-warning" />

        <div className="min-w-0 flex-1">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-warning">
            Review flag
          </p>
          <p className="mt-1 text-sm font-semibold text-foreground">
            {discrepancy.field}
          </p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {discrepancy.note}
          </p>
        </div>

        <button
          onClick={() => setDismissed(true)}
          className="rounded-full p-1 text-muted-foreground transition-colors hover:bg-background/60 hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
