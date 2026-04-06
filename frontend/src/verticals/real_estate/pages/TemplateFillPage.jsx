/**
 * Template Fill Page - Professional horizontal split layout
 *
 * Layout: [PDF Viewer 50%] | [Tabbed: Fields/Excel 50%]
 */

import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAppAuth } from "@/hooks/useAppAuth";
import DocumentViewer from '../../../components/pdf/DocumentViewer';
import FieldsList from '../components/FieldsList';
import ExcelGridView from '../components/ExcelGridView';
import { useTemplateFill, useTemplateFillActions, useUser } from '../../../store';
import { Loader2, AlertCircle, FileText, Table, List, Download, ArrowLeft, CheckCircle2, ExternalLink, X, Sparkles, Search, GitMerge, FileSpreadsheet, PartyPopper } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '../../../components/ui/resizable';
import { Progress } from '../../../components/ui/progress';
import { Card } from '../../../components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '../../../components/ui/alert';
import AppLayout from '../../../components/layout/AppLayout';
import { streamTemplateFillProgress, continueFillRun, downloadFilledExcel, startTemplateFill } from '../../../api/re-templates';
import { toast } from 'sonner';
import FeedbackButton from '../../../components/feedback/FeedbackButton';
import CompletionFeedbackModal from '../../../components/feedback/CompletionFeedbackModal';
import { shouldPromptForFeedback } from '../../../utils/feedbackRules';

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

// Helper function to format stage for display
function formatStage(stage) {
  const stageMap = {
    'auto_mapping': 'AI Mapping',
    'manual_review': 'Manual Review',
    'filling': 'Filling',
    'completed': 'Completed',
  };
  return stageMap[stage] || stage;
}

// Pipeline stage definitions for AI processing visualization
const PIPELINE_STAGES = [
  { key: 'detect', icon: Search, label: 'Scanning PDF', sub: 'Reading document structure and extracting fields', progress: [0, 35] },
  { key: 'map', icon: GitMerge, label: 'AI Field Mapping', sub: 'Matching extracted fields to Excel template cells', progress: [35, 75] },
  { key: 'fill', icon: FileSpreadsheet, label: 'Filling Template', sub: 'Writing values into Excel cells', progress: [75, 100] },
];

