/**
 * Workflow Result Page
 *
 * Display workflow run results with artifact viewer and export options
 */

import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { useWorkflowDraft, useWorkflowDraftActions } from "../store";
import {
  Download,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  FileText,
  RefreshCw,
  Trash2,
  ArrowLeft,
  FileDown,
  FileSpreadsheet,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "../components/ui/dropdown-menu";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import { getRun, getRunArtifact, exportRun, deleteRun } from "../api";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import InvestmentMemoView from "../components/workflows/InvestmentMemoView";
import { exportWorkflowAsWord } from "../utils/exportWorkflow";

export default function WorkflowResultPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();

  // Zustand execution state for progress tracking
  const { execution } = useWorkflowDraft();
  const { reconnectWorkflowExecution } = useWorkflowDraftActions();

  const [run, setRun] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // NEW: mark orphan/legacy run (no workflow_id)
  const [isLegacy, setIsLegacy] = useState(false);
  const [registering, setRegistering] = useState(false);

  const fetchRunDetails = useCallback(async () => {
    // Clear previous state when switching runs
    setRun(null);
    setArtifact(null);

    try {
      const runData = await getRun(getToken, runId);
      const artifactData = await getRunArtifact(getToken, runId);

      // mark legacy runs (no workflow_id)
      const legacy = !runData?.workflow_id;
      setIsLegacy(Boolean(legacy));

      // store run and artifact (explicitly set null if not present)
      setRun(runData || null);
      setArtifact(artifactData || null);
    } catch (error) {
      console.error("Failed to fetch run details:", error);
    } finally {
      setLoading(false);
    }
  }, [getToken, runId]);

  useEffect(() => {
    fetchRunDetails();
  }, [fetchRunDetails]);

  useEffect(() => {
    // Reconnect to SSE if this is an active workflow execution
    if (
      run &&
      execution &&
      execution.runId === runId &&
      (run.status === "running" || run.status === "queued")
    ) {
      console.log("🔄 Reconnecting to workflow execution on result page");
      reconnectWorkflowExecution(getToken);
    }

    // Cleanup on unmount
    return () => {
      if (execution && execution.cleanup && execution.runId === runId) {
        execution.cleanup();
      }
    };
  }, [run, runId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleExport = async (format) => {
    setExporting(true);
    try {
      // Handle Word export locally
      if (format === "word") {
        await exportWorkflowAsWord(artifact, run);
        console.log("✅ Exported as Word document");
      } else {
        // PDF and Excel use backend export
        const res = await exportRun(getToken, runId, format, "url");

        if (res.data?.url) {
          // R2 signed URL
          window.open(res.data.url, "_blank");
        } else if (res.data instanceof Blob) {
          // Direct download
          const url = window.URL.createObjectURL(res.data);
          const a = document.createElement("a");
          a.href = url;
          a.download = res.data.filename || `workflow_${runId}.${format}`;
          document.body.appendChild(a);
          a.click();
          window.URL.revokeObjectURL(url);
          document.body.removeChild(a);
        }
      }
    } catch (error) {
      console.error("Export failed:", error);
      alert(
        "Export failed: " + (error.response?.data?.detail || error.message)
      );
    } finally {
      setExporting(false);
    }
  };

  const handleDeleteClick = () => {
    setDeleteDialogOpen(true);
  };

  const handleDeleteConfirm = async () => {
    setDeleting(true);
    try {
      await deleteRun(getToken, runId);
      // Navigate back to workflows page after successful deletion
      navigate("/app/workflows/history");
    } catch (error) {
      console.error("Failed to delete run:", error);
      alert(
        "Failed to delete workflow run: " +
          (error.response?.data?.detail || error.message)
      );
      setDeleting(false);
      setDeleteDialogOpen(false);
    }
  };

  const getStatusIcon = (status) => {
    const icons = {
      completed: <CheckCircle className="w-6 h-6 text-success" />,
      failed: <XCircle className="w-6 h-6 text-destructive" />,
      running: <RefreshCw className="w-6 h-6 text-primary animate-spin" />,
      queued: <Clock className="w-6 h-6 text-warning" />,
    };
    return (
      icons[status] || <AlertCircle className="w-6 h-6 text-muted-foreground" />
    );
  };

  const renderArtifact = (data, depth = 0) => {
    if (!data) return null;

    if (Array.isArray(data)) {
      return (
        <div className="space-y-2 ml-4">
          {data.map((item, idx) => (
            <div key={idx} className="border-l-2 border-border pl-4">
              {renderArtifact(item, depth + 1)}
            </div>
          ))}
        </div>
      );
    }

    if (typeof data === "object") {
      return (
        <div className="space-y-3">
          {Object.entries(data).map(([key, value]) => (
            <div key={key} className="ml-4">
              <div className="font-medium text-muted-foreground text-sm mb-1">
                {key}:
              </div>
              <div className="ml-2">{renderArtifact(value, depth + 1)}</div>
            </div>
          ))}
        </div>
      );
    }

    return <div className="text-sm text-muted-foreground">{String(data)}</div>;
  };

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-screen">
          <Spinner size="lg" />
        </div>
      </AppLayout>
    );
  }

  if (!run) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-screen">
          <Card className="p-8 text-center">
            <p className="text-muted-foreground">Run not found</p>
            <Button
              onClick={() => navigate("/app/workflows/history")}
              className="mt-4"
            >
              Back to Workflows
            </Button>
          </Card>
        </div>
      </AppLayout>
    );
  }

  const breadcrumbs = [
    { label: "Workflows", href: "/app/workflows/history" },
    { label: run.workflow_name || "Workflow Run" },
  ];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/app/workflows/history")}
          className="mb-4"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Workflows
        </Button>

        {/* Page Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            {getStatusIcon(run.status)}
            <div>
              <h1 className="text-2xl font-bold text-foreground">
                {run.workflow_name || "Workflow Run"}
              </h1>
            </div>
          </div>
          <div className="flex gap-2">
            {run.status === "completed" && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" disabled={exporting}>
                    <Download className="w-4 h-4 mr-2" />
                    {exporting ? "Exporting..." : "Export"}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuItem onClick={() => handleExport("word")}>
                    <FileDown className="w-4 h-4 mr-3 text-primary" />
                    <div className="flex flex-col">
                      <span className="font-medium">Word Document</span>
                      <span className="text-xs text-muted-foreground">
                        Professional report (.docx)
                      </span>
                    </div>
                  </DropdownMenuItem>

                  <DropdownMenuSeparator />

                  <DropdownMenuItem onClick={() => handleExport("pdf")}>
                    <FileText className="w-4 h-4 mr-3 text-destructive" />
                    <div className="flex flex-col">
                      <span className="font-medium">PDF</span>
                      <span className="text-xs text-muted-foreground">
                        Portable document (.pdf)
                      </span>
                    </div>
                  </DropdownMenuItem>

                  <DropdownMenuItem
                    onClick={() => handleExport("xlsx")}
                    disabled
                  >
                    <FileSpreadsheet className="w-4 h-4 mr-3 text-muted-foreground" />
                    <div className="flex flex-col">
                      <span className="font-medium">Excel (Coming Soon)</span>
                      <span className="text-xs text-muted-foreground">
                        Needs workflow-specific setup
                      </span>
                    </div>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleDeleteClick}
              className="text-destructive hover:bg-destructive/10"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>

        {/* Status Messages */}
        {(run.status === "running" || run.status === "queued") &&
          execution &&
          execution.runId === runId && (
            <Card className="p-6 mb-8 bg-primary/10 border-primary/20">
              <div className="mb-4">
                <div className="flex items-center gap-3 mb-3">
                  <RefreshCw className="w-5 h-5 text-primary animate-spin" />
                  <p className="text-primary font-semibold">
                    {run.status === "queued"
                      ? "Workflow Queued"
                      : "Workflow Running"}
                  </p>
                </div>
                <p className="text-sm text-muted-foreground mb-4">
                  {execution.message ||
                    (run.status === "queued"
                      ? "Workflow is queued and will start shortly..."
                      : "Processing your workflow...")}
                </p>
              </div>

              {/* Progress Bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-primary font-medium">
                    {execution.stage || "Initializing"}
                  </span>
                  <span className="text-primary font-mono">
                    {execution.progress || 0}%
                  </span>
                </div>
                <div className="w-full bg-muted rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-primary h-3 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${execution.progress || 0}%` }}
                  />
                </div>
              </div>
            </Card>
          )}

        {(run.status === "running" || run.status === "queued") &&
          execution &&
          execution.runId !== runId && (
            <Card className="p-6 mb-8 bg-warning/10 border-warning/20">
              <div className="flex items-center gap-3">
                <Clock className="w-5 h-5 text-warning" />
                <p className="text-warning">
                  Workflow {run.status}... Refresh the page to see updates.
                </p>
              </div>
            </Card>
          )}

        {run.status === "failed" && (
          <Card className="p-6 mb-8 bg-destructive/10 border-destructive/20">
            <div className="flex items-center gap-3">
              <XCircle className="w-5 h-5 text-destructive" />
              <div>
                <p className="text-destructive font-semibold">
                  Workflow Failed
                </p>
                {run.error_message && (
                  <p className="text-sm text-destructive/80 mt-1">
                    {run.error_message}
                  </p>
                )}
              </div>
            </div>
          </Card>
        )}

        {/* Artifact Display */}
        {artifact &&
          artifact.artifact &&
          (run.workflow_name === "Investment Memo" ? (
            <InvestmentMemoView artifact={artifact} run={run} />
          ) : (
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Workflow Output
              </h2>
              <div className="bg-background rounded-lg p-6 overflow-auto max-h-[600px]">
                {renderArtifact(
                  artifact.artifact.parsed ||
                    artifact.artifact.partial_parsed ||
                    artifact.artifact
                )}
              </div>

              {artifact.artifact.citation_snippets && (
                <div className="mt-6">
                  <h3 className="text-sm font-semibold text-muted-foreground mb-3">
                    Citations
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(artifact.artifact.citation_snippets).map(
                      ([cite, snippet]) => (
                        <div
                          key={cite}
                          className="bg-muted p-3 rounded text-xs"
                        >
                          <span className="font-mono text-primary">{cite}</span>
                          <p className="text-muted-foreground mt-1">
                            {snippet}
                          </p>
                        </div>
                      )
                    )}
                  </div>
                </div>
              )}
            </Card>
          ))}

        {!artifact && run.status === "completed" && (
          <Card className="p-8 text-center">
            <p className="text-muted-foreground">
              No artifact available for this run
            </p>
          </Card>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Workflow Run?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this workflow run? This will
              permanently delete the run and all associated artifacts from
              storage. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleting}
              className="bg-destructive hover:bg-destructive/90"
            >
              {deleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppLayout>
  );
}
