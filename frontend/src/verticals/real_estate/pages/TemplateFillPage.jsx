/**
 * Template Fill Page - Professional horizontal split layout
 *
 * Layout: [PDF Viewer 50%] | [Tabbed: Fields/Excel 50%]
 */

import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppAuth } from "@/hooks/useAppAuth";
import DocumentViewer from '../../../components/pdf/DocumentViewer';
import FieldsList from '../components/FieldsList';
import ExcelGridView from '../components/ExcelGridView';
import SourceMapView from '../components/SourceMapView';
import SourceMapWarningBanner from '../components/SourceMapWarningBanner';
import { STRUCTURE_LOW_CONFIDENCE, tierForConfidence } from '../utils/sourceMapConfidence';
import { useTemplateFill, useTemplateFillActions, useUser } from '../../../store';
import { TemplateFillRunPageSkeleton } from '../../../components/skeletons/PageSkeletons';
import { Loader2, AlertCircle, FileText, Table, List, Download, CheckCircle2, ExternalLink, X, Search, GitMerge, FileSpreadsheet, PartyPopper, Layers } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { Tabs, TabsContent } from '../../../components/ui/tabs';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '../../../components/ui/resizable';
import { Alert, AlertDescription, AlertTitle } from '../../../components/ui/alert';
import AppLayout from '../../../components/layout/AppLayout';
import { streamTemplateFillProgress, continueFillRun, downloadFilledExcel, startTemplateFill } from '../../../api/re-templates';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import FeedbackButton from '../../../components/feedback/FeedbackButton';
import CompletionFeedbackModal from '../../../components/feedback/CompletionFeedbackModal';
import { shouldPromptForFeedback } from '../../../utils/feedbackRules';
import { usePostHog } from '@posthog/react';

// Helper function to format status for display
function formatStatus(status) {
  const statusMap = {
    'queued': { label: 'Queued', variant: 'secondary' },
    'detecting_fields': { label: 'Detecting Fields', variant: 'default' },
    'fields_detected': { label: 'Fields Detected', variant: 'default' },
    'mapping': { label: 'Mapping Fields', variant: 'default' },
    'mapped': { label: 'Mapped', variant: 'default' },
    'awaiting_review': { label: 'Ready for Review', variant: 'default' },
    'filling': { label: 'Filling Template', variant: 'default' },
    'completed': { label: 'Completed', variant: 'success' },
    'failed': { label: 'Failed', variant: 'destructive' },
  };
  return statusMap[status] || { label: status, variant: 'secondary' };
}

// Pipeline stage definitions for AI processing visualization
const PIPELINE_STAGES = [
  { key: 'detect', icon: Search, label: 'Scanning PDF', progress: [0, 35] },
  { key: 'map', icon: GitMerge, label: 'Mapping Fields', progress: [35, 75] },
  { key: 'fill', icon: FileSpreadsheet, label: 'Filling Template', progress: [75, 100] },
];

