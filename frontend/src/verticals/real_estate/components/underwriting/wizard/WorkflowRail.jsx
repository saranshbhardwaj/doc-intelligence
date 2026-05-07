import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Sparkles,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import DiscrepancyBanner from '../DiscrepancyBanner';
import { UnderwritingStatusBadge } from '../UnderwritingUI';
import { DOC_SLOTS } from './wizardConfig';

function DocCard({ slot, selected, onOpen, onRemove, extracting }) {
  const Icon = slot.icon;

  return (
    <div className="underwriting-rail-card" data-active={selected ? 'true' : undefined}>
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${
          selected ? 'bg-primary/12 text-primary' : 'bg-muted/70 text-muted-foreground'
        }`}
        >
          <Icon className="h-4 w-4" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-foreground">{slot.label}</p>
            {slot.required ? <UnderwritingStatusBadge tone="warning">Required</UnderwritingStatusBadge> : null}
            {selected ? <CheckCircle2 className="h-3.5 w-3.5 text-uw-success" /> : null}
          </div>
          <p
            className="mt-1 max-w-full truncate text-xs leading-5 text-muted-foreground"
            title={selected ? selected.name : undefined}
          >
            {selected ? selected.name : slot.hint}
          </p>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        {selected ? (
          <button
            type="button"
            onClick={onRemove}
            disabled={extracting}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-destructive disabled:cursor-not-allowed disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Remove
          </button>
        ) : (
          <span className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">No document attached</span>
        )}

        <Button size="sm" variant={selected ? 'outline' : 'default'} onClick={onOpen} disabled={extracting}>
          {selected ? 'Change' : 'Select'}
        </Button>
      </div>
    </div>
  );
}

export default function WorkflowRail({
  selectedDocs,
  hasOmForExtraction,
  extraction,
  extractionDone,
  handleRunExtraction,
  isExtracting,
  projectName,
  currentRun,
  setDocPickerOpen,
  setSelectedDocs,
  citationCount,
  leftCollapsed,
  setLeftCollapsed,
}) {
  const attachedCount = Object.values(selectedDocs).filter(Boolean).length;
  const runProcessing = currentRun?.status === 'extracting' || currentRun?.status === 'calculating';
  const railProcessing = !extractionDone && Boolean(
    extraction.isProcessing
    || runProcessing
  );
  const progressValue = Math.max(0, Math.min(100, extraction.progress || (railProcessing ? 8 : extractionDone ? 100 : 0)));
  const extractionTitle = railProcessing
    ? 'Extracting assumptions'
    : extractionDone
      ? 'Inputs ready for review'
      : 'Draft assumptions with AI';
  const extractionCopy = railProcessing
    ? extraction.message || 'Reading source documents and mapping assumptions.'
    : extractionDone
      ? `${citationCount} cited field${citationCount === 1 ? '' : 's'} are ready for review.`
      : hasOmForExtraction
        ? 'Offering Memorandum attached. Run extraction when the deal name is set.'
        : 'Attach an Offering Memorandum to unlock extraction.';
  const extractionButtonLabel = railProcessing
    ? 'Running extraction'
    : extractionDone
      ? 'Re-run extraction'
      : 'Run extraction';
  const extractionReady = Boolean(hasOmForExtraction && projectName.trim());

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="doc-rail-header">
        {!leftCollapsed && (
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">
            Source Docs
          </span>
        )}
        <button
          onClick={() => setLeftCollapsed((v) => !v)}
          className="ml-auto flex h-7 w-7 items-center justify-center rounded-lg border border-border/50 bg-card text-muted-foreground shadow-sm transition-colors hover:bg-muted hover:text-foreground"
          title={leftCollapsed ? 'Expand panel' : 'Collapse panel'}
        >
          {leftCollapsed ? <ChevronRight className="h-3.5 w-3.5" /> : <ChevronLeft className="h-3.5 w-3.5" />}
        </button>
      </div>

      {leftCollapsed ? (
        <div className="flex flex-col items-center py-2">
          {DOC_SLOTS.map((slot) => {
            const Icon = slot.icon;
            const attached = Boolean(selectedDocs[slot.key]);
            return (
              <button
                key={slot.key}
                onClick={() => setDocPickerOpen(slot.key)}
                title={slot.label}
                className={`flex h-10 w-full items-center justify-center border-l-2 transition-colors ${
                  attached
                    ? 'border-l-primary bg-primary/5 text-primary'
                    : 'border-l-transparent text-muted-foreground hover:bg-muted/50'
                }`}
              >
                <Icon className="h-4 w-4" />
              </button>
            );
          })}
        </div>
      ) : (
        <>
          <div className="rail-extraction-panel" data-state={railProcessing ? 'processing' : extractionDone ? 'complete' : 'idle'}>
            <div className="rail-extraction-head">
              <div>
                <p className="rail-extraction-eyebrow">
                  {railProcessing ? 'Processing' : extractionDone ? 'Extraction complete' : 'AI drafting'}
                </p>
                <h3 className="rail-extraction-title">{extractionTitle}</h3>
              </div>
              {railProcessing ? (
                <span className="rail-extraction-percent">{progressValue}%</span>
              ) : extractionDone ? (
                <CheckCircle2 className="h-4 w-4 text-uw-success" />
              ) : (
                <Sparkles className="h-4 w-4 text-primary" />
              )}
            </div>
            <p className="rail-extraction-copy">{extractionCopy}</p>
            {railProcessing ? (
              <div className="rail-extraction-progress">
                <Progress value={progressValue} className="h-1.5" />
              </div>
            ) : null}
            <Button
              onClick={handleRunExtraction}
              disabled={railProcessing || isExtracting || !extractionReady}
              className="rail-extraction-button"
              variant={extractionDone ? 'outline' : 'default'}
            >
              {railProcessing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {extractionButtonLabel}
            </Button>
            {!extractionReady && !railProcessing ? (
              <p className="rail-extraction-hint">
                {projectName.trim() ? 'Offering Memorandum required.' : 'Deal name and Offering Memorandum required.'}
              </p>
            ) : null}
          </div>

          <div className="rail-docs-scroll">
            <div>
              <div className="rail-section-label">
                <span>Source documents</span>
                <span>{attachedCount}/3 attached</span>
              </div>
              <div className="space-y-2.5">
                {DOC_SLOTS.map((slot) => (
                  <DocCard
                    key={slot.key}
                    slot={slot}
                    selected={selectedDocs[slot.key]}
                    onOpen={() => setDocPickerOpen(slot.key)}
                    onRemove={() => setSelectedDocs((prev) => ({ ...prev, [slot.key]: null }))}
                    extracting={railProcessing}
                  />
                ))}
              </div>
            </div>

            {currentRun?.discrepancies?.length ? (
              <div className="mt-4 space-y-2.5">
                <div className="rail-section-label">
                  <span>Review flags</span>
                  <span>{currentRun.discrepancies.length}</span>
                </div>
                {currentRun.discrepancies.map((disc) => (
                  <DiscrepancyBanner key={disc.field} discrepancy={disc} />
                ))}
              </div>
            ) : null}
          </div>

          <div className="doc-rail-footer">
            <div>
              <div className="doc-rail-stat-val text-uw-citation">{attachedCount}/3</div>
              <div className="doc-rail-stat-label">Docs attached</div>
            </div>
            <div>
              <div className={`doc-rail-stat-val ${railProcessing ? 'text-primary' : extractionDone ? 'text-uw-success' : 'text-muted-foreground'}`}>
                {railProcessing ? 'Working' : extractionDone ? 'Ready' : 'Idle'}
              </div>
              <div className="doc-rail-stat-label">Extraction</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
