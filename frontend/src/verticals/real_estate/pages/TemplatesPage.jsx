/**
 * Templates Management Page
 * Upload, view, and manage Excel templates for Real Estate vertical
 */

import React, { useState, useEffect, useRef } from 'react';
import { useAppAuth } from "@/hooks/useAppAuth";
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import AppLayout from '../../../components/layout/AppLayout';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../../../components/ui/table';
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../../../components/ui/alert-dialog';
import UploadTemplateModal from '../components/UploadTemplateModal';
import DocumentSelectorDialog from '../components/DocumentSelectorDialog';
import ExcelViewerDialog from '../components/ExcelViewerDialog';
import {
  FileSpreadsheet,
  Upload,
  Play,
  Trash2,
  Search,
  Loader2,
  AlertCircle,
  CheckCircle,
  Clock,
  Download,
  Eye,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Check,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  listRETemplates,
  uploadRETemplate,
  deleteRETemplate,
  getTemplateUsage,
  startTemplateFill,
  listFillRuns,
  getFillRunCount,
  deleteFillRun,
  waitForTemplateAnalysis,
  renameRETemplate,
} from '../../../api/re-templates';

export default function TemplatesPage() {
  const { getToken } = useAppAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Get tab from URL, default to 'templates'
  const activeTab = searchParams.get('tab') || 'templates';
  const [templates, setTemplates] = useState([]);
  const [fillRuns, setFillRuns] = useState([]);
  const [fillRunCount, setFillRunCount] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination for fill runs (page-based)
  const FILL_PAGE_SIZE = 20;
  const [fillPage, setFillPage] = useState(0);
  const [fillTotal, setFillTotal] = useState(null);

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  // Document selector state
  const [showDocumentSelector, setShowDocumentSelector] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [startingFill, setStartingFill] = useState(false);

  // Excel viewer state
  const [showExcelViewer, setShowExcelViewer] = useState(false);
  const [viewedTemplate, setViewedTemplate] = useState(null);

  // Delete confirmation state
  const [showDeleteAlert, setShowDeleteAlert] = useState(false);
  const [templateToDelete, setTemplateToDelete] = useState(null);
  const [templateUsage, setTemplateUsage] = useState(null);
  const [fillRunToDelete, setFillRunToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [checkingUsage, setCheckingUsage] = useState(false);

  // Track if component is mounted to prevent state updates after unmount
  const isMountedRef = useRef(true);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setFillPage(0);
    setFillRuns([]);
    loadData(0);
  }, [activeTab]);

  async function loadData(page = fillPage) {
    try {
      setLoading(true);
      setError(null);

      if (activeTab === 'templates') {
        const [data, count] = await Promise.all([
          listRETemplates(getToken),
          getFillRunCount(getToken),
        ]);
        // Only update state if component is still mounted
        if (!isMountedRef.current) return;
        setTemplates(data || []);
        setFillRunCount(count);
      } else {
        const offset = page * FILL_PAGE_SIZE;
        const [data, total] = await Promise.all([
          listFillRuns(getToken, FILL_PAGE_SIZE, offset),
          getFillRunCount(getToken),
        ]);
        // Only update state if component is still mounted
        if (!isMountedRef.current) return;
        setFillRuns(data || []);
        setFillTotal(total);
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('Failed to load data:', err);
      setError(`Failed to load ${activeTab}`);
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }

  async function goToFillPage(newPage) {
    setFillPage(newPage);
    await loadData(newPage);
  }

  async function handleUpload(file, metadata) {
    try {
      setUploadError(null);

      // Step 1: Upload the file (fast HTTP POST — modal stays open only for this)
      const uploadedTemplate = await uploadRETemplate(getToken, file, metadata);

      // Step 2: Add to the list immediately with "analyzing" state so the user
      // sees feedback right away. The modal will close after this function returns.
      setTemplates(prev => [{ ...uploadedTemplate, _analyzing: true }, ...prev]);

      // Step 3: Poll in the background — don't await, don't block modal close.
      pollTemplateAnalysis(uploadedTemplate.id);
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadError(err.message || 'Failed to upload template');
      throw err; // Re-throw so modal shows the error and stays open
    }
  }

  // Background polling — runs after modal closes.
  async function pollTemplateAnalysis(templateId) {
    try {
      const maxPollAttempts = 6;

      for (let attempt = 0; attempt < maxPollAttempts; attempt += 1) {
        const analyzed = await waitForTemplateAnalysis(getToken, templateId, 30_000);
        const hasSchemaMetadata =
          analyzed?.schema_metadata && Object.keys(analyzed.schema_metadata).length > 0;

        setTemplates(prev =>
          prev.map(t => (
            t.id === templateId
              ? { ...analyzed, _analyzing: !hasSchemaMetadata, _analysisFailed: false }
              : t
          ))
        );

        if (hasSchemaMetadata) {
          toast.success('Template ready', {
            description: 'Template analysis completed successfully.',
          });
          return;
        }
      }

      throw new Error('Template analysis did not complete in time');
    } catch (err) {
      console.error('Template analysis polling failed:', err);
      setTemplates(prev =>
        prev.map(t =>
          t.id === templateId ? { ...t, _analyzing: false, _analysisFailed: true } : t
        )
      );
      toast.error('Template analysis failed', {
        description: 'The template was uploaded but could not be analyzed. Try deleting and re-uploading.',
      });
    }
  }

  async function handleDelete(templateId) {
    const template = templates.find((t) => t.id === templateId);
    setTemplateToDelete(template);
    setCheckingUsage(true);
    setShowDeleteAlert(true);

    try {
      // Fetch usage stats from backend
      const usage = await getTemplateUsage(getToken, templateId);
      if (!isMountedRef.current) return;
      setTemplateUsage(usage);
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('Failed to check template usage:', err);
      setTemplateUsage(null);
    } finally {
      if (isMountedRef.current) {
        setCheckingUsage(false);
      }
    }
  }

  async function confirmDeleteTemplate() {
    if (!templateToDelete) return;

    try {
      setIsDeleting(true);
      const result = await deleteRETemplate(getToken, templateToDelete.id);

      if (!isMountedRef.current) return;
      if (activeTab === 'templates') {
        await loadData(0);
      } else {
        await loadData(fillPage);
      }
      setShowDeleteAlert(false);
      setTemplateToDelete(null);
      setTemplateUsage(null);

      if (result.affected_fill_runs > 0) {
        toast.success(`Template deleted`, {
          description: `${result.affected_fill_runs} fill run(s) were also removed.`,
        });
      } else {
        toast.success(`Template deleted`);
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('Delete failed:', err);
      toast.error('Failed to delete template', {
        description: err.response?.data?.detail || err.message,
      });
    } finally {
      if (isMountedRef.current) {
        setIsDeleting(false);
      }
    }
  }

  function handleViewTemplate(templateId) {
    const template = templates.find((t) => t.id === templateId);
    setViewedTemplate(template);
    setShowExcelViewer(true);
  }

  async function handleStartFill(templateId) {
    const template = templates.find((t) => t.id === templateId);
    setSelectedTemplate(template);
    setShowDocumentSelector(true);
  }

  async function handleDocumentSelected(document) {
    if (!selectedTemplate) return;

    try {
      setStartingFill(true);

      const result = await startTemplateFill(getToken, selectedTemplate.id, document.id);

      if (!isMountedRef.current) return;
      // Navigate to fill run page
      navigate(`/app/re/fills/${result.fill_run_id}`);
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('Failed to start fill run:', err);
      alert('Failed to start fill run: ' + (err.message || 'Unknown error'));
    } finally {
      if (isMountedRef.current) {
        setStartingFill(false);
      }
    }
  }

  function handleViewFill(fillRunId) {
    navigate(`/app/re/fills/${fillRunId}`);
  }

  function handleDeleteFillRun(fillRunId) {
    const fillRun = fillRuns.find((fr) => fr.id === fillRunId);
    setFillRunToDelete(fillRun);
    setShowDeleteAlert(true);
  }

  async function confirmDeleteFillRun() {
    if (!fillRunToDelete) return;

    try {
      setIsDeleting(true);
      await deleteFillRun(getToken, fillRunToDelete.id);
      if (!isMountedRef.current) return;
      setShowDeleteAlert(false);
      setFillRunToDelete(null);
      await loadData(fillPage);
    } catch (err) {
      if (!isMountedRef.current) return;
      console.error('Delete failed:', err);
      toast.error('Failed to delete fill run', {
        description: err.message,
      });
    } finally {
      if (isMountedRef.current) {
        setIsDeleting(false);
      }
    }
  }

  const filteredTemplates = templates.filter((t) =>
    t.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredFillRuns = fillRuns.filter((f) =>
    f.template_snapshot?.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const uploadButton = (
    <Button onClick={() => setShowUploadModal(true)} size="sm" className="h-7 text-xs">
      <Upload className="h-3.5 w-3.5 mr-1.5" />
      Upload Template
    </Button>
  );

  return (
    <AppLayout headerRight={uploadButton}>
      <div className="h-full flex flex-col bg-background">
        {/* Tabs */}
        <div className="px-4 sm:px-6 flex gap-6 border-b overflow-x-auto">
          <button
            onClick={() => setSearchParams({ tab: 'templates' })}
            className={cn(
              'px-1 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all duration-200',
              activeTab === 'templates'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            Templates
            {templates.length > 0 && (
              <Badge variant="secondary" className="ml-2 text-xs">
                {templates.length}
              </Badge>
            )}
          </button>
          <button
            onClick={() => setSearchParams({ tab: 'fills' })}
            className={cn(
              'px-1 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all duration-200',
              activeTab === 'fills'
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            )}
          >
            Fill Runs
            {(fillRunCount ?? fillRuns.length) > 0 && (
              <Badge variant="secondary" className="ml-2 text-xs">
                {fillRunCount ?? fillRuns.length}
              </Badge>
            )}
          </button>
        </div>

        {/* Mobile upload button */}
        <div className="md:hidden px-4 pt-3">
          <Button onClick={() => setShowUploadModal(true)} className="w-full" size="sm">
            <Upload className="h-4 w-4 mr-2" />
            Upload Template
          </Button>
        </div>

        {/* Error Messages */}
        {uploadError && (
          <div className="mx-4 sm:mx-6 mt-4 bg-destructive/10 border border-destructive/20 rounded-lg p-3 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-destructive mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-destructive">Upload Failed</p>
              <p className="text-xs text-destructive/80 mt-0.5">{uploadError}</p>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <AlertCircle className="h-12 w-12 text-destructive mb-3" />
              <p className="text-destructive text-sm">{error}</p>
              <Button onClick={() => loadData(0)} variant="outline" size="sm" className="mt-4">
                Try Again
              </Button>
            </div>
          ) : activeTab === 'templates' ? (
            <TemplatesGrid
              templates={filteredTemplates}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onView={handleViewTemplate}
              onStartFill={handleStartFill}
              onDelete={handleDelete}
              onRename={async (templateId, name) => {
                await renameRETemplate(getToken, templateId, name);
                setTemplates((prev) => prev.map((t) => t.id === templateId ? { ...t, name } : t));
              }}
            />
          ) : (
            <FillRunsList
              fillRuns={filteredFillRuns}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onViewFill={handleViewFill}
              onDeleteFill={handleDeleteFillRun}
              page={fillPage}
              pageSize={FILL_PAGE_SIZE}
              total={fillTotal}
              onPageChange={goToFillPage}
            />
          )}
        </div>
      </div>

      {/* Upload Template Modal */}
      <UploadTemplateModal
        open={showUploadModal}
        onOpenChange={setShowUploadModal}
        onUpload={handleUpload}
      />

      {/* Document Selector Dialog */}
      <DocumentSelectorDialog
        open={showDocumentSelector}
        onOpenChange={setShowDocumentSelector}
        onSelect={handleDocumentSelected}
        templateName={selectedTemplate?.name || ''}
      />

      {/* Excel Viewer Dialog */}
      <ExcelViewerDialog
        open={showExcelViewer}
        onOpenChange={setShowExcelViewer}
        templateId={viewedTemplate?.id}
        templateName={viewedTemplate?.name}
      />

      {/* Delete Confirmation Dialog */}
      <AlertDialog
        open={showDeleteAlert}
        onOpenChange={(open) => {
          if (isDeleting) return; // Prevent closing while delete is in progress
          setShowDeleteAlert(open);
          if (!open) {
            setTemplateToDelete(null);
            setFillRunToDelete(null);
            setTemplateUsage(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {templateToDelete ? 'Delete Template?' : 'Delete Fill Run?'}
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              {templateToDelete ? (
                <div className="space-y-3">
                  <p>
                    This will permanently delete the template <strong className="text-foreground">"{templateToDelete.name}"</strong>. This action cannot be undone.
                  </p>

                  {/* Loading usage info */}
                  {checkingUsage && (
                    <div className="flex items-center gap-2 p-3 bg-muted rounded-md">
                      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                      <span className="text-sm text-muted-foreground">Checking usage...</span>
                    </div>
                  )}

                  {/* Show usage warning if there are fill runs */}
                  {!checkingUsage && templateUsage && templateUsage.total_fill_runs > 0 && (
                    <div className={cn(
                      "p-3 rounded-md border space-y-2",
                      templateUsage.can_delete
                        ? "bg-warning/10 border-warning/20"
                        : "bg-destructive/10 border-destructive/20"
                    )}>
                      <div className="flex items-start gap-2">
                        <AlertCircle className={cn(
                          "h-4 w-4 mt-0.5 shrink-0",
                          templateUsage.can_delete ? "text-warning" : "text-destructive"
                        )} />
                        <div className="space-y-1.5 flex-1 text-sm">
                          <p className={cn(
                            "font-medium",
                            templateUsage.can_delete ? "text-warning-foreground" : "text-destructive-foreground"
                          )}>
                            {templateUsage.can_delete ? 'Warning' : 'Cannot Delete'}
                          </p>
                          <p className="text-muted-foreground">
                            {templateUsage.warning}
                          </p>

                          {/* Usage stats */}
                          <div className="flex gap-4 pt-1 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1.5">
                              <CheckCircle className="h-3.5 w-3.5 text-success" />
                              <span>{templateUsage.completed_runs} completed</span>
                            </div>
                            {templateUsage.in_progress_runs > 0 && (
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3.5 w-3.5 text-warning" />
                                <span>{templateUsage.in_progress_runs} in progress</span>
                              </div>
                            )}
                            {templateUsage.failed_runs > 0 && (
                              <div className="flex items-center gap-1.5">
                                <AlertCircle className="h-3.5 w-3.5 text-destructive" />
                                <span>{templateUsage.failed_runs} failed</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ) : fillRunToDelete ? (
                <p>
                  This will permanently delete the fill run for <strong className="text-foreground">"{fillRunToDelete.template_snapshot?.name || 'Unknown'}"</strong>. This action cannot be undone.
                </p>
              ) : null}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <Button
              onClick={templateToDelete ? confirmDeleteTemplate : confirmDeleteFillRun}
              disabled={isDeleting || checkingUsage || (templateUsage && !templateUsage.can_delete)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Deleting...
                </>
              ) : (
                templateToDelete ? 'Delete Template' : 'Delete Fill Run'
              )}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppLayout>
  );
}

// Templates Grid Component
function TemplatesGrid({ templates, searchQuery, onSearchChange, onView, onStartFill, onDelete, onRename }) {
  return (
    <div className="max-w-7xl mx-auto">
      {/* Search Bar */}
      <div className="mb-4 sm:mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search templates..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Templates Grid */}
      {templates.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 sm:py-16 text-muted-foreground">
          <FileSpreadsheet className="h-16 w-16 mb-4 text-muted-foreground/50" />
          <p className="text-sm">No templates found</p>
          <p className="text-xs mt-1">Upload an Excel template to get started</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4">
          {templates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              onView={onView}
              onStartFill={onStartFill}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Template Card Component
function TemplateCard({ template, onView, onStartFill, onDelete, onRename }) {
  const totalFields = template.total_fields || 0;
  const totalSheets = template.total_sheets || 0;
  const isAnalyzing = template._analyzing;
  const analysisFailed = template._analysisFailed;
  const [isRenaming, setIsRenaming] = React.useState(false);
  const [renameValue, setRenameValue] = React.useState('');
  const [isSaving, setIsSaving] = React.useState(false);

  async function saveRename() {
    const trimmed = renameValue.trim();
    if (!trimmed) return;
    setIsSaving(true);
    try { await onRename(template.id, trimmed); } finally { setIsSaving(false); setIsRenaming(false); }
  }

  return (
    <div className={cn(
      "bg-card rounded-lg border transition-all overflow-hidden",
      isAnalyzing ? "border-primary/30" :
      analysisFailed ? "border-destructive/30" :
      "border-border hover:border-primary/50"
    )}>
      {/* Header */}
      <div className="p-4 border-b bg-muted/30">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            {isRenaming ? (
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <input
                  autoFocus
                  className="font-semibold bg-transparent border-b border-primary outline-none text-foreground flex-1 min-w-0 text-sm"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') saveRename();
                    else if (e.key === 'Escape') setIsRenaming(false);
                  }}
                />
                <button className="p-0.5 text-primary disabled:opacity-50 flex-shrink-0" disabled={isSaving || !renameValue.trim()} onClick={saveRename}>
                  {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                </button>
                <button className="p-0.5 text-muted-foreground hover:text-foreground flex-shrink-0" onClick={() => setIsRenaming(false)}>
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            ) : (
              <div
                className="flex items-center gap-1 group cursor-pointer"
                onClick={() => { setRenameValue(template.name); setIsRenaming(true); }}
              >
                <h3 className="font-semibold text-foreground truncate">{template.name}</h3>
                <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
              </div>
            )}
            {template.description && (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {template.description}
              </p>
            )}
          </div>
          {isAnalyzing ? (
            <Badge variant="secondary" className="text-xs flex-shrink-0 gap-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              Analyzing…
            </Badge>
          ) : analysisFailed ? (
            <Badge variant="destructive" className="text-xs flex-shrink-0 gap-1">
              <AlertCircle className="h-3 w-3" />
              Failed
            </Badge>
          ) : template.category ? (
            <Badge variant="outline" className="ml-2 text-xs flex-shrink-0">
              {template.category}
            </Badge>
          ) : null}
        </div>
        {analysisFailed && (
          <p className="text-xs text-destructive mt-2">
            Analysis failed — delete and re-upload to try again.
          </p>
        )}
      </div>

      {/* Stats */}
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Created</span>
          {template.created_at
            ? <Badge variant="secondary">{new Date(template.created_at).toLocaleDateString()}</Badge>
            : <span className="text-xs text-muted-foreground italic">—</span>}
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Sheets</span>
          {isAnalyzing
            ? <span className="text-xs text-muted-foreground italic">—</span>
            : <Badge variant="secondary">{totalSheets}</Badge>}
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Times Used</span>
          <span className="text-foreground font-medium">{template.usage_count || 0}</span>
        </div>
      </div>

      {/* Actions */}
      <div className="p-4 border-t bg-muted/10 flex gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => onView(template.id)}
          disabled={isAnalyzing}
          className="px-2 sm:px-3"
        >
          <Eye className="h-3 w-3" />
        </Button>
        <Button
          size="sm"
          onClick={() => onStartFill(template.id)}
          disabled={isAnalyzing || analysisFailed}
          className="flex-1"
          title={
            isAnalyzing ? 'Template is still being analyzed' :
            analysisFailed ? 'Analysis failed — re-upload to use' :
            undefined
          }
        >
          {isAnalyzing ? (
            <>
              <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
              Analyzing…
            </>
          ) : (
            <>
              <Play className="h-3 w-3 mr-1.5" />
              Start Fill
            </>
          )}
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => onDelete(template.id)}
          className="px-2 sm:px-3"
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

const FILL_STATUS_CONFIG = {
  queued:           { icon: Clock,        label: 'Queued',          cls: 'text-muted-foreground bg-muted/50' },
  detecting_fields: { icon: Loader2,      label: 'Detecting',       cls: 'text-primary bg-primary/10', spin: true },
  fields_detected:  { icon: CheckCircle,  label: 'Fields Detected', cls: 'text-primary bg-primary/10' },
  mapping:          { icon: Loader2,      label: 'Mapping',         cls: 'text-primary bg-primary/10', spin: true },
  awaiting_review:  { icon: Eye,          label: 'Awaiting Review', cls: 'text-amber-600 bg-amber-50 dark:bg-amber-950/30' },
  extracting:       { icon: Loader2,      label: 'Extracting',      cls: 'text-primary bg-primary/10', spin: true },
  filling:          { icon: Loader2,      label: 'Filling',         cls: 'text-primary bg-primary/10', spin: true },
  completed:        { icon: CheckCircle,  label: 'Completed',       cls: 'text-green-600 bg-green-50 dark:bg-green-950/30' },
  failed:           { icon: AlertCircle,  label: 'Failed',          cls: 'text-destructive bg-destructive/10' },
};

// Fill Runs List Component — paginated table view
function FillRunsList({ fillRuns, searchQuery, onSearchChange, onViewFill, onDeleteFill, page, pageSize, total, onPageChange }) {
  const totalPages = total != null ? Math.ceil(total / pageSize) : null;
  const from = total != null ? page * pageSize + 1 : null;
  const to   = total != null ? Math.min((page + 1) * pageSize, total) : null;

  return (
    <div className="flex flex-col gap-3">
      {/* Search + count row */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search fill runs..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9 h-8 text-sm"
          />
        </div>
        {total != null && (
          <span className="text-xs text-muted-foreground shrink-0">{total} total</span>
        )}
      </div>

      {/* Table */}
      {fillRuns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Clock className="h-12 w-12 mb-3 text-muted-foreground/40" />
          <p className="text-sm">No fill runs found</p>
          <p className="text-xs mt-1">Start a fill run from a template</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/30 hover:bg-muted/30">
                <TableHead className="text-xs font-medium py-2 pl-4">Template</TableHead>
                <TableHead className="text-xs font-medium py-2">Status</TableHead>
                <TableHead className="text-xs font-medium py-2">Document</TableHead>
                <TableHead className="text-xs font-medium py-2">Date</TableHead>
                <TableHead className="text-xs font-medium py-2">Stage</TableHead>
                <TableHead className="text-xs font-medium py-2 pr-4 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {fillRuns.map((fillRun) => {
                const cfg = FILL_STATUS_CONFIG[fillRun.status] || FILL_STATUS_CONFIG.queued;
                const Icon = cfg.icon;
                const templateDeleted = !fillRun.template_id;
                const documentDeleted = !fillRun.document_id;
                return (
                  <TableRow
                    key={fillRun.id}
                    className="hover:bg-muted/30 transition-colors group"
                  >
                    {/* Template name / fill run name */}
                    <TableCell className="py-2.5 pl-4 max-w-[220px]">
                      {fillRun.name && (
                        <span className="font-medium text-sm truncate block">{fillRun.name}</span>
                      )}
                      <span className={cn('truncate block', fillRun.name ? 'text-xs text-muted-foreground' : 'font-medium text-sm')}>
                        {fillRun.template_snapshot?.name || 'Unknown Template'}
                      </span>
                      {templateDeleted && (
                        <span className="text-xs text-destructive">Template deleted</span>
                      )}
                    </TableCell>

                    {/* Status badge */}
                    <TableCell className="py-2.5">
                      <span className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', cfg.cls)}>
                        <Icon className={cn('h-3 w-3', cfg.spin && 'animate-spin')} />
                        {cfg.label}
                      </span>
                    </TableCell>

                    {/* Document filename */}
                    <TableCell className="py-2.5 max-w-[200px]">
                      <span className={cn('text-xs text-muted-foreground truncate block', documentDeleted && 'line-through opacity-50')}>
                        {fillRun.document_metadata?.filename || '—'}
                      </span>
                      {fillRun.total_fields_detected > 0 && (
                        <span className="text-xs text-muted-foreground/70">
                          {fillRun.total_fields_mapped ?? 0} / {fillRun.total_fields_detected} fields
                        </span>
                      )}
                    </TableCell>

                    {/* Date */}
                    <TableCell className="py-2.5 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(fillRun.created_at).toLocaleDateString()}
                    </TableCell>

                    {/* Stage */}
                    <TableCell className="py-2.5 text-xs text-muted-foreground">
                      {fillRun.current_stage ? fillRun.current_stage.replace(/_/g, ' ') : '—'}
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="py-2.5 pr-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {fillRun.status === 'completed' && fillRun.artifact && (
                          <Button size="sm" variant="ghost" className="h-7 px-2">
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => onViewFill(fillRun.id)}>
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-7 px-2 text-muted-foreground hover:text-destructive"
                          onClick={() => onDeleteFill(fillRun.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Pagination controls */}
      {totalPages != null && totalPages > 1 && (
        <div className="flex items-center justify-between pt-1">
          <span className="text-xs text-muted-foreground">
            {from}–{to} of {total}
          </span>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2"
              disabled={page === 0}
              onClick={() => onPageChange(page - 1)}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </Button>
            <span className="text-xs px-2 text-muted-foreground">
              Page {page + 1} / {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="h-7 px-2"
              disabled={page >= totalPages - 1}
              onClick={() => onPageChange(page + 1)}
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
