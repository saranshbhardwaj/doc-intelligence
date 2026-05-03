/**
 * Templates Management Page
 * Upload, view, and manage Excel templates for Real Estate vertical
 */

import React, { useState, useEffect, useRef } from 'react';
import { useAppAuth } from "@/hooks/useAppAuth";
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import AppLayout from '../../../components/layout/AppLayout';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
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
  ArrowUpDown,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { TemplatesPageSkeleton } from '../../../components/skeletons/PageSkeletons';
import {
  listRETemplates,
  uploadRETemplate,
  deleteRETemplate,
  getTemplateUsage,
  startTemplateFill,
  listFillRuns,
  getFillRunCount,
  deleteFillRun,
  renameRETemplate,
  renameFillRun,
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
  const [fillSortBy, setFillSortBy] = useState('date');
  const [fillSortOrder, setFillSortOrder] = useState('desc');

  // Upload state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadError, setUploadError] = useState(null);

  // Document selector state
  const [showDocumentSelector, setShowDocumentSelector] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [_startingFill, setStartingFill] = useState(false);

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
      const uploadedTemplate = await uploadRETemplate(getToken, file, metadata);
      // schema_metadata is populated immediately — no polling needed.
      setTemplates(prev => [uploadedTemplate, ...prev]);
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadError(err.response?.data?.detail || err.message || 'Failed to upload template');
      throw err; // Re-throw so modal shows the inline error and stays open
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

  async function handleDocumentSelected(selection) {
    if (!selectedTemplate) return;

    try {
      setStartingFill(true);
      const document = selection?.document || selection;
      const fillName = selection?.fillName?.trim();

      const result = await startTemplateFill(getToken, selectedTemplate.id, document.id, {
        name: fillName || undefined,
      });

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

  const filteredFillRuns = fillRuns.filter((f) => {
    const query = searchQuery.toLowerCase();
    const displayName = f.name || f.template_snapshot?.name || '';
    const docName = f.document_metadata?.filename || '';
    return displayName.toLowerCase().includes(query) || docName.toLowerCase().includes(query);
  });

  const sortedFillRuns = React.useMemo(() => {
    const statusRank = {
      queued: 0,
      detecting_fields: 1,
      fields_detected: 2,
      mapping: 3,
      awaiting_review: 4,
      extracting: 5,
      filling: 6,
      completed: 7,
      failed: 8,
    };

    const items = [...filteredFillRuns];
    items.sort((a, b) => {
      let comparison = 0;

      if (fillSortBy === 'name') {
        const left = (a.name || a.template_snapshot?.name || '').toLowerCase();
        const right = (b.name || b.template_snapshot?.name || '').toLowerCase();
        comparison = left.localeCompare(right);
      } else if (fillSortBy === 'status') {
        const left = statusRank[a.status] ?? 999;
        const right = statusRank[b.status] ?? 999;
        comparison = left - right;
      } else {
        const left = new Date(a.created_at || 0).getTime();
        const right = new Date(b.created_at || 0).getTime();
        comparison = left - right;
      }

      return fillSortOrder === 'asc' ? comparison : -comparison;
    });

    return items;
  }, [filteredFillRuns, fillSortBy, fillSortOrder]);

  const breadcrumb = (
    <div className="flex items-center gap-1.5 text-sm">
      <Link to="/app/re" className="text-muted-foreground hover:text-foreground transition-colors">
        Real Estate
      </Link>
      <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
      <span className="font-medium text-foreground">Templates</span>
    </div>
  );

  const uploadButton = (
    <Button
      onClick={() => setShowUploadModal(true)}
      size="sm"
      className="h-9 rounded-full border border-primary/20 bg-primary/10 px-4 text-xs font-medium text-primary shadow-sm transition-all hover:bg-primary hover:text-primary-foreground hover:shadow-md"
    >
      <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/15">
        <Upload className="h-3.5 w-3.5" />
      </span>
      Upload Template
    </Button>
  );

  if (loading) {
    return (
      <AppLayout headerLeft={breadcrumb} headerRight={uploadButton}>
        <TemplatesPageSkeleton />
      </AppLayout>
    );
  }

  return (
    <AppLayout headerLeft={breadcrumb} headerRight={uploadButton}>
      <div className="h-full flex flex-col bg-background">
        {/* Tabs */}
        <div className="px-4 sm:px-6 border-b">
          <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={() => setSearchParams({ tab: 'templates' })}
            className={cn(
              'inline-flex items-center gap-2 rounded-t-lg px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all duration-200',
              activeTab === 'templates'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/40'
            )}
            aria-pressed={activeTab === 'templates'}
          >
            Templates
            {templates.length > 0 && (
              <Badge
                variant="secondary"
                className={cn(
                  'text-xs',
                  activeTab === 'templates' && 'bg-primary/10 text-primary'
                )}
              >
                {templates.length}
              </Badge>
            )}
          </button>
          <button
            type="button"
            onClick={() => setSearchParams({ tab: 'fills' })}
            className={cn(
              'inline-flex items-center gap-2 rounded-t-lg px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-all duration-200',
              activeTab === 'fills'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/40'
            )}
            aria-pressed={activeTab === 'fills'}
          >
            Fill Runs
            {(fillRunCount ?? fillRuns.length) > 0 && (
              <Badge
                variant="secondary"
                className={cn(
                  'text-xs',
                  activeTab === 'fills' && 'bg-primary/10 text-primary'
                )}
              >
                {fillRunCount ?? fillRuns.length}
              </Badge>
            )}
          </button>
        </div>
        </div>

        {/* Mobile upload button */}
        <div className="md:hidden px-4 pt-3">
          <Button
            onClick={() => setShowUploadModal(true)}
            className="h-10 w-full rounded-2xl border border-primary/20 bg-primary/10 text-primary shadow-sm hover:bg-primary hover:text-primary-foreground"
            size="sm"
          >
            <span className="mr-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary/15">
              <Upload className="h-3.5 w-3.5" />
            </span>
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
              fillRuns={sortedFillRuns}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onViewFill={handleViewFill}
              onDeleteFill={handleDeleteFillRun}
              onRenameFillRun={async (fillRunId, name) => {
                await renameFillRun(getToken, fillRunId, name);
                setFillRuns(prev => prev.map(fr => fr.id === fillRunId ? { ...fr, name } : fr));
              }}
              sortBy={fillSortBy}
              onSortByChange={setFillSortBy}
              sortOrder={fillSortOrder}
              onSortOrderChange={setFillSortOrder}
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
        allowedExtensions={['pdf']}
        dialogDescription={(
          <>Choose the PDF source document to analyze and fill <span className="font-medium text-foreground">{selectedTemplate?.name || ''}</span></>
        )}
        emptyStateLabel="No PDFs in this collection"
        emptyStateDescription="Upload a PDF to your library first"
        submitLabel="Start Fill"
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
                            {templateUsage.processing_runs > 0 && (
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3.5 w-3.5 text-warning" />
                                <span>{templateUsage.processing_runs} processing</span>
                              </div>
                            )}
                            {templateUsage.awaiting_review_runs > 0 && (
                              <div className="flex items-center gap-1.5">
                                <Clock className="h-3.5 w-3.5 text-warning" />
                                <span>{templateUsage.awaiting_review_runs} awaiting review</span>
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
  const totalSheets = template.total_sheets || 0;
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
    <div className="bg-card rounded-lg border border-border hover:border-primary/50 transition-all overflow-hidden">
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
          {template.category ? (
            <Badge variant="outline" className="ml-2 text-xs flex-shrink-0">
              {template.category}
            </Badge>
          ) : null}
        </div>
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
          <Badge variant="secondary">{totalSheets}</Badge>
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
          className="px-2 sm:px-3"
        >
          <Eye className="h-3 w-3" />
        </Button>
        <Button
          size="sm"
          onClick={() => onStartFill(template.id)}
          className="flex-1"
        >
          <Play className="h-3 w-3 mr-1.5" />
          Start Fill
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

function FillRunNameCell({ fillRun, onRename }) {
  const [isEditing, setIsEditing] = React.useState(false);
  const [value, setValue] = React.useState('');
  const [isSaving, setIsSaving] = React.useState(false);

  const displayName = fillRun.name || fillRun.template_snapshot?.name || 'Unknown Template';
  const subName = fillRun.name ? (fillRun.template_snapshot?.name || null) : null;

  async function save() {
    const trimmed = value.trim();
    if (!trimmed) { setIsEditing(false); return; }
    setIsSaving(true);
    try { await onRename(fillRun.id, trimmed); }
    finally { setIsSaving(false); setIsEditing(false); }
  }

  if (isEditing) {
    return (
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          className="font-medium text-sm bg-transparent border-b border-primary outline-none text-foreground flex-1 min-w-0"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') save();
            else if (e.key === 'Escape') setIsEditing(false);
          }}
        />
        <button className="p-0.5 text-primary disabled:opacity-50 shrink-0" disabled={isSaving || !value.trim()} onClick={save}>
          {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
        </button>
        <button className="p-0.5 text-muted-foreground hover:text-foreground shrink-0" onClick={() => setIsEditing(false)}>
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
    );
  }

  return (
    <div
      className="flex items-center gap-1 group cursor-pointer"
      onClick={(e) => { e.stopPropagation(); setValue(displayName); setIsEditing(true); }}
    >
      <div className="min-w-0">
        <span className="font-medium text-sm truncate block">{displayName}</span>
        {subName && <span className="text-xs text-muted-foreground truncate block">{subName}</span>}
      </div>
      <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
    </div>
  );
}

// Fill Runs List Component — paginated table view
function FillRunsList({
  fillRuns,
  searchQuery,
  onSearchChange,
  onViewFill,
  onDeleteFill,
  onRenameFillRun,
  sortBy,
  onSortByChange,
  sortOrder,
  onSortOrderChange,
  page,
  pageSize,
  total,
  onPageChange,
}) {
  const totalPages = total != null ? Math.ceil(total / pageSize) : null;
  const from = total != null ? page * pageSize + 1 : null;
  const to   = total != null ? Math.min((page + 1) * pageSize, total) : null;

  return (
    <div className="flex flex-col gap-3">
      {/* Search + count row */}
      <div className="flex flex-col gap-2.5 sm:flex-row sm:items-center sm:justify-between">
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
        <div className="flex items-center gap-2">
          <Select value={sortBy} onValueChange={onSortByChange}>
            <SelectTrigger className="h-8 w-[140px] rounded-xl border-border/70 bg-background/72 text-xs">
              <ArrowUpDown className="mr-2 h-3.5 w-3.5" />
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="date">Date</SelectItem>
              <SelectItem value="status">Status</SelectItem>
              <SelectItem value="name">Name</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            className="h-8 rounded-xl px-3 text-xs"
            onClick={() => onSortOrderChange(sortOrder === 'asc' ? 'desc' : 'asc')}
          >
            {sortOrder === 'asc' ? 'Ascending' : 'Descending'}
          </Button>
          {total != null && (
            <span className="text-xs text-muted-foreground shrink-0">{total} total</span>
          )}
        </div>
      </div>

      {/* Table */}
      {fillRuns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Clock className="h-12 w-12 mb-3 text-muted-foreground/40" />
          <p className="text-sm">No fill runs found</p>
          <p className="text-xs mt-1">Start a fill run from a template</p>
        </div>
      ) : (
        <div className="library-table-shell overflow-hidden">
          <div className="library-scrollbar overflow-auto">
            <Table>
              <TableHeader className="sticky top-0 z-[1] bg-card/95 backdrop-blur">
                <TableRow className="border-b border-border/70 bg-transparent hover:bg-transparent">
                  <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground pl-4">
                    Template
                  </TableHead>
                  <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Status
                  </TableHead>
                  <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Document
                  </TableHead>
                  <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                    Date
                  </TableHead>
                  <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground pr-4 text-right">
                    Actions
                  </TableHead>
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
                    className="library-table-row group"
                  >
                    {/* Template name / fill run name */}
                    <TableCell className="library-table-cell pl-4 max-w-[220px]">
                      <FillRunNameCell fillRun={fillRun} onRename={onRenameFillRun} />
                      {templateDeleted && (
                        <span className="text-xs text-destructive">Template deleted</span>
                      )}
                    </TableCell>

                    {/* Status badge */}
                    <TableCell className="library-table-cell">
                      <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium', cfg.cls)}>
                        <Icon className={cn('h-3 w-3', cfg.spin && 'animate-spin')} />
                        {cfg.label}
                      </span>
                    </TableCell>

                    {/* Document filename */}
                    <TableCell className="library-table-cell max-w-[200px]">
                      <span className={cn('text-sm text-muted-foreground truncate block', documentDeleted && 'line-through opacity-50')}>
                        {fillRun.document_metadata?.filename || '—'}
                      </span>
                      {fillRun.total_fields_detected > 0 && (
                        <span className="text-xs text-muted-foreground/70">
                          {fillRun.total_fields_mapped ?? 0} / {fillRun.total_fields_detected} fields
                        </span>
                      )}
                    </TableCell>

                    {/* Date */}
                    <TableCell className="library-table-cell whitespace-nowrap text-sm text-muted-foreground">
                      {new Date(fillRun.created_at).toLocaleDateString()}
                    </TableCell>

                    {/* Actions */}
                    <TableCell className="library-table-cell pr-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        {fillRun.status === 'completed' && fillRun.artifact && (
                          <Button size="sm" variant="ghost" className="h-8 w-8 rounded-lg px-0">
                            <Download className="h-3.5 w-3.5" />
                          </Button>
                        )}
                        <Button size="sm" variant="ghost" className="h-8 w-8 rounded-lg px-0" onClick={() => onViewFill(fillRun.id)}>
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="h-8 w-8 rounded-lg px-0 text-muted-foreground hover:text-destructive"
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
