/**
 * Extraction History Page - Redesigned
 *
 * ChatGPT-inspired professional design with clean table and actions
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import AppLayout from "../components/layout/AppLayout";
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
import EnhancedDeleteWarning from "../components/common/EnhancedDeleteWarning";
import {
  FileText,
  Download,
  Eye,
  RefreshCw,
  Search,
  CheckCircle,
  Clock,
  XCircle,
  FileSpreadsheet,
  FileDown,
  FileJson,
  Trash2,
  ArrowLeft,
} from "lucide-react";
import { useUser, useUserActions } from "../store";
import { deleteExtraction, fetchExtractionResult } from "../api/extraction";
import { exportToExcel } from "../utils/excelExport";
import { exportExtractionAsWord } from "../utils/exportExtraction";
import { saveAs } from "file-saver";

export default function ExtractionHistoryPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const user = useUser();
  const { fetchExtractions, loadMoreExtractions } = useUserActions();

  const [loading, setLoading] = useState(false);
  const [exportingId, setExportingId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");

  const loadInitial = useCallback(async () => {
    setLoading(true);
    try {
      await fetchExtractions(getToken, { limit: 25, offset: 0 });
    } catch (err) {
      console.error("Failed to load extraction history", err);
    } finally {
      setLoading(false);
    }
  }, [fetchExtractions, getToken]);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  const handleLoadMore = async () => {
    try {
      await loadMoreExtractions(getToken);
    } catch (err) {
      console.error("Load more failed", err);
    }
  };

  const handleDelete = async (docId) => {
    // Refresh list after deletion
    await loadInitial();
  };

  const handleExport = async (id, format) => {
    setExportingId(id);
    try {
      const data = await fetchExtractionResult(id, getToken);

      if (format === "json") {
        const filename = data?.metadata?.filename || `extraction_${id}.json`;
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        saveAs(blob, filename);
      } else if (format === "excel") {
        await exportToExcel(data.data || data, data.metadata);
      } else if (format === "word") {
        await exportExtractionAsWord(data.data || data, data.metadata);
      }
    } catch (err) {
      console.error("Export failed", err);
      alert("Export failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setExportingId(null);
    }
  };

  // Filter extractions by search
  const filteredExtractions = useMemo(() => {
    if (!searchQuery.trim()) return user.extractions;

    const query = searchQuery.toLowerCase();
    return user.extractions.filter((ex) =>
      (ex.filename || "").toLowerCase().includes(query)
    );
  }, [user.extractions, searchQuery]);

  const getStatusBadge = (status) => {
    switch (status) {
      case "completed":
        return (
          <Badge variant="success" className="text-xs gap-1">
            <CheckCircle className="w-3 h-3" />
            Completed
          </Badge>
        );
      case "processing":
      case "running":
        return (
          <Badge variant="default" className="text-xs gap-1">
            <Clock className="w-3 h-3" />
            Processing
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="destructive" className="text-xs gap-1">
            <XCircle className="w-3 h-3" />
            Failed
          </Badge>
        );
      case "queued":
        return (
          <Badge variant="warning" className="text-xs gap-1">
            <Clock className="w-3 h-3" />
            Queued
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className="text-xs">
            {status || "Unknown"}
          </Badge>
        );
    }
  };

  const breadcrumbs = [{ label: "Extractions" }];

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
                  onClick={() => navigate("/app/extract")}
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Back
                </Button>
              </div>
              <h1 className="text-2xl font-semibold text-foreground">
                Extraction History
              </h1>
              <p className="text-sm text-muted-foreground mt-1">
                View and manage your document extractions
              </p>
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={loadInitial}
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
              placeholder="Search extractions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 h-10"
            />
          </div>
        </div>

        {/* Table */}
        {loading && user.extractions.length === 0 ? (
          <div className="flex justify-center py-12">
            <Spinner />
          </div>
        ) : user.extractions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 bg-muted/30 rounded-lg border-2 border-dashed border-border">
            <FileText className="w-16 h-16 text-muted-foreground mb-4 opacity-40" />
            <h3 className="text-lg font-medium text-foreground mb-2">
              No extractions yet
            </h3>
            <p className="text-sm text-muted-foreground mb-6">
              Extract documents to see them here
            </p>
            <Button onClick={() => navigate("/app/extract")}>
              <FileText className="w-4 h-4 mr-2" />
              Extract Document
            </Button>
          </div>
        ) : (
          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Pages</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredExtractions.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-8">
                      <p className="text-sm text-muted-foreground">
                        No extractions match your search
                      </p>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredExtractions.map((ex) => {
                    // Handle both id and extraction_id fields
                    const extractionId = ex.id || ex.extraction_id;

                    return (
                      <TableRow
                        key={extractionId}
                        className="hover:bg-muted/30 transition-colors"
                      >
                        <TableCell>
                          <div className="flex items-center gap-2 max-w-md">
                            <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                            <span className="font-medium text-sm truncate">
                              {ex.filename || extractionId}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>{getStatusBadge(ex.status)}</TableCell>
                        <TableCell className="text-right text-sm text-muted-foreground">
                          {ex.pages ?? ex.page_count ?? "-"}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {ex.started_at
                            ? new Date(ex.started_at).toLocaleDateString(
                                undefined,
                                {
                                  month: "short",
                                  day: "numeric",
                                  year: "numeric",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                }
                              )
                            : "-"}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center justify-end gap-1">
                            {/* View Button */}
                            <button
                              onClick={() =>
                                navigate(`/app/extractions/${extractionId}`)
                              }
                              className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                              title="View extraction"
                            >
                              <Eye className="w-4 h-4 text-muted-foreground hover:text-primary" />
                            </button>

                            {/* Export Dropdown */}
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <button
                                  className="p-1.5 hover:bg-primary/10 rounded transition-colors"
                                  disabled={exportingId === extractionId}
                                  title="Export"
                                >
                                  <Download className="w-4 h-4 text-muted-foreground hover:text-primary" />
                                </button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent align="end" className="w-48">
                                <DropdownMenuItem
                                  onClick={() =>
                                    handleExport(extractionId, "excel")
                                  }
                                >
                                  <FileSpreadsheet className="w-4 h-4 mr-2 text-success" />
                                  Excel Workbook
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onClick={() =>
                                    handleExport(extractionId, "word")
                                  }
                                >
                                  <FileDown className="w-4 h-4 mr-2 text-primary" />
                                  Word Document
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                              </DropdownMenuContent>
                            </DropdownMenu>

                            {/* Delete Button with Enhanced Warning */}
                            <EnhancedDeleteWarning
                              documentId={extractionId}
                              documentName={
                                ex.filename || `Extraction ${extractionId}`
                              }
                              getToken={getToken}
                              onConfirmDelete={() => handleDelete(extractionId)}
                              trigger={
                                <button className="p-1.5 hover:bg-destructive/10 rounded transition-colors">
                                  <Trash2 className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                                </button>
                              }
                            />
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })
                )}
              </TableBody>
            </Table>

            {/* Load More */}
            {user.pagination.has_more && (
              <div className="p-4 border-t border-border flex justify-center">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleLoadMore}
                  disabled={user.isLoadingExtractions}
                >
                  {user.isLoadingExtractions ? "Loading..." : "Load More"}
                </Button>
              </div>
            )}
          </div>
        )}

        {/* Search info */}
        {searchQuery && filteredExtractions.length > 0 && (
          <div className="mt-4 text-sm text-muted-foreground">
            Showing {filteredExtractions.length} of {user.extractions.length}{" "}
            extractions
          </div>
        )}
      </div>
    </AppLayout>
  );
}
