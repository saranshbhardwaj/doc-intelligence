/**
 * Template Fill Page - Professional horizontal split layout
 *
 * Layout: [PDF Viewer 50%] | [Tabbed: Fields/Excel 50%]
 */

import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '@clerk/clerk-react';
import PDFViewer from '../../../components/pdf/PDFViewer';
import FieldsList from '../components/FieldsList';
import ExcelGridView from '../components/ExcelGridView';
import { useTemplateFill, useTemplateFillActions } from '../../../store';
import { Loader2, AlertCircle, FileText, Table, List, Download, ArrowLeft, CheckCircle2, ExternalLink } from 'lucide-react';
import { Badge } from '../../../components/ui/badge';
import { Button } from '../../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from '../../../components/ui/resizable';
import { Progress } from '../../../components/ui/progress';
import { Card } from '../../../components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '../../../components/ui/alert';
import AppLayout from '../../../components/layout/AppLayout';
import { streamTemplateFillProgress, continueFillRun, downloadFilledExcel } from '../../../api/re-templates';
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

export default function TemplateFillPage() {
  const { fillRunId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const [currentPage, setCurrentPage] = useState(1);
  const [activeTab, setActiveTab] = useState('excel');
  const [highlightBbox, setHighlightBbox] = useState(null); // For PDF highlighting
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);

  // Progress tracking state
  const [jobProgress, setJobProgress] = useState(0);
  const [jobMessage, setJobMessage] = useState('');
  const [jobStatus, setJobStatus] = useState('idle'); // idle, processing, completed, failed

  // Zustand store
  const {
    fillRun,
    pdfUrl,
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

  // Load fill run data on mount
  useEffect(() => {
    loadFillRun(fillRunId, getToken);

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
      } else if (fillRun.status === 'failed') {
        setJobStatus('failed');
        setJobMessage(fillRun.error_message || 'Template fill failed');
      } else if (fillRun.status === 'awaiting_review') {
        // Auto-mapping complete, ready for user review
        setJobStatus('idle'); // Clear progress overlay
        setJobProgress(100);
        setJobMessage('Ready for review');
      }
      // If status is 'completed' but no artifact yet, keep processing overlay visible
      if (fillRun.status === 'completed' && !fillRun.artifact) {
        // Don't return - let SSE reconnect or continue polling
        setJobStatus('processing');
        setJobMessage('Finalizing download...');
        return;
      }
      return;
    }

    // For all non-terminal statuses, connect to SSE
    // This includes: queued, detecting_fields, fields_detected, mapping, mapped, filling
    // SSE will fetch initial state and then stream updates

    // Connect to SSE stream
    setJobStatus('processing');

    let cleanup;
    streamTemplateFillProgress(fillRunId, getToken, {
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
          console.log('❌ Failed status detected in progress event');
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
  }, [fillRun?.status, fillRunId]);

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
      // Legacy: just a page number
      setCurrentPage(pageNumberOrBbox);
      setHighlightBbox(null);
      navigatePdfToPage(pageNumberOrBbox);
    } else if (pageNumberOrBbox?.page) {
      // New: bbox object with { page, x0, y0, x1, y1 }
      setCurrentPage(pageNumberOrBbox.page);
      setHighlightBbox(pageNumberOrBbox);
      navigatePdfToPage(pageNumberOrBbox.page);
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
        alert(`Failed to download Excel file: ${err.message}`);
      }
    } else if (fillRun.status === 'awaiting_review') {
      // Continue with filling the template
      try {
        setJobStatus('processing');
        setJobProgress(70);
        setJobMessage('Filling Excel template...');

        const result = await continueFillRun(getToken, fillRunId);

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
        setJobMessage('Failed to continue fill run');
      }
    } else {
      // For other statuses, navigate back to templates
      navigate('/re/templates?tab=fills');
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
        <div className="flex items-center justify-center flex-1">
          <div className="bg-destructive/10 p-6 rounded-lg max-w-md border border-destructive/20">
            <div className="flex items-center mb-4">
              <AlertCircle className="h-6 w-6 text-destructive mr-2" />
              <h2 className="text-lg font-semibold text-foreground">Error</h2>
            </div>
            <p className="text-destructive text-sm mb-4">{error}</p>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => window.location.reload()}
            >
              Reload Page
            </Button>
          </div>
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

  return (
    <AppLayout>
      <div className="flex-1 flex flex-col bg-background relative">
        {/* Progress Overlay - Fixed to top */}
        {jobStatus === 'processing' && (
          <div className="absolute inset-0 bg-background/95 backdrop-blur-sm z-50 flex items-start justify-center pt-6">
            <Card className="w-[480px] p-6 shadow-lg sticky top-6">
              <div className="space-y-4">
                <div className="flex items-center gap-3">
                  <Loader2 className="h-5 w-5 animate-spin text-primary" />
                  <h3 className="text-lg font-semibold">Template Fill in Progress</h3>
                </div>

                {/* Progress bar */}
                <div className="space-y-2">
                  <Progress value={jobProgress} className="w-full h-2" />
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>{jobProgress}%</span>
                    <span>{jobMessage}</span>
                  </div>
                </div>

                {/* Details */}
                <div className="text-xs text-muted-foreground space-y-1 bg-muted/50 p-3 rounded-md">
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />
                    <span>Processing large documents may take several minutes</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-1.5 h-1.5 bg-muted-foreground rounded-full" />
                    <span>The page will auto-refresh when complete</span>
                  </div>
                </div>
              </div>
            </Card>
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
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => window.location.reload()}
                  >
                    Retry
                  </Button>
                </div>
              </AlertDescription>
            </Alert>
          </div>
        )}

        {/* Header */}
        <div className="border-b bg-card">
          <div className="px-6 py-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate('/app/re/templates')}
                  className="h-8 w-8 p-0"
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <div className="p-2 bg-muted rounded-lg">
                  <Table className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-foreground">Template Fill</h1>
                  <p className="text-xs text-muted-foreground">
                    {fillRun.document_metadata?.filename || 'Document'} → Excel Template
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 flex-wrap">
                  {(() => {
                    const statusInfo = formatStatus(fillRun.status);
                    return (
                      <Badge
                        variant={statusInfo.variant}
                        className={statusInfo.variant === 'success' ? 'bg-green-500 hover:bg-green-600 text-white' : ''}
                      >
                        {statusInfo.label}
                      </Badge>
                    );
                  })()}
                  {fillRun.current_stage && (
                    <Badge variant="outline" className="text-xs">
                      {formatStage(fillRun.current_stage)}
                    </Badge>
                  )}
                  {!fillRun.template_id && (
                    <Badge variant="destructive" className="text-xs">
                      Template Deleted
                    </Badge>
                  )}
                  {!fillRun.document_id && (
                    <Badge variant="destructive" className="text-xs">
                      Document Deleted
                    </Badge>
                  )}
                </div>
                {fillRun.status === 'completed' && fillRun.artifact ? (
                  <>
                    <Button
                      size="sm"
                      onClick={handleContinue}
                      className="bg-green-600 hover:bg-green-700 text-white shadow-sm"
                    >
                      <Download className="h-4 w-4 mr-2" />
                      Download Excel
                    </Button>
                    <FeedbackButton
                      operationType="template_fill"
                      entityId={fillRunId}
                      entitySummary={fillRun.template_snapshot?.name || 'Template Fill'}
                    />
                  </>
                ) : fillRun.status === 'awaiting_review' ? (
                  <Button
                    size="sm"
                    onClick={handleContinue}
                    className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white shadow-md hover:shadow-lg transition-all"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    Approve & Fill Template
                  </Button>
                ) : fillRun.status === 'filling' ? (
                  <Button size="sm" disabled className="bg-muted">
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Filling Template...
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </div>

        {/* Horizontal Split Layout */}
        <ResizablePanelGroup direction="horizontal" className="flex-1">
          {/* Left Panel: PDF Viewer */}
          <ResizablePanel defaultSize={50} minSize={30}>
            <div className="h-full flex flex-col bg-background overflow-hidden">
              <div className="bg-card px-4 py-2 border-b flex-shrink-0">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <h2 className="font-medium text-sm text-foreground">PDF Document</h2>
                  </div>
                  <div className="flex items-center gap-2">
                    {fillRun.document_metadata && (
                      <Badge variant="secondary">
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
              <div className="flex-1 overflow-auto">
                {pdfUrl ? (
                  <PDFViewer
                    pdfUrl={pdfUrl}
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
                        {!fillRun.document_id ? 'Source Document Deleted' : 'PDF Not Available'}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {!fillRun.document_id
                          ? 'The source PDF document for this fill run has been deleted.'
                          : 'The PDF is loading or temporarily unavailable.'}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </ResizablePanel>

          <ResizableHandle withHandle />

          {/* Right Panel: Tabbed Fields/Excel */}
          <ResizablePanel defaultSize={50} minSize={30}>
            <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col overflow-hidden">
              <div className="sticky top-0 z-10 bg-card border-b flex-shrink-0">
                <div className="flex items-center justify-between px-4">
                  <TabsList className="bg-transparent rounded-none p-0 h-auto border-b-0">
                    <TabsTrigger
                      value="excel"
                      className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 gap-2"
                    >
                      <Table className="h-4 w-4" />
                      <span className="text-sm font-medium">Excel Preview</span>
                      <Badge variant="secondary">
                        {fillRun.total_fields_mapped || 0} / {fillRun.total_fields_detected || 0}
                      </Badge>
                    </TabsTrigger>
                    <TabsTrigger
                      value="fields"
                      className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent px-4 py-2 gap-2"
                    >
                      <List className="h-4 w-4" />
                      <span className="text-sm font-medium">Extracted Fields</span>
                      <Badge variant="secondary">
                        {fillRun.total_fields_detected || 0}
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

              <TabsContent value="fields" className="flex-1 overflow-auto m-0">
                <FieldsList
                  fillRunId={fillRunId}
                  extractedData={fillRun.extracted_data}
                  fieldMapping={fillRun.field_mapping}
                  selectedText={selectedText}
                  onCitationClick={handleCitationClick}
                />
              </TabsContent>

              <TabsContent value="excel" className="flex-1 overflow-auto m-0">
                {!fillRun.template_id ? (
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