function AIPipelineView({ progress, message, fillRun }) {
  const currentStageIndex = PIPELINE_STAGES.findIndex(
    (s, i) => progress < PIPELINE_STAGES[i + 1]?.progress[0] ?? 100
  );
  const activeIndex = PIPELINE_STAGES.findIndex((s, i) => {
    const next = PIPELINE_STAGES[i + 1];
    return progress >= s.progress[0] && progress < (next?.progress[0] ?? 101);
  });

  return (
    <div className="h-full flex flex-col items-center justify-center p-8 gap-8">
      {/* Central AI animation */}
      <div className="relative">
        <div className="w-20 h-20 rounded-2xl glass-card flex items-center justify-center">
          <Sparkles className="h-9 w-9 text-primary" />
        </div>
        <div className="absolute inset-0 rounded-2xl bg-primary/10 animate-ping opacity-30" />
      </div>

      <div className="text-center space-y-1 max-w-xs">
        <h3 className="font-display text-lg font-semibold text-foreground">Processing</h3>
        <p className="text-sm text-muted-foreground">{message || 'Analyzing document...'}</p>
      </div>

      {/* Overall progress bar */}
      <div className="w-full max-w-xs space-y-2">
        <Progress value={progress} className="h-1.5" />
        <p className="text-xs text-muted-foreground text-center">{progress}% complete</p>
      </div>

      {/* Pipeline stages */}
      <div className="w-full max-w-sm space-y-3">
        {PIPELINE_STAGES.map((stage, i) => {
          const isDone = progress >= (PIPELINE_STAGES[i + 1]?.progress[0] ?? 101);
          const isActive = i === activeIndex;
          const Icon = stage.icon;
          return (
            <div
              key={stage.key}
              className={`flex items-start gap-3 p-3 rounded-xl transition-all duration-300 ${
                isActive ? 'glass-card border border-primary/20' : isDone ? 'opacity-60' : 'opacity-30'
              }`}
            >
              <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                isDone ? 'bg-primary/15' : isActive ? 'bg-primary/10' : 'bg-muted'
              }`}>
                {isDone ? (
                  <CheckCircle2 className="h-4 w-4 text-primary" />
                ) : isActive ? (
                  <Loader2 className="h-4 w-4 text-primary animate-spin" />
                ) : (
                  <Icon className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <div className="min-w-0">
                <p className={`text-sm font-medium ${isDone || isActive ? 'text-foreground' : 'text-muted-foreground'}`}>
                  {stage.label}
                  {isDone && <span className="ml-2 text-xs text-primary font-normal">Done</span>}
                </p>
                {isActive && (
                  <p className="text-xs text-muted-foreground mt-0.5">{stage.sub}</p>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground/60 text-center max-w-xs">
        Processing in the background · You can review the PDF while this runs
      </p>
    </div>
  );
}

export default function TemplateFillPage() {
  const { fillRunId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAppAuth();
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState('excel');
  const [highlightBbox, setHighlightBbox] = useState(null); // For PDF highlighting
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

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
    cleanupPopouts,
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
        setShowCompletionBanner(true);
        setTimeout(() => setShowCompletionBanner(false), 8000);
      } else if (fillRun.status === 'failed') {
        setJobStatus('failed');
        setJobMessage(fillRun.error_message || 'Template fill failed');
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
      onComplete: async (data) => {
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
        setJobStatus('failed');
        setJobMessage(error?.message || 'An error occurred');
        // Reload fill run silently to get error details
        loadFillRun(fillRunId, getToken, { silent: true, skipPdf: true });
      },
      onEnd: (data) => {
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
      const newFillRun = await startTemplateFill(getToken, fillRun.template_id, fillRun.document_id);
      navigate(`/app/re/fills/${newFillRun.fill_run_id}`);
    } catch (err) {
      console.error('Failed to retry fill run:', err);
      setJobMessage('Failed to start new fill: ' + (err.message || 'Unknown error'));
      setIsRetrying(false);
    }
  }

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
        <div className="flex items-center justify-center flex-1">
          <p className="text-muted-foreground text-sm">Fill run not found</p>
        </div>
      </AppLayout>
    );
  }

  const statusInfo = formatStatus(fillRun.status);

  const fillHeaderLeft = (
    <div className="flex items-center gap-2.5 min-w-0">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/app/re/templates?tab=fills')}
        className="h-8 w-8 rounded-full border border-border/70 bg-background/80 p-0 shrink-0 text-muted-foreground shadow-sm hover:bg-accent hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
      </Button>
      <div className="min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-foreground leading-tight truncate max-w-[220px]">
            {fillRun.name || 'Template Fill'}
          </span>
          <Badge
            variant={statusInfo.variant}
            className={statusInfo.variant === 'success'
              ? 'h-5 px-2 text-[10px] bg-green-500 hover:bg-green-600 text-white shrink-0'
              : 'h-5 px-2 text-[10px] shrink-0'}
          >
            {statusInfo.label}
          </Badge>
          {!fillRun.template_id && <Badge variant="destructive" className="h-5 px-2 text-[10px] shrink-0">Template Deleted</Badge>}
          {!fillRun.document_id && <Badge variant="destructive" className="h-5 px-2 text-[10px] shrink-0">Doc Deleted</Badge>}
        </div>
      </div>
    </div>
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
            className="h-8 rounded-full px-3 text-xs font-medium shadow-sm"
          >
            <span className="mr-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary-foreground/15 text-primary-foreground">
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
            className="h-8 w-8 rounded-full border border-border/60 bg-background/75 p-0 text-muted-foreground shadow-sm backdrop-blur-sm hover:bg-accent hover:text-foreground"
          />
        </>
      ) : fillRun.status === 'awaiting_review' ? (
        <Button size="sm" onClick={handleContinue} className="bg-blue-600 hover:bg-blue-700 text-white h-8 rounded-full px-3 text-xs">
          <CheckCircle2 className="h-3.5 w-3.5 mr-1.5" />
          Approve &amp; Fill
        </Button>
      ) : fillRun.status === 'filling' ? (
        <Button size="sm" disabled className="bg-muted h-8 rounded-full px-3 text-xs">
          <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
          Filling...
        </Button>
      ) : null}
    </div>
  );

  return (
    <AppLayout lockViewport headerLeft={fillHeaderLeft} headerRight={fillHeaderRight}>
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

        {/* Error Alert */}
        {jobStatus === 'failed' && (
          <div className="px-6 pt-4">
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

        {/* Mobile toolbar */}
        <div className="md:hidden flex items-center justify-between px-3 py-1.5 border-b bg-card flex-shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Button variant="ghost" size="sm" onClick={() => navigate('/app/re/templates?tab=fills')} className="h-7 w-7 p-0 shrink-0">
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-semibold truncate">{fillRun.name || 'Template Fill'}</span>
          </div>
          {fillRun.status === 'completed' && fillRun.artifact && (
            <Button size="sm" onClick={handleContinue} disabled={isDownloading} className="bg-green-600 text-white h-7 text-xs shrink-0">
              {isDownloading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
            </Button>
          )}
        </div>

        {/* Horizontal Split Layout */}
        <ResizablePanelGroup direction="horizontal" className="flex-1 min-h-0 overflow-hidden">
          {/* Left Panel: PDF Viewer */}
          <ResizablePanel defaultSize={50} minSize={30} className="min-h-0 overflow-hidden">
            <div className="h-full min-h-0 flex flex-col bg-background overflow-hidden">
              <div className="bg-card px-4 py-1 border-b flex-shrink-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                    <h2 className="font-medium text-xs text-foreground">PDF Document</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    {fillRun.document_metadata && (
                      <Badge variant="secondary" className="text-[11px] px-2 py-0">
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
                {jobStatus === 'processing' && (
                  <div className="h-0.5 bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all duration-700"
                      style={{ width: `${jobProgress}%` }}
                    />
                  </div>
                )}
                <div className="flex items-center justify-between px-4">
                  <TabsList className="bg-transparent rounded-none p-0 h-auto border-b-0">
                    <TabsTrigger
                      value="excel"
                      className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 gap-2"
                    >
                      <Table className="h-4 w-4" />
                      <span className="text-sm font-medium">Excel Preview</span>
                      <Badge variant="secondary">
                        {fillRun.total_fields_mapped || 0} / {fillRun.total_template_fields || 0}
                      </Badge>
                    </TabsTrigger>
                    <TabsTrigger
                      value="fields"
                      className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 gap-2"
                    >
                      <List className="h-4 w-4" />
                      <span className="text-sm font-medium">Extracted Fields</span>
                      <Badge variant="secondary">
                        {fillRun.field_mapping?.pdf_fields?.length || 0}
                      </Badge>
                    </TabsTrigger>
                  </TabsList>
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
                          // Register after a short delay to allow the window to load
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