function AIPipelineView({ progress, message }) {
  const activeIndex = PIPELINE_STAGES.findIndex((s, i) => {
    const next = PIPELINE_STAGES[i + 1];
    return progress >= s.progress[0] && progress < (next?.progress[0] ?? 101);
  });

  // Track when each stage becomes active so we can show elapsed time
  const stageStartTimes = useRef({});
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const key = PIPELINE_STAGES[activeIndex]?.key;
    if (key && stageStartTimes.current[key] === undefined) {
      stageStartTimes.current[key] = Date.now();
    }
  }, [activeIndex]);

  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  function getElapsed(stageKey, isDone, isActive) {
    const start = stageStartTimes.current[stageKey];
    if (!start) return null;
    if (isDone) {
      // Find when the next stage started (as a proxy for when this one ended)
      const stageIdx = PIPELINE_STAGES.findIndex(s => s.key === stageKey);
      const nextKey = PIPELINE_STAGES[stageIdx + 1]?.key;
      const end = nextKey ? stageStartTimes.current[nextKey] : Date.now();
      return end ? ((end - start) / 1000).toFixed(1) : null;
    }
    if (isActive) {
      // eslint-disable-next-line no-unused-expressions
      tick; // subscribe to tick
      return ((Date.now() - start) / 1000).toFixed(1);
    }
    return null;
  }

  return (
    <div className="h-full flex flex-col items-center justify-center p-6">
      <div className="glass-card rounded-2xl p-6 w-full max-w-sm space-y-5">
        {/* Header + progress */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-foreground tracking-[0.08px]">Processing</span>
            <span className="text-xs font-mono text-muted-foreground tabular-nums">{progress}%</span>
          </div>
          <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full bg-primary transition-all duration-700"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Stage rows */}
        <div className="space-y-1">
          {PIPELINE_STAGES.map((stage, i) => {
            const isDone = progress >= (PIPELINE_STAGES[i + 1]?.progress[0] ?? 101);
            const isActive = i === activeIndex;
            const isPending = !isDone && !isActive;
            const elapsed = getElapsed(stage.key, isDone, isActive);

            return (
              <div
                key={stage.key}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-xl transition-all duration-300',
                  isActive && 'bg-primary/5 border border-primary/15',
                  isDone && 'opacity-55',
                  isPending && 'opacity-25',
                )}
              >
                <div className="shrink-0 w-5 flex justify-center">
                  {isDone ? (
                    <CheckCircle2 className="h-4 w-4 text-primary" />
                  ) : isActive ? (
                    <Loader2 className="h-4 w-4 text-primary animate-spin" />
                  ) : (
                    <div className="h-4 w-4 rounded-full border-2 border-muted-foreground/30" />
                  )}
                </div>
                <span className={cn(
                  'flex-1 text-sm tracking-[0.07px]',
                  (isDone || isActive) ? 'text-foreground font-medium' : 'text-muted-foreground',
                )}>
                  {stage.label}
                </span>
                <span className="text-xs font-mono tabular-nums text-muted-foreground w-12 text-right">
                  {elapsed != null ? `${elapsed}s` : '—'}
                </span>
              </div>
            );
          })}
        </div>

        {/* Live message ticker */}
        {message && (
          <div className="border-t border-border/50 pt-3">
            <p
              key={message}
              className="text-xs text-muted-foreground tracking-[0.07px] animate-fade-in truncate"
              title={message}
            >
              <span className="text-muted-foreground/50 mr-1.5">›</span>
              {message}
            </p>
          </div>
        )}
      </div>

      <p className="text-xs text-muted-foreground/50 text-center mt-4 tracking-[0.07px]">
        You can review the PDF while this runs
      </p>
    </div>
  );
}

