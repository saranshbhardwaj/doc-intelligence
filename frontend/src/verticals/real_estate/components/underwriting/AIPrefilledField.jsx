import { useState } from 'react';
import { ArrowUpRight } from 'lucide-react';
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
  const confidenceTone = !Number.isFinite(confidence) || confidence <= 0
    ? 'neutral'
    : confidence >= 0.9
      ? 'high'
      : confidence >= 0.7
        ? 'mid'
        : 'low';

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
            <label
              htmlFor={inputId}
              className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-600"
            >
              {label}
            </label>
            {citation ? <span className={`uw-confidence-dot uw-confidence-dot-${confidenceTone}`} /> : null}
          </div>
        </div>
        {citation && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 rounded-full px-3 text-[11px] font-semibold text-uw-citation hover:bg-background/70"
            onClick={handleSourceClick}
          >
            <ArrowUpRight className="mr-1 h-3.5 w-3.5" />
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
