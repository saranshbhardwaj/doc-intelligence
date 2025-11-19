/**
 * Workflow Result Sheet
 *
 * Displays workflow run results in a side sheet (opens from left)
 * Replicates WorkflowResultPage content in a sheet for inline viewing
 */

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";
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
} from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import Spinner from "../common/Spinner";
import { getRun, getRunArtifact, exportRun, deleteRun } from "../../api";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import InvestmentMemoView from "./InvestmentMemoView";

export default function WorkflowResultSheet({ open, onOpenChange, runId }) {
  const { getToken } = useAuth();

  const [run, setRun] = useState(null);
  const [artifact, setArtifact] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchRunDetails = useCallback(async () => {
    if (!runId) return;

    setLoading(true);
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

  // Fetch run details when sheet opens
  useEffect(() => {
    if (open && runId) {
      fetchRunDetails();
    }
  }, [open, runId, fetchRunDetails]);

  const handleExport = async (format) => {
    setExporting(true);
    try {
      const res = await exportRun(getToken, runId, format, "url");

      if (res.data?.url) {
        window.open(res.data.url, "_blank");
      } else if (res.data instanceof Blob) {
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
      // Close sheet and dialog after successful deletion
      setDeleteDialogOpen(false);
      onOpenChange(false);
      // Optionally trigger a refresh of the runs list
      window.location.reload();
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
      completed: (
        <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
      ),
      failed: <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />,
      running: (
        <RefreshCw className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
      ),
      queued: (
        <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
      ),
    };
    return (
      icons[status] || (
        <AlertCircle className="w-5 h-5 text-muted-foreground dark:text-muted-foreground" />
      )
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

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="left"
          className="w-[1000px] sm:max-w-[1000px] overflow-y-auto bg-background "
        >
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Spinner size="lg" />
            </div>
          ) : !run ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-muted-foreground dark:text-muted-foreground">
                Run not found
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Header */}
              <SheetHeader>
                <div className="flex items-center gap-3">
                  {getStatusIcon(run.status)}
                  <div className="flex-1">
                    <SheetTitle className="text-xl font-bold text-foreground">
                      {run.workflow_name || "Workflow Run"}
                    </SheetTitle>
                    <p className="text-sm text-muted-foreground dark:text-muted-foreground mt-1">
                      Run ID: {run.id.slice(0, 8)}...
                    </p>
                  </div>
                </div>
              </SheetHeader>

              {/* Action Buttons */}
              <div className="flex gap-2 flex-wrap">
                {run.status === "completed" && (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleExport("pdf")}
                      disabled={exporting}
                      className="dark:border-gray-700 dark:hover:bg-card"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      PDF
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleExport("xlsx")}
                      disabled={exporting}
                      className="dark:border-gray-700 dark:hover:bg-card"
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
                  className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:text-red-300 dark:hover:bg-red-950 dark:border-gray-700"
                >
                  <Trash2 className="w-4 h-4 mr-2" />
                  Delete
                </Button>
              </div>

              {/* Metrics */}
              <div className="grid grid-cols-2 gap-3">
                <Card className="p-3 dark:bg-card dark:border-gray-700">
                  <div className="flex items-center gap-2">
                    <div className="p-2 bg-blue-100 dark:bg-blue-900 rounded-lg">
                      <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                        Mode
                      </p>
                      <p className="text-sm font-semibold text-foreground">
                        {run.mode}
                      </p>
                    </div>
                  </div>
                </Card>

                {run.latency_ms && (
                  <Card className="p-3 dark:bg-card dark:border-gray-700">
                    <div className="flex items-center gap-2">
                      <div className="p-2 bg-purple-100 dark:bg-purple-900 rounded-lg">
                        <Clock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          Duration
                        </p>
                        <p className="text-sm font-semibold text-foreground">
                          {(run.latency_ms / 1000).toFixed(1)}s
                        </p>
                      </div>
                    </div>
                  </Card>
                )}

                {run.cost_usd && (
                  <Card className="p-3 dark:bg-card dark:border-gray-700">
                    <div className="flex items-center gap-2">
                      <div className="p-2 bg-green-100 dark:bg-green-900 rounded-lg">
                        <DollarSign className="w-4 h-4 text-green-600 dark:text-green-400" />
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          Cost
                        </p>
                        <p className="text-sm font-semibold text-foreground">
                          ${run.cost_usd.toFixed(3)}
                        </p>
                      </div>
                    </div>
                  </Card>
                )}

                {run.token_usage && (
                  <Card className="p-3 dark:bg-card dark:border-gray-700">
                    <div className="flex items-center gap-2">
                      <div className="p-2 bg-orange-100 dark:bg-orange-900 rounded-lg">
                        <Hash className="w-4 h-4 text-orange-600 dark:text-orange-400" />
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          Tokens
                        </p>
                        <p className="text-sm font-semibold text-foreground">
                          {run.token_usage.toLocaleString()}
                        </p>
                      </div>
                    </div>
                  </Card>
                )}
              </div>

              {/* Status Messages */}
              {run.status === "running" && (
                <Card className="p-4 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800">
                  <div className="flex items-center gap-3 mb-3">
                    <RefreshCw className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
                    <p className="text-blue-900 dark:text-blue-200 font-semibold text-sm">
                      Workflow Running
                    </p>
                  </div>
                  <p className="text-xs text-blue-800 dark:text-blue-300">
                    Processing your workflow...
                  </p>
                </Card>
              )}

              {run.status === "queued" && (
                <Card className="p-4 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800">
                  <div className="flex items-center gap-3">
                    <Clock className="w-5 h-5 text-yellow-600 dark:text-yellow-400" />
                    <p className="text-yellow-900 dark:text-yellow-200 text-sm">
                      Workflow queued... Will start shortly.
                    </p>
                  </div>
                </Card>
              )}

              {run.status === "failed" && (
                <Card className="p-4 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800">
                  <div className="flex items-center gap-3">
                    <XCircle className="w-5 h-5 text-red-600 dark:text-red-400" />
                    <div>
                      <p className="text-red-900 dark:text-red-200 font-semibold text-sm">
                        Workflow Failed
                      </p>
                      {run.error_message && (
                        <p className="text-xs text-red-700 dark:text-red-300 mt-1">
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
                  <Card className="p-4 dark:bg-card dark:border-gray-700">
                    <h3 className="text-base font-semibold text-foreground mb-3">
                      Workflow Output
                    </h3>
                    <div className="bg-background  rounded-lg p-4 overflow-auto max-h-[400px]">
                      {renderArtifact(
                        artifact.artifact.parsed ||
                          artifact.artifact.partial_parsed ||
                          artifact.artifact
                      )}
                    </div>

                    {artifact.artifact.citation_snippets && (
                      <div className="mt-4">
                        <h4 className="text-sm font-semibold text-muted-foreground dark:text-gray-300 mb-2">
                          Citations
                        </h4>
                        <div className="grid grid-cols-1 gap-2">
                          {Object.entries(
                            artifact.artifact.citation_snippets
                          ).map(([cite, snippet]) => (
                            <div
                              key={cite}
                              className="bg-popover dark:bg-card p-2 rounded text-xs"
                            >
                              <span className="font-mono text-blue-600 dark:text-blue-400">
                                {cite}
                              </span>
                              <p className="text-muted-foreground dark:text-muted-foreground mt-1">
                                {snippet}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </Card>
                ))}

              {!artifact && run.status === "completed" && (
                <Card className="p-6 text-center dark:bg-card dark:border-gray-700">
                  <p className="text-muted-foreground dark:text-muted-foreground text-sm">
                    No artifact available for this run
                  </p>
                </Card>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent className="dark:bg-card dark:border-gray-700">
          <AlertDialogHeader>
            <AlertDialogTitle className="">
              Delete Workflow Run?
            </AlertDialogTitle>
            <AlertDialogDescription className="dark:text-muted-foreground">
              Are you sure you want to delete this workflow run? This will
              permanently delete the run and all associated artifacts from
              storage. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              disabled={deleting}
              className="dark:bg-gray-700  dark:hover:bg-gray-600"
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              disabled={deleting}
              className="bg-red-600 hover:bg-red-700 focus:ring-red-600 dark:bg-red-700 dark:hover:bg-red-800"
            >
              {deleting ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
