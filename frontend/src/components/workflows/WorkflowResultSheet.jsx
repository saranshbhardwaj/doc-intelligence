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
  CheckCircle,
  XCircle,
  AlertCircle,
  FileText,
  RefreshCw,
  Trash2,
  FileDown,
  FileSpreadsheet,
} from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "../ui/dropdown-menu";
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
import { exportWorkflowAsWord } from "../../utils/exportWorkflow";

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
    // Clear previous state when switching runs
    setRun(null);
    setArtifact(null);

    try {
      const runData = await getRun(getToken, runId);
      const artifactData = await getRunArtifact(getToken, runId);
      setRun(runData);
      setArtifact(artifactData || null); // Always set, clear if no data
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
      // Handle Word export locally
      if (format === "word") {
        await exportWorkflowAsWord(artifact, run);
      } else {
        // PDF and Excel use backend export
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
      completed: <CheckCircle className="w-5 h-5 text-success" />,
      failed: <XCircle className="w-5 h-5 text-destructive" />,
      running: <RefreshCw className="w-5 h-5 text-primary animate-spin" />,
      queued: <Clock className="w-5 h-5 text-warning" />,
    };
    return (
      icons[status] || <AlertCircle className="w-5 h-5 text-muted-foreground" />
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

  return (
    <>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent
          side="left"
          className="w-[1400px] sm:max-w-[1400px] overflow-y-auto bg-background "
        >
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Spinner size="lg" />
            </div>
          ) : !run ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-muted-foreground">Run not found</p>
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
                  </div>
                </div>
              </SheetHeader>

              {/* Action Buttons */}
              <div className="flex gap-2 flex-wrap">
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
                          <span className="font-medium">
                            Excel (Coming Soon)
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Needs workflow-specific setup
                          </span>
                        </div>
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                )}
                {run.status !== "running" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDeleteClick}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 className="w-4 h-4 mr-2" />
                    Delete
                  </Button>
                )}
              </div>

              {/* Status Messages */}
              {run.status === "running" && (
                <Card className="p-4 bg-primary/10 border-primary/20">
                  <div className="flex items-center gap-3 mb-3">
                    <RefreshCw className="w-5 h-5 text-primary animate-spin" />
                    <p className="text-primary font-semibold text-sm">
                      Workflow Running
                    </p>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Processing your workflow...
                  </p>
                </Card>
              )}

              {run.status === "queued" && (
                <Card className="p-4 bg-warning/10 border-warning/20">
                  <div className="flex items-center gap-3">
                    <Clock className="w-5 h-5 text-warning" />
                    <p className="text-warning text-sm">
                      Workflow queued... Will start shortly.
                    </p>
                  </div>
                </Card>
              )}

              {run.status === "failed" && (
                <Card className="p-4 bg-destructive/10 border-destructive/20">
                  <div className="flex items-center gap-3">
                    <XCircle className="w-5 h-5 text-destructive" />
                    <div>
                      <p className="text-destructive font-semibold text-sm">
                        Workflow Failed
                      </p>
                      {run.error_message && (
                        <p className="text-xs text-destructive/80 mt-1">
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
                  <Card className="p-4">
                    <h3 className="text-base font-semibold text-foreground mb-3">
                      Workflow Output
                    </h3>
                    <div className="bg-background rounded-lg p-4 overflow-auto max-h-[400px]">
                      {renderArtifact(
                        artifact.artifact.parsed ||
                          artifact.artifact.partial_parsed ||
                          artifact.artifact
                      )}
                    </div>

                    {/* Rich Citations with Metadata */}
                  </Card>
                ))}

              {!artifact && run.status === "completed" && (
                <Card className="p-6 text-center">
                  <p className="text-muted-foreground text-sm">
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
    </>
  );
}
