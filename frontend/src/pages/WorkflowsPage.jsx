/**
 * All Workflow Runs Page
 *
 * Professional table layout with row selection, pagination,
 * status pills, and floating bulk-action bar.
 */

import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import {
  ArrowLeft,
  FileText,
  CheckCircle,
  XCircle,
  Eye,
  Download,
  RefreshCw,
  Search,
  FileDown,
  Trash2,
  Filter,
  Calendar,
  ChevronLeft,
  ChevronRight,
  X,
  RotateCcw,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Checkbox } from "../components/ui/checkbox";
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

const ITEMS_PER_PAGE = 10;

const getStatusBadge = (status) => {
  if (status === "completed")
    return (
      <span className="px-2 py-0.5 inline-flex items-center gap-1 text-xs font-semibold rounded-full bg-primary/10 text-primary border border-primary/20 whitespace-nowrap">
        <CheckCircle className="w-3 h-3" /> Completed
      </span>
    );
  if (status === "failed")
    return (
      <span className="px-2 py-0.5 inline-flex items-center gap-1 text-xs font-semibold rounded-full bg-destructive/10 text-destructive border border-destructive/20 whitespace-nowrap">
        <XCircle className="w-3 h-3" /> Failed
      </span>
    );
  return (
    <span className="px-2 py-0.5 inline-flex items-center gap-1 text-xs font-semibold rounded-full bg-amber-100 text-amber-800 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-400 dark:border-amber-800/50 whitespace-nowrap">
      <RefreshCw className="w-3 h-3 animate-spin" /> In Progress
    </span>
  );
};

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const { getToken } = useAppAuth();

  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [exportingId, setExportingId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);

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

  // Reset to page 1 when search changes
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  const handleDeleteSuccess = async () => {
    await fetchData();
  };

  const handleExport = async (runId, format) => {
    setExportingId(runId);
    try {
      if (format === "word") {
        const [runData, artifactData] = await Promise.all([
          getRun(getToken, runId),
          getRunArtifact(getToken, runId),
        ]);
        if (!artifactData) {
          throw new Error("Artifact not available — it may still be processing.");
        }
        await exportWorkflowAsWord(artifactData, runData);
      } else {
        const res = await exportRun(getToken, runId, format, "url");
        if (res.data?.url) {
          window.open(res.data.url, "_blank");
        }
      }
    } catch (error) {
      console.error("Export failed", error);
      alert("Export failed: " + (error.response?.data?.detail || error.message));
    } finally {
      setExportingId(null);
    }
  };

  const handleBulkDelete = async () => {
    await Promise.allSettled(
      [...selectedIds].map((id) => deleteRun(getToken, id))
    );
    setSelectedIds(new Set());
    await fetchData();
  };

  const toggleRow = (id, checked) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const filteredRuns = useMemo(() => {
    if (!searchQuery.trim()) return runs;
    const query = searchQuery.toLowerCase();
    return runs.filter((run) =>
      (run.workflow_name || "").toLowerCase().includes(query)
    );
  }, [runs, searchQuery]);

  const totalPages = Math.ceil(filteredRuns.length / ITEMS_PER_PAGE);
  const paginatedRuns = filteredRuns.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  const allPageSelected =
    paginatedRuns.length > 0 &&
    paginatedRuns.every((r) => selectedIds.has(r.id));

  const toggleAllPage = (checked) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      paginatedRuns.forEach((r) => {
        if (checked) next.add(r.id);
        else next.delete(r.id);
      });
      return next;
    });
  };

  // Page number rendering helper: 1 2 3 ... 8 9 10
  const getPageNumbers = () => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const pages = [];
    if (currentPage <= 3) {
      pages.push(1, 2, 3, 4, "...", totalPages);
    } else if (currentPage >= totalPages - 2) {
      pages.push(1, "...", totalPages - 3, totalPages - 2, totalPages - 1, totalPages);
    } else {
      pages.push(1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages);
    }
    return pages;
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
          <a
            onClick={() => navigate("/app/workflows")}
            className="inline-flex items-center text-sm text-muted-foreground hover:text-primary cursor-pointer mb-3 transition-colors"
          >
            <ArrowLeft className="w-4 h-4 mr-1" /> Back
          </a>
          <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-3">
            <div>
              <h1 className="text-2xl font-bold text-foreground">All Workflow Runs</h1>
              <p className="text-sm text-muted-foreground mt-1">
                View and manage your workflow run history.
              </p>
            </div>
            <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </div>
        </div>

        {/* Search + Filter Bar */}
        <div className="mb-5 flex flex-col sm:flex-row gap-3">
          <div className="relative flex-grow max-w-lg">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search workflows..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm">
              <Filter className="w-4 h-4 mr-2" /> Filter
            </Button>
            <Button variant="outline" size="sm">
              <Calendar className="w-4 h-4 mr-2" /> Date
            </Button>
          </div>
        </div>

        {/* Table */}
        {loading && runs.length === 0 ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : runs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 bg-muted/30 rounded-lg border-2 border-dashed border-border">
            <FileText className="w-14 h-14 text-muted-foreground mb-3 opacity-40" />
            <h3 className="text-lg font-medium text-foreground mb-1">No workflow runs yet</h3>
            <p className="text-sm text-muted-foreground mb-5">
              Start your first workflow to see results here
            </p>
            <Button onClick={() => navigate("/app/workflows")}>
              <FileText className="w-4 h-4 mr-2" />
              Start Workflow
            </Button>
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableHead className="w-12 px-4">
                      <Checkbox
                        checked={allPageSelected}
                        onCheckedChange={toggleAllPage}
                      />
                    </TableHead>
                    <TableHead>Workflow</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead>Created</TableHead>
                    <TableHead className="text-right">Duration</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginatedRuns.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-sm text-muted-foreground">
                        No workflows match your search
                      </TableCell>
                    </TableRow>
                  ) : (
                    paginatedRuns.map((run, index) => (
                      <TableRow
                        key={run.id}
                        className={`hover:bg-muted/40 transition-colors ${
                          index % 2 === 1 ? "bg-muted/20" : ""
                        }`}
                      >
                        {/* Checkbox */}
                        <TableCell className="w-12 px-4">
                          <Checkbox
                            checked={selectedIds.has(run.id)}
                            onCheckedChange={(c) => toggleRow(run.id, c)}
                          />
                        </TableCell>

                        {/* Workflow: icon + name + short ID */}
                        <TableCell>
                          <div className="flex items-center gap-3">
                            <div className="h-8 w-8 rounded bg-primary/10 flex items-center justify-center text-primary shrink-0">
                              <FileText className="w-4 h-4" />
                            </div>
                            <div>
                              <div className="text-sm font-medium text-foreground">
                                {run.workflow_name || "Workflow"}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {run.error_message
                                  ? run.error_message.slice(0, 50)
                                  : run.id
                                  ? `#${String(run.id).slice(0, 8)}`
                                  : "—"}
                              </div>
                            </div>
                          </div>
                        </TableCell>

                        {/* Status */}
                        <TableCell>{getStatusBadge(run.status)}</TableCell>

                        {/* Mode */}
                        <TableCell className="text-sm text-muted-foreground capitalize">
                          {run.mode || "—"}
                        </TableCell>

                        {/* Created */}
                        <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                          {new Date(run.created_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </TableCell>

                        {/* Duration */}
                        <TableCell className="text-right text-sm text-muted-foreground font-mono">
                          {run.latency_ms
                            ? `${(run.latency_ms / 1000).toFixed(1)}s`
                            : "—"}
                        </TableCell>

                        {/* Actions */}
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            {/* View */}
                            <button
                              onClick={() => navigate(`/app/workflows/runs/${run.id}`)}
                              className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                              title="View"
                            >
                              <Eye className="w-4 h-4 text-muted-foreground hover:text-primary" />
                            </button>

                            {/* Export (completed only) */}
                            {run.status === "completed" && (
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <button
                                    className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                                    disabled={exportingId === run.id}
                                    title="Export"
                                  >
                                    {exportingId === run.id ? (
                                      <Spinner size="sm" />
                                    ) : (
                                      <Download className="w-4 h-4 text-muted-foreground hover:text-primary" />
                                    )}
                                  </button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-44">
                                  <DropdownMenuItem onClick={() => handleExport(run.id, "word")}>
                                    <FileDown className="w-4 h-4 mr-2 text-primary" />
                                    Word Document
                                  </DropdownMenuItem>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem onClick={() => handleExport(run.id, "pdf")}>
                                    <FileText className="w-4 h-4 mr-2 text-muted-foreground" />
                                    PDF
                                  </DropdownMenuItem>
                                </DropdownMenuContent>
                              </DropdownMenu>
                            )}

                            {/* Retry placeholder (failed only) */}
                            {run.status === "failed" && (
                              <button
                                className="p-1.5 rounded opacity-40 cursor-not-allowed"
                                title="Retry (coming soon)"
                                disabled
                              >
                                <RotateCcw className="w-4 h-4 text-muted-foreground" />
                              </button>
                            )}

                            {/* Delete */}
                            <DeleteConfirmDialog
                              itemId={run.id}
                              itemName={run.workflow_name || `Workflow ${run.id}`}
                              itemType="workflow run"
                              deleteApiCall={deleteRun}
                              getToken={getToken}
                              onSuccess={handleDeleteSuccess}
                              trigger={
                                <button
                                  className="p-1.5 hover:bg-destructive/10 rounded transition-colors"
                                  title="Delete"
                                >
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

            {/* Pagination Footer */}
            {filteredRuns.length > 0 && (
              <div className="px-4 py-3 flex items-center justify-between border-t border-border bg-card">
                <p className="text-sm text-muted-foreground">
                  Showing{" "}
                  <span className="font-medium">
                    {(currentPage - 1) * ITEMS_PER_PAGE + 1}
                  </span>{" "}
                  to{" "}
                  <span className="font-medium">
                    {Math.min(currentPage * ITEMS_PER_PAGE, filteredRuns.length)}
                  </span>{" "}
                  of{" "}
                  <span className="font-medium">{filteredRuns.length}</span> entries
                </p>
                <nav className="inline-flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setCurrentPage((p) => p - 1)}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  {getPageNumbers().map((page, i) =>
                    page === "..." ? (
                      <span
                        key={`ellipsis-${i}`}
                        className="h-8 w-8 flex items-center justify-center text-sm text-muted-foreground"
                      >
                        …
                      </span>
                    ) : (
                      <Button
                        key={page}
                        variant={currentPage === page ? "default" : "outline"}
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setCurrentPage(page)}
                      >
                        {page}
                      </Button>
                    )
                  )}
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setCurrentPage((p) => p + 1)}
                    disabled={currentPage === totalPages || totalPages === 0}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </nav>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Floating Bulk Action Bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
          <div className="flex items-center bg-card border border-border shadow-xl rounded-full px-6 py-3 gap-6 pointer-events-auto">
            {/* Count */}
            <div className="flex items-center border-r border-border pr-6">
              <span className="bg-primary text-primary-foreground text-xs font-bold px-2 py-0.5 rounded-full mr-2">
                {selectedIds.size}
              </span>
              <span className="text-sm font-medium text-foreground">Selected</span>
            </div>

            {/* Bulk Delete */}
            <button
              onClick={handleBulkDelete}
              className="flex items-center text-sm font-medium text-destructive hover:text-destructive/80 transition-colors gap-2"
            >
              <Trash2 className="w-4 h-4" /> Delete
            </button>

            {/* Close */}
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