export default function TemplateFillPage() {
  const { fillRunId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAppAuth();
  const posthog = usePostHog();
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState('excel');
  const [highlightBbox, setHighlightBbox] = useState(null); // For PDF highlighting
  const [_showFeedbackModal, setShowFeedbackModal] = useState(false);

  // Progress tracking state
  const [jobProgress, setJobProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState('');
  const [jobStatus, setJobStatus] = useState('idle'); // idle, processing, completed, failed
  const [isRetrying, setIsRetrying] = useState(false);
  const [jobIdOverride, setJobIdOverride] = useState(null);
  const [showCompletionBanner, setShowCompletionBanner] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  // Zustand store
  const {
    fillRun,
    pdfUrl,
    pdfError,
    selectedText,
    isLoading,
    error,
  } = useTemplateFill();

  const {
    loadFillRun,
    setSelectedText,
    resetTemplateFill,
    registerPdfPopout,
    registerExcelPopout,
    navigatePdfToPage,
    cleanupPopouts: _cleanupPopouts,
  } = useTemplateFillActions();
  const userLimits = useUser()?.info?.limits;
  const progressStateToken = `${fillRun?.status || ''}|${fillRun?.artifact?.key || ''}|${fillRun?.artifact?.filename || ''}`;

  // Warn when approaching monthly template fill limit
  useEffect(() => {
    const fills = userLimits?.template_fill_runs;
    if (!fills?.limit || fills.used < 40) return;
    if (fills.used >= 45) {
      toast.error(`${fills.used}/${fills.limit} template fills used this month — you're almost at your limit.`, { duration: 6000 });
    } else {
      toast.warning(`Heads up: ${fills.used} of ${fills.limit} template fills used this month.`, { duration: 5000 });
    }
  }, [userLimits?.template_fill_runs?.used]);

  // Load fill run data on mount
  useEffect(() => {
    loadFillRun(fillRunId, getToken);
    const storedJobId = window.localStorage.getItem(`template_fill_job:${fillRunId}`);
    if (storedJobId) {
      setJobIdOverride(storedJobId);
    }

    // Cleanup on unmount
    return () => {
      resetTemplateFill();
    };
  }, [fillRunId]);

  // Listen for messages from pop-out windows
  useEffect(() => {
    function handleMessage(event) {
      // Security: In production, validate event.origin
      const { type, page } = event.data;

      switch (type) {
        case 'PDF_POPOUT_READY':
          registerPdfPopout(event.source);
          break;

        case 'EXCEL_POPOUT_READY':
          registerExcelPopout(event.source);
          break;

        case 'NAVIGATE_PDF_TO_PAGE':
          navigatePdfToPage(page);
          // Also update local state
          setCurrentPage(page);
          break;

        default:
          break;
      }
    }

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [registerPdfPopout, registerExcelPopout, navigatePdfToPage]);

  // Connect to SSE for progress updates when fill run is processing
  useEffect(() => {
    if (!fillRun) return;

    // Terminal states where no more background processing will occur
    const terminalStatuses = ['completed', 'failed', 'awaiting_review'];
    const isTerminal = terminalStatuses.includes(fillRun.status);

    if (isTerminal) {
      // Set final UI state for terminal statuses
      if (fillRun.status === 'completed' && fillRun.artifact) {
        // Only consider truly complete if artifact is available
        setJobStatus('completed');
        setJobProgress(100);
        setJobMessage('Template fill completed');
        posthog?.capture('template_fill_completed', {
          fill_run_id: fillRunId,
          fields_mapped: fillRun.total_fields_mapped ?? 0,
        });
        setShowCompletionBanner(true);
        setTimeout(() => setShowCompletionBanner(false), 8000);
      } else if (fillRun.status === 'failed') {
        setJobStatus('failed');
        setJobMessage(fillRun.error_message || 'Template fill failed');
        posthog?.capture('template_fill_failed', {
          fill_run_id: fillRunId,
          error_message: fillRun.error_message || 'unknown',
        });
      } else if (fillRun.status === 'awaiting_review') {
        // Auto-mapping complete, ready for user review
        setJobStatus('idle'); // Clear progress overlay
        setJobProgress(100);
        setJobMessage('Ready for review');
        setShowCompletionBanner(true);
        setTimeout(() => setShowCompletionBanner(false), 6000);
      }
      // If status is 'completed' but no artifact yet, keep processing overlay visible
      if (fillRun.status === 'completed' && !fillRun.artifact) {
        // Don't return - let SSE reconnect or continue polling
        setJobStatus('processing');
        setJobMessage('Finalizing download...');
        return;
      }
      if (fillRun.status === 'completed' || fillRun.status === 'failed') {
        window.localStorage.removeItem(`template_fill_job:${fillRunId}`);
        setJobIdOverride(null);
      }
      return;
    }

    // For all non-terminal statuses, connect to SSE
    // This includes: queued, detecting_fields, fields_detected, mapping, mapped, filling
    // SSE will fetch initial state and then stream updates

    // Connect to SSE stream
    setJobStatus('processing');

    let cleanup;
    const sseJobId = jobIdOverride || fillRunId;
    streamTemplateFillProgress(sseJobId, getToken, {
      onProgress: (data) => {
        setJobProgress(data.progress_percent || 0);
        setJobMessage(data.message || 'Processing...');
        if (data.status) {
          posthog?.capture('template_fill_step_changed', {
            fill_run_id: fillRunId,
            status: data.status,
          });
        }

        // Check if progress event contains a terminal status
        // This handles the case where backend sends progress events with terminal status
        // instead of a separate "complete" event
        if (data.status === 'awaiting_review' || data.status === 'completed') {
          // Don't clear progress overlay yet - wait for store to update with artifact
          // Reload to get final state (including artifact if completed)
          setTimeout(async () => {
            await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });
            // Only clear progress after loadFillRun completes
            setJobStatus('idle');
          }, 100);
        } else if (data.status === 'failed') {
          setJobStatus('failed');
        }
      },
      onComplete: async (_data) => {
        setJobProgress(100);
        setJobMessage('Complete');
        // Wait for backend to finish updating database, then reload
        // This ensures we get the final status and artifact data
        // Don't clear progress overlay until artifact is loaded
        setTimeout(async () => {
          await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });
          // Only clear progress after loadFillRun completes
          setJobStatus('idle');
        }, 100);
      },
      onError: (error) => {
        console.error('❌ Fill run error:', error);
        posthog?.capture('template_fill_failed', {
          fill_run_id: fillRunId,
          error_message: error?.message || 'sse_error',
        });
        setJobStatus('failed');
        setJobMessage(error?.message || 'An error occurred');
        // Reload fill run silently to get error details
        loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });
      },
      onEnd: (_data) => {
      },
    }).then((cleanupFn) => {
      cleanup = cleanupFn;
    });

    // Cleanup SSE connection on unmount
    return () => {
      if (cleanup) cleanup();
    };
  }, [progressStateToken, fillRunId, jobIdOverride]);

  // Auto-show feedback modal on completion (with frequency rules)
  useEffect(() => {
    if (fillRun?.status === 'completed' && fillRunId) {
      const shouldPrompt = shouldPromptForFeedback('template_fill', fillRunId);
      setShowFeedbackModal(shouldPrompt);
    }
  }, [fillRun?.status, fillRunId]);

  function handleTextSelect(selection) {
    setSelectedText(selection);
  }

  // Citation click handler - navigate to PDF page with optional bbox highlighting
  function handleCitationClick(pageNumberOrBbox) {
    // Support both old (page number only) and new (bbox object) formats
    if (typeof pageNumberOrBbox === 'number') {
      const targetPage = Number(pageNumberOrBbox);
      if (!Number.isFinite(targetPage) || targetPage < 1) return;

      // Page-only citation: trigger deterministic scroll without rendering a highlight.
      setCurrentPage(targetPage);
      setHighlightBbox({ page: targetPage, __scrollOnly: true, __ts: Date.now() });
      navigatePdfToPage(targetPage);
    } else if (pageNumberOrBbox?.page) {
      // New: bbox object with { page, x0, y0, x1, y1 }
      const targetPage = Number(pageNumberOrBbox.page);
      if (!Number.isFinite(targetPage) || targetPage < 1) return;

      setCurrentPage(targetPage);
      setHighlightBbox({
        ...pageNumberOrBbox,
        page: targetPage,
        __ts: Date.now(),
      });
      navigatePdfToPage(targetPage);
    }
  }

  // Clear highlight when user clicks on it
  function handleHighlightClick() {
    setHighlightBbox(null);
  }

  async function handleContinue() {
    if (fillRun.status === 'completed') {
      // Download the filled Excel file
      try {
        setIsDownloading(true);
        const blob = await downloadFilledExcel(getToken, fillRunId);
        posthog?.capture('template_fill_downloaded', { fill_run_id: fillRunId });

        // Verify blob is valid
        if (blob.size === 0) {
          throw new Error('Downloaded file is empty');
        }

        // Create blob with correct MIME type if not set
        const excelBlob = blob.type.includes('spreadsheet') || blob.type.includes('excel')
          ? blob
          : new Blob([blob], {
              type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            });

        const url = window.URL.createObjectURL(excelBlob);
        const a = document.createElement('a');
        a.href = url;
        // Use the filename from artifact (which has correct extension) or fallback
        a.download = fillRun.artifact?.filename || `${fillRun.template_snapshot?.name || 'template'}_filled.xlsx`;
        document.body.appendChild(a);
        a.click();

        // Cleanup
        setTimeout(() => {
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
        }, 100);
      } catch (err) {
        console.error('❌ Failed to download Excel file:', err);
        setJobStatus('failed');
        setJobMessage(`Failed to download Excel file: ${err.message}`);
      } finally {
        setIsDownloading(false);
      }
    } else if (fillRun.status === 'awaiting_review') {
      // Continue with filling the template
      try {
        setJobStatus('processing');
        setJobProgress(70);
        setJobMessage('Filling Excel template...');

        const result = await continueFillRun(getToken, fillRunId);
        if (result?.job_id) {
          window.localStorage.setItem(`template_fill_job:${fillRunId}`, result.job_id);
          setJobIdOverride(result.job_id);
        }

        // Wait a moment for backend to start processing, then reload
        // This allows the fill_run status to update from 'awaiting_review' to 'processing'
        // which will trigger the SSE effect to connect and stream progress updates
        setTimeout(async () => {
          await loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });
        }, 200);

        // Don't reset jobStatus here - let SSE manage it via the progress effect
        // The progress overlay will stay visible until a terminal status is reached
      } catch (err) {
        console.error('Failed to continue fill run:', err);
        setJobStatus('failed');
        if (err?.response?.status === 403 || err?.status === 403) {
          setJobMessage('Monthly template fill limit reached. Contact support to increase your limit.');
        } else {
          setJobMessage('Failed to continue fill run');
        }
      }
    } else {
      // For other statuses, navigate back to templates
      navigate('/re/templates?tab=fills');
    }
  }

  async function handleRetry() {
    if (!fillRun?.template_id || !fillRun?.document_id) {
      navigate('/app/re/templates');
      return;
    }
    try {
      setIsRetrying(true);
      posthog?.capture('template_fill_retried', { fill_run_id: fillRunId });
      const newFillRun = await startTemplateFill(getToken, fillRun.template_id, fillRun.document_id);
      posthog?.capture('template_fill_started', {
        fill_run_id: newFillRun.fill_run_id,
        template_id: fillRun.template_id,
        document_id: fillRun.document_id,
      });
      navigate(`/app/re/fills/${newFillRun.fill_run_id}`);
    } catch (err) {
      console.error('Failed to retry fill run:', err);
      setJobMessage('Failed to start new fill: ' + (err.message || 'Unknown error'));
      setIsRetrying(false);
    }
  }

  // Must be before early returns to satisfy Rules of Hooks.
  const omStructure = fillRun?.extracted_data?.om_structure ?? null;
  const structureChipCounts = useMemo(() => {
    if (!omStructure?.effective) return null;
    const { column_map = {}, section_presence = {} } = omStructure.effective;
    const counts = { high: 0, mid: 0, low: 0, total: 0 };
    for (const e of [...Object.values(column_map), ...Object.values(section_presence)]) {
      if (!e || e.present !== true || e.confidence == null) continue;
      counts[tierForConfidence(e.confidence)]++;
      counts.total++;
    }
    return counts;
  }, [omStructure]);

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center flex-1">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="animate-spin h-8 w-8 text-primary" />
            <span className="text-sm text-muted-foreground">Loading template fill...</span>
          </div>
        </div>
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center flex-1 p-6">
          <Alert variant="destructive" className="max-w-md">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Failed to load fill run</AlertTitle>
            <AlertDescription className="mt-2 space-y-3">
              <p>{error}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => window.location.reload()}
              >
                Reload Page
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      </AppLayout>
    );
  }

  if (!fillRun) {
    return (
      <AppLayout>
        <div className="h-full">
          <TemplateFillRunPageSkeleton />
        </div>
      </AppLayout>
    );
  }

  const statusInfo = formatStatus(fillRun.status);

  const fillHeaderMeta = (
    <>
      <Badge
        variant={statusInfo.variant}
        className={statusInfo.variant === 'success'
          ? 'h-5 px-2 text-[10px] bg-green-500 hover:bg-green-600 text-white shrink-0 tracking-[0.28px]'
          : 'h-5 px-2 text-[10px] shrink-0 tracking-[0.28px]'}
      >
        {statusInfo.label}
      </Badge>
      {!fillRun.template_id && <Badge variant="destructive" className="h-5 px-2 text-[10px] shrink-0 tracking-[0.28px]">Template Deleted</Badge>}
      {!fillRun.document_id && <Badge variant="destructive" className="h-5 px-2 text-[10px] shrink-0 tracking-[0.28px]">Doc Deleted</Badge>}
    </>
  );

  const fillHeaderRight = (
    <div className="flex items-center gap-2 shrink-0">
      {fillRun.status === 'completed' && fillRun.artifact ? (
        <>
          <Button
            size="sm"
            variant="default"
            onClick={handleContinue}
            disabled={isDownloading}
            className="h-7 rounded-lg px-2.5 text-[11px] font-medium shadow-sm tracking-[0.04px]"
          >
            <span className="mr-1 flex h-4.5 w-4.5 items-center justify-center rounded-full bg-primary-foreground/15 text-primary-foreground">
              {isDownloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            </span>
            {isDownloading ? 'Downloading...' : 'Download'}
          </Button>
          <FeedbackButton
            operationType="template_fill"
            entityId={fillRunId}
            entitySummary={fillRun.template_snapshot?.name || 'Template Fill'}
            variant="ghost"
            size="sm"
            label="Give Feedback"
            submittedLabel="Update Feedback"
            iconOnly
            className="h-7 w-7 rounded-full border border-border/60 bg-background/75 p-0 text-muted-foreground shadow-sm backdrop-blur-sm hover:bg-accent hover:text-foreground"
          />
        </>
      ) : fillRun.status === 'awaiting_review' ? (
        <Button size="sm" onClick={handleContinue} className="bg-blue-600 hover:bg-blue-700 text-white h-7 rounded-lg px-2.5 text-[11px] tracking-[0.04px]">
          <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
          Approve &amp; Fill
        </Button>
      ) : fillRun.status === 'filling' ? (
        <Button size="sm" disabled className="bg-muted h-7 rounded-lg px-2.5 text-[11px] tracking-[0.04px]">
          <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          Filling...
        </Button>
      ) : null}
    </div>
  );

  const pageHeader = {
    eyebrow: 'Real Estate',
    title: fillRun.name || 'Template Fill',
    backTo: '/app/re/templates?tab=fills',
    backLabel: 'Fill runs',
    meta: fillHeaderMeta,
    actions: fillHeaderRight,
    compact: true,
  };
  const contextBudgetWarning = fillRun.field_mapping?.context_budget?.user_warning;
  const omStructureSummary = fillRun.field_mapping?.om_structure_summary ?? null;

  return (
    <AppLayout lockViewport pageHeader={pageHeader}>
      <div className="flex-1 flex flex-col bg-background relative overflow-hidden min-h-0">
        {/* Completion Banner */}
        {showCompletionBanner && (
          <div className="absolute top-2 left-1/2 -translate-x-1/2 z-50 animate-fade-in">
            <div className="glass-card rounded-full px-5 py-2.5 flex items-center gap-3 shadow-lg border border-primary/20">
              <div className="w-6 h-6 rounded-full bg-primary/10 flex items-center justify-center">
                {fillRun?.status === 'completed' ? (
                  <PartyPopper className="h-3.5 w-3.5 text-primary" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
                )}
              </div>
              <span className="text-sm font-semibold text-foreground">
                {fillRun?.status === 'completed'
                  ? `${fillRun.total_fields_mapped || 0} cells filled · Ready to download`
                  : `AI mapping complete · ${fillRun?.total_fields_mapped || 0} fields mapped`}
              </span>
              <button onClick={() => setShowCompletionBanner(false)} className="text-muted-foreground hover:text-foreground transition-colors">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        )}

        {/* Error Alert — always-present container prevents layout shift when alert appears */}
        <div className={`px-6 overflow-hidden transition-all duration-200 ${jobStatus === 'failed' ? 'pt-4' : 'h-0'}`}>
        {jobStatus === 'failed' && (
          <div>
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Template Fill Failed</AlertTitle>
              <AlertDescription className="mt-2">
                <div className="space-y-2">
                  <p>{jobMessage}</p>
                  {fillRun?.template_id && fillRun?.document_id ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRetry}
                      disabled={isRetrying}
                    >
                      {isRetrying ? (
                        <>
                          <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                          Starting...
                        </>
                      ) : (
                        'Retry'
                      )}
                    </Button>
                  ) : (
                  <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate('/app/re/templates?tab=fills')}
                    >
                      Back to Fill Runs
                    </Button>
                  )}
                </div>
              </AlertDescription>
            </Alert>
          </div>
        )}
        </div>

        {contextBudgetWarning && (
          <div className="px-6 pt-4">
            <Alert className="border-amber-200 bg-amber-50 text-amber-950">
              <AlertCircle className="h-4 w-4 text-amber-600" />
              <AlertTitle>Large document reviewed selectively</AlertTitle>
              <AlertDescription className="mt-1 text-amber-900">
                {contextBudgetWarning}
              </AlertDescription>
            </Alert>
          </div>
        )}
        {omStructureSummary && (
          omStructureSummary.low_confidence_keys?.length > 0 ||
          (omStructureSummary.min_confidence != null && omStructureSummary.min_confidence < STRUCTURE_LOW_CONFIDENCE)
        ) && (
          <div className="px-6 pt-3">
            <SourceMapWarningBanner
              summary={omStructureSummary}
              onReview={() => setActiveTab('structure')}
            />
          </div>
        )}

        {/* Horizontal Split Layout */}
        <ResizablePanelGroup direction="horizontal" className="flex-1 min-h-0 overflow-hidden">
          {/* Left Panel: PDF Viewer */}
          <ResizablePanel defaultSize={50} minSize={30} className="min-h-0 overflow-hidden">
            <div className="h-full min-h-0 flex flex-col bg-background overflow-hidden">
              <div className="bg-card px-4 py-2 border-b flex-shrink-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                    <h2 className="font-medium text-xs text-foreground tracking-[0.12px]">PDF Document</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    {fillRun.document_metadata && (
                      <Badge variant="secondary" className="text-[10px] px-2 py-0 tracking-[0.28px]">
                        {fillRun.document_metadata.page_count} pages
                      </Badge>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const popout = window.open(
                          `/app/re/fills/${fillRunId}/pdf-popout?page=${currentPage}`,
                          '_blank',
                          'width=800,height=900'
                        );
                        if (popout) {
                          // Register after a short delay to allow the window to load
                          setTimeout(() => registerPdfPopout(popout), 500);
                        }
                      }}
                      className="h-7 w-7 p-0"
                      title="Open PDF in new window"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
              <div className="flex-1 min-h-0 overflow-auto">
                {pdfUrl ? (
                  <DocumentViewer
                    fileUrl={pdfUrl}
                    filename={fillRun?.document_metadata?.filename || ''}
                    onTextSelect={handleTextSelect}
                    defaultPage={currentPage}
                    highlightBbox={highlightBbox}
                    onHighlightClick={handleHighlightClick}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center space-y-2 p-6 max-w-sm">
                      <div className="flex justify-center">
                        <div className="p-3 bg-muted rounded-full">
                          <FileText className="h-6 w-6 text-muted-foreground" />
                        </div>
                      </div>
                      <p className="text-sm font-medium text-foreground">
                        {!fillRun.document_id || pdfError?.toLowerCase().includes('deleted')
                          ? 'Source Document Deleted'
                          : 'PDF Not Available'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {pdfError || (!fillRun.document_id
                          ? 'The source PDF document for this fill run has been deleted.'
                          : 'The PDF is loading or temporarily unavailable.')}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right Panel: Tabbed Fields/Excel */}
          <ResizablePanel defaultSize={50} minSize={30} className="min-h-0 overflow-hidden">
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full min-h-0 flex flex-col overflow-hidden">
              <div className="sticky top-0 z-10 bg-card border-b flex-shrink-0">
                {/* Processing progress stripe */}
                {jobStatus === 'processing' && (
                  <div className="h-0.5 bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-700"
                      style={{ width: `${jobProgress}%` }}
                    />
                  </div>
                )}

                {/* Pill tab switcher + inline stats + popout button */}
                <div className="flex items-center justify-between px-3 py-2">
                  <div className="flex items-center bg-muted/50 rounded-xl p-1 gap-0.5">
                    <button
                      onClick={() => setActiveTab('excel')}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium tracking-[0.08px] transition-all duration-150',
                        activeTab === 'excel'
                          ? 'bg-background shadow-sm text-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <Table className="h-3.5 w-3.5" />
                      Excel
                      <span className={cn(
                        'ml-0.5 tabular-nums text-[10px] tracking-[0.07px]',
                        activeTab === 'excel' ? 'text-muted-foreground' : 'text-muted-foreground/60',
                      )}>
                        {fillRun.total_fields_mapped || 0}/{fillRun.total_template_fields || 0}
                      </span>
                    </button>
                    {omStructure && (
                      <button
                        onClick={() => setActiveTab('structure')}
                        className={cn(
                          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium tracking-[0.08px] transition-all duration-150',
                          activeTab === 'structure'
                            ? 'bg-background shadow-sm text-foreground'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        <Layers className="h-3.5 w-3.5" />
                        Structure
                        {structureChipCounts && (
                          <span className="ml-0.5 flex items-center gap-0.5 text-[10px] tabular-nums">
                            {structureChipCounts.high > 0 && (
                              <span className={activeTab === 'structure' ? 'text-success' : 'text-success/60'}>
                                {structureChipCounts.high} ok
                              </span>
                            )}
                            {structureChipCounts.mid > 0 && (
                              <>
                                {structureChipCounts.high > 0 && <span className="text-muted-foreground/40">·</span>}
                                <span className={activeTab === 'structure' ? 'text-warning' : 'text-warning/60'}>
                                  {structureChipCounts.mid} review
                                </span>
                              </>
                            )}
                            {structureChipCounts.low > 0 && (
                              <>
                                {(structureChipCounts.high > 0 || structureChipCounts.mid > 0) && <span className="text-muted-foreground/40">·</span>}
                                <span className={activeTab === 'structure' ? 'text-destructive' : 'text-destructive/60'}>
                                  {structureChipCounts.low} low
                                </span>
                              </>
                            )}
                          </span>
                        )}
                      </button>
                    )}
                    <button
                      onClick={() => setActiveTab('fields')}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium tracking-[0.08px] transition-all duration-150',
                        activeTab === 'fields'
                          ? 'bg-background shadow-sm text-foreground'
                          : 'text-muted-foreground hover:text-foreground',
                      )}
                    >
                      <List className="h-3.5 w-3.5" />
                      Fields
                      <span className={cn(
                        'ml-0.5 tabular-nums text-[10px] tracking-[0.07px]',
                        activeTab === 'fields' ? 'text-muted-foreground' : 'text-muted-foreground/60',
                      )}>
                        {fillRun.field_mapping?.pdf_fields?.length || 0}
                      </span>
                    </button>
                  </div>
{activeTab === 'excel' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const popout = window.open(
                          `/app/re/fills/${fillRunId}/excel-popout`,
                          '_blank',
                          'width=1200,height=900'
                        );
                        if (popout) {
                          setTimeout(() => registerExcelPopout(popout), 500);
                        }
                      }}
                      className="h-7 w-7 p-0"
                      title="Open Excel in new window"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>


              <TabsContent value="structure" className="flex-1 min-h-0 overflow-auto m-0">
                <SourceMapView
                  omStructure={omStructure}
                  cellStatus={fillRun.field_mapping?.yaml_cell_status}
                  citationContext={fillRun.citation_context}
                  onCitationClick={handleCitationClick}
                />
              </TabsContent>

              <TabsContent value="fields" className="flex-1 min-h-0 overflow-auto m-0">
                <FieldsList
                  fillRunId={fillRunId}
                  extractedData={fillRun.extracted_data}
                  fieldMapping={fillRun.field_mapping}
                  citationContext={fillRun.citation_context}
                  selectedText={selectedText}
                  onCitationClick={handleCitationClick}
                />
              </TabsContent>

              <TabsContent value="excel" className="flex-1 min-h-0 overflow-auto m-0">
                {jobStatus === 'processing' ? (
                  <AIPipelineView progress={jobProgress} message={jobMessage} fillRun={fillRun} />
                ) : !fillRun.template_id ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="text-center space-y-3 p-8 max-w-md">
                      <div className="flex justify-center">
                        <div className="p-4 bg-destructive/10 rounded-full">
                          <AlertCircle className="h-8 w-8 text-destructive" />
                        </div>
                      </div>
                      <h3 className="text-lg font-semibold text-foreground">
                        Template No Longer Available
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        The Excel template for this fill run has been deleted. The filled Excel file is still available for download if this fill run was completed.
                      </p>
                      {fillRun.status === 'completed' && fillRun.artifact && (
                        <Button
                          onClick={handleContinue}
                          className="mt-4"
                        >
                          <Download className="h-4 w-4 mr-2" />
                          Download Filled Excel
                        </Button>
                      )}
                    </div>
                  </div>
                ) : (
                  <ExcelGridView
                    fillRunId={fillRunId}
                    extractedData={fillRun.extracted_data}
                    fieldMapping={fillRun.field_mapping}
                    templateId={fillRun.template_id}
                    citationContext={fillRun.citation_context}
                    onCitationClick={handleCitationClick}
                  />
                )}
              </TabsContent>
            </Tabs>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </AppLayout>
  );
}



