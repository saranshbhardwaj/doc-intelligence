/**
 * Templates Management Page
 * Upload, view, and manage Excel templates for Real Estate vertical
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import AppLayout from '../../../components/layout/AppLayout';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from '../../../components/ui/alert-dialog';
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
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  listRETemplates,
  uploadRETemplate,
  deleteRETemplate,
  getTemplateUsage,
  startTemplateFill,
  listFillRuns,
  deleteFillRun,
  waitForTemplateAnalysis,
} from '../../../api/re-templates';

export default function TemplatesPage() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Get tab from URL, default to 'templates'
  const activeTab = searchParams.get('tab') || 'templates';
  const [templates, setTemplates] = useState([]);
  const [fillRuns, setFillRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Pagination for fill runs
  const [fillRunsOffset, setFillRunsOffset] = useState(0);
  const [hasMoreFillRuns, setHasMoreFillRuns] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

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

  useEffect(() => {
    // Reset pagination when switching tabs
    setFillRunsOffset(0);
    setHasMoreFillRuns(true);
    setFillRuns([]);
    loadData(true);
  }, [activeTab]);

  async function loadData(reset = false) {
    try {
      setLoading(true);
      setError(null);

      if (activeTab === 'templates') {
        const data = await listRETemplates(getToken);
        setTemplates(data || []);
      } else {
        const offset = reset ? 0 : fillRunsOffset;
        const data = await listFillRuns(getToken, 20, offset);

        if (reset) {
          setFillRuns(data || []);
          setFillRunsOffset(20);
        } else {
          setFillRuns(prev => [...prev, ...(data || [])]);
          setFillRunsOffset(prev => prev + 20);
        }

        // If we got less than 20 items, there's no more to load
        setHasMoreFillRuns(data && data.length === 20);
      }
    } catch (err) {
      console.error('❌ Failed to load data:', err);
      console.error('❌ Error details:', err.response?.data);
      setError(`Failed to load ${activeTab}`);
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreFillRuns() {
    try {
      setLoadingMore(true);
      const data = await listFillRuns(getToken, 20, fillRunsOffset);
      setFillRuns(prev => [...prev, ...(data || [])]);
      setFillRunsOffset(prev => prev + 20);
      setHasMoreFillRuns(data && data.length === 20);
    } catch (err) {
      console.error('Failed to load more fill runs:', err);
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleUpload(file, metadata) {
    try {
      setUploadError(null);

      // Upload template
      const uploadedTemplate = await uploadRETemplate(getToken, file, metadata);

      // Poll until template analysis is complete
      // This will wait for schema_metadata to be populated by the background task
      await waitForTemplateAnalysis(getToken, uploadedTemplate.id, 10000);

      // Reload templates to get updated list with analyzed template
      await loadData();
    } catch (err) {
      console.error('Upload failed:', err);
      setUploadError(err.message || 'Failed to upload template');
      throw err; // Re-throw so modal can handle it
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
      setTemplateUsage(usage);
    } catch (err) {
      console.error('Failed to check template usage:', err);
      setTemplateUsage(null);
    } finally {
      setCheckingUsage(false);
    }
  }

  async function confirmDeleteTemplate() {
    if (!templateToDelete) return;

    try {
      setIsDeleting(true);
      const result = await deleteRETemplate(getToken, templateToDelete.id);

      // Show success message if fill runs were affected
      if (result.affected_fill_runs > 0) {
        alert(`⚠️ ${result.affected_fill_runs} fill run(s) affected`);
      }

      await loadData();
      setShowDeleteAlert(false);
      setTemplateToDelete(null);
      setTemplateUsage(null);
    } catch (err) {
      console.error('Delete failed:', err);
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to delete template';
      alert(errorMsg);
    } finally {
      setIsDeleting(false);
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

      // Navigate to fill run page
      navigate(`/app/re/fills/${result.fill_run_id}`);
    } catch (err) {
      console.error('Failed to start fill run:', err);
      alert('Failed to start fill run: ' + (err.message || 'Unknown error'));
    } finally {
      setStartingFill(false);
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
      // Remove from local state
      setFillRuns(prev => prev.filter(fr => fr.id !== fillRunToDelete.id));
      setShowDeleteAlert(false);
      setFillRunToDelete(null);
    } catch (err) {
      console.error('Delete failed:', err);
      alert('Failed to delete fill run: ' + err.message);
    } finally {
      setIsDeleting(false);
    }
  }

  const filteredTemplates = templates.filter((t) =>
    t.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const filteredFillRuns = fillRuns.filter((f) =>
    f.template_snapshot?.name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <AppLayout>
      <div className="h-full flex flex-col bg-background">
        {/* Header - ChatGPT Inspired */}
        <div className="border-b bg-card/50 backdrop-blur supports-[backdrop-filter]:bg-card/50">
          <div className="px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary/10 rounded-lg">
                  <FileSpreadsheet className="h-5 w-5 text-primary" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-foreground">Excel Templates</h1>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Upload and manage templates for document filling
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button onClick={() => setShowUploadModal(true)}>
                  <Upload className="h-4 w-4 mr-2" />
                  Upload Template
                </Button>
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div className="px-6 flex gap-6 border-t">
            <button
              onClick={() => setSearchParams({ tab: 'templates' })}
              className={cn(
                'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
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
                'px-1 py-3 text-sm font-medium border-b-2 transition-colors',
                activeTab === 'fills'
                  ? 'border-primary text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              )}
            >
              Fill Runs
              {fillRuns.length > 0 && (
                <Badge variant="secondary" className="ml-2 text-xs">
                  {fillRuns.length}
                </Badge>
              )}
            </button>
          </div>
        </div>

        {/* Error Messages */}
        {uploadError && (
          <div className="mx-6 mt-4 bg-destructive/10 border border-destructive/20 rounded-lg p-3 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-destructive mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-destructive">Upload Failed</p>
              <p className="text-xs text-destructive/80 mt-0.5">{uploadError}</p>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full">
              <AlertCircle className="h-12 w-12 text-destructive mb-3" />
              <p className="text-destructive text-sm">{error}</p>
              <Button onClick={loadData} variant="outline" size="sm" className="mt-4">
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
            />
          ) : (
            <FillRunsList
              fillRuns={filteredFillRuns}
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              onViewFill={handleViewFill}
              onDeleteFill={handleDeleteFillRun}
              onLoadMore={loadMoreFillRuns}
              hasMore={hasMoreFillRuns}
              loadingMore={loadingMore}
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
      <AlertDialog open={showDeleteAlert} onOpenChange={setShowDeleteAlert}>
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
            <AlertDialogAction
              onClick={templateToDelete ? confirmDeleteTemplate : confirmDeleteFillRun}
              disabled={isDeleting || (templateUsage && !templateUsage.can_delete)}
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
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppLayout>
  );
}

// Templates Grid Component
function TemplatesGrid({ templates, searchQuery, onSearchChange, onView, onStartFill, onDelete }) {
  return (
    <div className="max-w-7xl mx-auto">
      {/* Search Bar */}
      <div className="mb-6">
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
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <FileSpreadsheet className="h-16 w-16 mb-4 text-muted-foreground/50" />
          <p className="text-sm">No templates found</p>
          <p className="text-xs mt-1">Upload an Excel template to get started</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              onView={onView}
              onStartFill={onStartFill}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// Template Card Component
function TemplateCard({ template, onView, onStartFill, onDelete }) {
  const totalFields = template.total_fields || 0;
  const totalSheets = template.total_sheets || 0;

  return (
    <div className="bg-card rounded-lg border border-border hover:border-primary/50 transition-all overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b bg-muted/30">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-foreground truncate">{template.name}</h3>
            {template.description && (
              <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                {template.description}
              </p>
            )}
          </div>
          {template.category && (
            <Badge variant="outline" className="ml-2 text-xs">
              {template.category}
            </Badge>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Fillable Fields</span>
          <Badge variant="secondary">{totalFields}</Badge>
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
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}

// Fill Runs List Component
function FillRunsList({ fillRuns, searchQuery, onSearchChange, onViewFill, onDeleteFill, onLoadMore, hasMore, loadingMore }) {
  return (
    <div className="max-w-7xl mx-auto">
      {/* Search Bar */}
      <div className="mb-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search fill runs..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      {/* Fill Runs List */}
      {fillRuns.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
          <Clock className="h-16 w-16 mb-4 text-muted-foreground/50" />
          <p className="text-sm">No fill runs found</p>
          <p className="text-xs mt-1">Start a fill run from a template</p>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {fillRuns.map((fillRun) => (
              <FillRunCard key={fillRun.id} fillRun={fillRun} onView={onViewFill} onDelete={onDeleteFill} />
            ))}
          </div>

          {/* Load More Button */}
          {hasMore && (
            <div className="flex justify-center mt-6">
              <Button
                variant="outline"
                onClick={onLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Loading...
                  </>
                ) : (
                  'Load More'
                )}
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// Fill Run Card Component
function FillRunCard({ fillRun, onView, onDelete }) {
  const statusConfig = {
    queued: { icon: Clock, variant: 'secondary', color: 'text-muted-foreground' },
    detecting_fields: { icon: Loader2, variant: 'default', color: 'text-primary', spin: true },
    fields_detected: { icon: CheckCircle, variant: 'default', color: 'text-primary' },
    mapping: { icon: Loader2, variant: 'default', color: 'text-primary', spin: true },
    awaiting_review: { icon: Eye, variant: 'default', color: 'text-primary' },
    extracting: { icon: Loader2, variant: 'default', color: 'text-primary', spin: true },
    filling: { icon: Loader2, variant: 'default', color: 'text-primary', spin: true },
    completed: { icon: CheckCircle, variant: 'success', color: 'text-success' },
    failed: { icon: AlertCircle, variant: 'destructive', color: 'text-destructive' },
  };

  const config = statusConfig[fillRun.status] || statusConfig.queued;
  const StatusIcon = config.icon;

  // Check if template or document was deleted
  const templateDeleted = !fillRun.template_id;
  const documentDeleted = !fillRun.document_id;

  return (
    <div className="bg-card rounded-lg border border-border hover:border-primary/50 transition-all p-4">
      <div className="flex items-start justify-between">
        <div
          className="flex-1 min-w-0 cursor-pointer"
          onClick={() => onView(fillRun.id)}
        >
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <h3 className="font-semibold text-foreground truncate">
              {fillRun.template_snapshot?.name || 'Unknown Template'}
            </h3>
            <Badge variant={config.variant} className="text-xs">
              <StatusIcon className={cn('h-3 w-3 mr-1', config.color, config.spin && 'animate-spin')} />
              {fillRun.status}
            </Badge>
            {templateDeleted && (
              <Badge variant="destructive" className="text-xs">
                Template Deleted
              </Badge>
            )}
            {documentDeleted && (
              <Badge variant="destructive" className="text-xs">
                Document Deleted
              </Badge>
            )}
          </div>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            <span className={cn(documentDeleted && "line-through opacity-50")}>
              {fillRun.document_metadata?.filename || 'Unknown Document'}
            </span>
            {fillRun.total_fields_mapped > 0 && (
              <span>
                {fillRun.total_fields_mapped} / {fillRun.total_fields_detected} fields mapped
              </span>
            )}
            <span>{new Date(fillRun.created_at).toLocaleDateString()}</span>
          </div>

          {fillRun.current_stage && (
            <p className="text-xs text-muted-foreground mt-2">
              Stage: {fillRun.current_stage}
            </p>
          )}
        </div>

        <div className="flex items-center gap-2 ml-4">
          {fillRun.status === 'completed' && fillRun.artifact && (
            <Button size="sm" variant="outline">
              <Download className="h-3 w-3 mr-1.5" />
              Download
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => onView(fillRun.id)}
          >
            <Eye className="h-3 w-3 mr-1.5" />
            View
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={(e) => {
              e.stopPropagation();
              onDelete(fillRun.id);
            }}
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>
    </div>
  );
}
