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
  DollarSign,
  Hash,
  CheckCircle,
  XCircle,
  AlertCircle,
  FileText,
  RefreshCw,
  Trash2,
  ArrowLeft,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
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

  const fetchRunDetails = useCallback(async () => {
    try {
      const runData = await getRun(getToken, runId);
      const artifactData = await getRunArtifact(getToken, runId);
      setRun(runData);
      if (artifactData) setArtifact(artifactData);
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
      navigate("/app/workflows");
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
      completed: <CheckCircle className="w-6 h-6 text-green-600" />,
      failed: <XCircle className="w-6 h-6 text-red-600" />,
      running: <RefreshCw className="w-6 h-6 text-blue-600 animate-spin" />,
      queued: <Clock className="w-6 h-6 text-yellow-600" />,
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
            <div
              key={idx}
              className="border-l-2 border-border dark:border-gray-700 pl-4"
            >
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
              <div className="font-medium text-muted-foreground dark:text-gray-300 text-sm mb-1">
                {key}:
              </div>
              <div className="ml-2">{renderArtifact(value, depth + 1)}</div>
            </div>
          ))}
        </div>
      );
    }

    return (
      <div className="text-sm text-muted-foreground dark:text-muted-foreground">
        {String(data)}
      </div>
    );
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
            <p className="text-muted-foreground dark:text-muted-foreground">
              Run not found
            </p>
            <Button onClick={() => navigate("/app/workflows")} className="mt-4">
              Back to Workflows
            </Button>
          </Card>
        </div>
      </AppLayout>
    );
  }

  const breadcrumbs = [
    { label: "Workflows", href: "/app/workflows" },
    { label: run.workflow_name || "Workflow Run" },
  ];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/app/workflows")}
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
              <p className="text-sm text-muted-foreground dark:text-gray-300">
                Run ID: {run.id.slice(0, 8)}...
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            {run.status === "completed" && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleExport("pdf")}
                  disabled={exporting}
                >
                  <Download className="w-4 h-4 mr-2" />
                  PDF
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleExport("xlsx")}
                  disabled={exporting}
                >
                  <Download className="w-4 h-4 mr-2" />
                  Excel
                </Button>
              </>
            )}
            <Button
              variant="outline"
              size="sm"
              onClick={handleDeleteClick}
              className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-950"
            >
              <Trash2 className="w-4 h-4 mr-2" />
              Delete
            </Button>
          </div>
        </div>
        {/* Metrics */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <Card className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900 rounded-lg">
                <FileText className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                  Mode
                </p>
                <p className="text-lg font-semibold text-foreground">
                  {run.mode}
                </p>
              </div>
            </div>
          </Card>

          {run.latency_ms && (
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-100 dark:bg-purple-900 rounded-lg">
                  <Clock className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                    Duration
                  </p>
                  <p className="text-lg font-semibold text-foreground">
                    {(run.latency_ms / 1000).toFixed(1)}s
                  </p>
                </div>
              </div>
            </Card>
          )}

          {run.cost_usd && (
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900 rounded-lg">
                  <DollarSign className="w-5 h-5 text-green-600 dark:text-green-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                    Cost
                  </p>
                  <p className="text-lg font-semibold text-foreground">
                    ${run.cost_usd.toFixed(3)}
                  </p>
                </div>
              </div>
            </Card>
          )}

          {run.token_usage && (
            <Card className="p-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 dark:bg-orange-900 rounded-lg">
                  <Hash className="w-5 h-5 text-orange-600 dark:text-orange-400" />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                    Tokens
                  </p>
                  <p className="text-lg font-semibold text-foreground">
                    {run.token_usage.toLocaleString()}
                  </p>
                </div>
              </div>
            </Card>
          )}
        </div>

        {/* Status Messages */}
        {(run.status === "running" || run.status === "queued") &&
          execution &&
          execution.runId === runId && (
            <Card className="p-6 mb-8 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
              <div className="mb-4">
                <div className="flex items-center gap-3 mb-3">
                  <RefreshCw className="w-5 h-5 text-blue-600 animate-spin" />
                  <p className="text-blue-900 dark:text-blue-200 font-semibold">
                    {run.status === "queued"
                      ? "Workflow Queued"
                      : "Workflow Running"}
                  </p>
                </div>
                <p className="text-sm text-blue-800 dark:text-blue-300 mb-4">
                  {execution.message ||
                    (run.status === "queued"
                      ? "Workflow is queued and will start shortly..."
                      : "Processing your workflow...")}
                </p>
              </div>

              {/* Progress Bar */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-blue-700 dark:text-blue-300 font-medium">
                    {execution.stage || "Initializing"}
                  </span>
                  <span className="text-blue-600 dark:text-blue-400 font-mono">
                    {execution.progress || 0}%
                  </span>
                </div>
                <div className="w-full bg-blue-100 dark:bg-blue-900 rounded-full h-3 overflow-hidden">
                  <div
                    className="bg-blue-600 dark:bg-blue-400 h-3 rounded-full transition-all duration-500 ease-out"
                    style={{ width: `${execution.progress || 0}%` }}
                  />
                </div>
              </div>
            </Card>
          )}

        {(run.status === "running" || run.status === "queued") &&
          execution &&
          execution.runId !== runId && (
            <Card className="p-6 mb-8 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800">
              <div className="flex items-center gap-3">
                <Clock className="w-5 h-5 text-yellow-600" />
                <p className="text-yellow-900 dark:text-yellow-200">
                  Workflow {run.status}... Refresh the page to see updates.
                </p>
              </div>
            </Card>
          )}

        {run.status === "failed" && (
          <Card className="p-6 mb-8 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
            <div className="flex items-center gap-3">
              <XCircle className="w-5 h-5 text-red-600" />
              <div>
                <p className="text-red-900 dark:text-red-200 font-semibold">
                  Workflow Failed
                </p>
                {run.error_message && (
                  <p className="text-sm text-red-700 dark:text-red-300 mt-1">
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
              <div className="bg-background dark:bg-card rounded-lg p-6 overflow-auto max-h-[600px]">
                {renderArtifact(
                  artifact.artifact.parsed ||
                    artifact.artifact.partial_parsed ||
                    artifact.artifact
                )}
              </div>

              {artifact.artifact.citation_snippets && (
                <div className="mt-6">
                  <h3 className="text-sm font-semibold text-muted-foreground dark:text-gray-300 mb-3">
                    Citations
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {Object.entries(artifact.artifact.citation_snippets).map(
                      ([cite, snippet]) => (
                        <div
                          key={cite}
                          className="bg-popover dark:bg-gray-700 p-3 rounded text-xs"
                        >
                          <span className="font-mono text-blue-600 dark:text-blue-400">
                            {cite}
                          </span>
                          <p className="text-muted-foreground dark:text-muted-foreground mt-1">
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
            <p className="text-muted-foreground dark:text-muted-foreground">
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
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
            >
              {deleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppLayout>
  );
}
