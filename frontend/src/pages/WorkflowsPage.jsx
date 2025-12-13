/**
 * Workflows History Page - Redesigned
 *
 * ChatGPT-inspired professional table layout matching ExtractionHistoryPage
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import {
  ArrowLeft,
  FileText,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  DollarSign,
  Eye,
  Download,
  RefreshCw,
  Search,
  FileDown,
  Trash2,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from "../components/ui/dropdown-menu";
import Spinner from "../components/common/Spinner";
import DeleteConfirmDialog from "../components/common/DeleteConfirmDialog";
import AppLayout from "../components/layout/AppLayout";
import { listRuns, exportRun, getRun, getRunArtifact, deleteRun } from "../api";
import { exportWorkflowAsWord } from "../utils/exportWorkflow";

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();

  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [exportingId, setExportingId] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const runsData = await listRuns(getToken);
      setRuns(runsData || []);
    } catch (error) {
      console.error("Failed to fetch workflow runs:", error);
    } finally {
      setLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDeleteSuccess = async () => {
    // Refresh list after successful deletion
    await fetchData();
  };

  const handleExport = async (runId, format) => {
    setExportingId(runId);
    try {
      if (format === "word") {
        // Get the run metadata and artifact data separately
        const [runData, artifactData] = await Promise.all([
          getRun(getToken, runId),
          getRunArtifact(getToken, runId),
        ]);

        console.log("📦 Run data received:", runData);
        console.log("📄 Artifact data received:", artifactData);

        // Check if artifact exists
        if (!artifactData) {
          throw new Error(
            "This workflow run does not have exportable data. The artifact may still be processing or was not generated."
          );
        }

        await exportWorkflowAsWord(artifactData, runData);
        console.log("✅ Exported as Word document");
      } else {
        // PDF uses backend export
        const res = await exportRun(getToken, runId, format, "url");
        if (res.data?.url) {
          window.open(res.data.url, "_blank");
        }
      }
    } catch (error) {
      console.error("Export failed", error);
      alert(
        "Export failed: " + (error.response?.data?.detail || error.message)
      );
    } finally {
      setExportingId(null);
    }
  };

  // Filter workflows by search
  const filteredRuns = useMemo(() => {
    if (!searchQuery.trim()) return runs;

    const query = searchQuery.toLowerCase();
    return runs.filter((run) =>
      (run.workflow_name || "").toLowerCase().includes(query)
    );
  }, [runs, searchQuery]);

  const getStatusBadge = (status) => {
    const variants = {
      completed: { variant: "success", icon: CheckCircle },
      failed: { variant: "destructive", icon: XCircle },
      running: { variant: "default", icon: Clock },
      queued: { variant: "warning", icon: AlertCircle },
    };
    const config = variants[status] || variants.queued;
    const Icon = config.icon;

    return (
      <Badge variant={config.variant} className="text-xs gap-1">
        <Icon className="w-3 h-3" />
        {status}
      </Badge>
    );
  };

  const breadcrumbs = [
    { label: "Workflows", href: "/app/workflows" },
    { label: "All Runs" },
  ];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="h-full flex flex-col p-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate("/app/workflows")}
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back
                </Button>
              </div>
              <h1 className="text-2xl font-semibold text-foreground">
                All Workflow Runs
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                View and manage your workflow run history
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={fetchData}
              disabled={loading}
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              Refresh
            </Button>
          </div>

          {/* Search */}
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search workflows..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-10"
            />
          </div>
        </div>

        {/* Table */}
        {loading && runs.length === 0 ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 bg-muted/30 rounded-lg border-2 border-dashed border-border">
            <FileText className="w-16 h-16 text-muted-foreground mb-4 opacity-40" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              No workflow runs yet
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Start your first workflow to see results here
            </p>
            <Button onClick={() => navigate("/app/workflows")}>
              <FileText className="w-4 h-4 mr-2" />
              Start Workflow
            </Button>
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableHead>Workflow</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRuns.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="text-center py-8">
                      <p className="text-sm text-muted-foreground">
                        No workflows match your search
                      </p>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredRuns.map((run) => (
                    <TableRow
                      key={run.id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <TableCell>
                        <div className="flex flex-col max-w-md">
                          <span className="font-medium text-sm truncate">
                            {run.workflow_name || "Workflow"}
                          </span>
                          {run.error_message && (
                            <span className="text-xs text-destructive truncate mt-0.5">
                              {run.error_message}
                            </span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{getStatusBadge(run.status)}</TableCell>
                      <TableCell className="text-sm text-muted-foreground capitalize">
                        {run.mode}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(run.created_at).toLocaleDateString(
                          undefined,
                          {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          }
                        )}
                      </TableCell>
                      <TableCell className="text-right text-sm text-muted-foreground">
                        {run.completed_at
                          ? `${((run.latency_ms || 0) / 1000).toFixed(1)}s`
                          : "-"}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          {/* View Button */}
                          <button
                            onClick={() =>
                              navigate(`/app/workflows/runs/${run.id}`)
                            }
                            className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                            title="View workflow run"
                          >
                            <Eye className="w-4 h-4 text-muted-foreground hover:text-primary" />
                          </button>

                          {/* Export Dropdown */}
                          {run.status === "completed" && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button
                                  className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                                  disabled={exportingId === run.id}
                                  title="Export"
                                >
                                  <Download className="w-4 h-4 text-muted-foreground hover:text-primary" />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="w-48">
                                <DropdownMenuItem
                                  onClick={() => handleExport(run.id, "word")}
                                >
                                  <FileDown className="w-4 h-4 mr-2 text-primary" />
                                  Word Document
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem
                                  onClick={() => handleExport(run.id, "pdf")}
                                >
                                  <FileText className="w-4 h-4 mr-2 text-muted-foreground" />
                                  PDF
                                </DropdownMenuItem>
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}

                          {/* Delete Button */}
                          <DeleteConfirmDialog
                            itemId={run.id}
                            itemName={run.workflow_name || `Workflow ${run.id}`}
                            itemType="workflow run"
                            deleteApiCall={deleteRun}
                            getToken={getToken}
                            onSuccess={handleDeleteSuccess}
                            trigger={
                              <button className="p-1.5 hover:bg-destructive/10 rounded transition-colors">
                                <Trash2 className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                              </button>
                            }
                          />
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        )}

        {/* Search info */}
        {searchQuery && filteredRuns.length > 0 && (
          <div className="mt-4 text-sm text-muted-foreground">
            Showing {filteredRuns.length} of {runs.length} workflow runs
          </div>
        )}
      </div>
    </AppLayout>
  );
}
