/**
 * AIPrefilledField
 * Wraps inputs with AI citation highlighting.
 * Shows sparkles icon and source button if citation exists.
 * If onOpenSource is provided the caller owns the source panel; otherwise
 * falls back to the embedded CitationDrawer (sheet).
 */
import { useState } from 'react';
import { Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import CitationDrawer from './CitationDrawer';

export default function AIPrefilledField({
  label,
  inputId,
  citation = null,
  unit = null,
  onOpenSource = null,
  children,
}) {
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const confidence = Number(citation?.confidence);
  const confidenceLabel = Number.isFinite(confidence) && confidence > 0
    ? `${Math.round(confidence * 100)}% confidence`
    : null;

  const handleSourceClick = () => {
    if (onOpenSource) {
      onOpenSource(citation);
    } else {
      setIsDrawerOpen(true);
    }
  };

  return (
    <div data-cited={citation ? 'true' : 'false'} className="underwriting-citation-field">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <label htmlFor={inputId} className="text-sm font-medium text-foreground">
              {label}
            </label>
            {citation && (
              <Sparkles className="h-3.5 w-3.5 text-uw-citation" />
            )}
          </div>
          {citation ? (
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] font-medium uppercase tracking-[0.16em] text-uw-citation">
              <span>AI populated</span>
              {confidenceLabel ? <span className="text-muted-foreground">{confidenceLabel}</span> : null}
            </div>
          ) : null}
        </div>
        {citation && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 rounded-full px-3 text-[11px] font-semibold text-uw-citation hover:bg-background/70"
            onClick={handleSourceClick}
          >
            Source
          </Button>
        )}
      </div>

      {unit && (
        <div className="mb-3 mt-2 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{unit}</span>
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        {children}
      </div>

      {/* Fallback sheet drawer — only used when caller doesn't own the panel */}
      {!onOpenSource && (
        <CitationDrawer
          isOpen={isDrawerOpen}
          onClose={() => setIsDrawerOpen(false)}
          citation={citation}
        />
      )}
    </div>
  );
}
