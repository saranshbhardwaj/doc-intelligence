/**
 * DocumentsTable Component
 *
 * Table view for documents with search, filter, and sort
 * Inspiration-aligned design with colored file icons, date column, and pill badges
 *
 * Input:
 *   - documents: Array<{id, filename, status, page_count, chunk_count, has_embeddings, created_at}>
 *   - loading: boolean
 *   - getToken: () => Promise<string>
 *   - onDeleteDocument: (docId, filename) => Promise<void>
 *   - onUpload: () => void
 *   - deletingDocId: string | null - ID of document currently being deleted
 */

import { useState, useEffect } from "react";
import {
  FileText,
  FileSpreadsheet,
  File,
  Search,
  Filter,
  Upload,
  Trash2,
  Clock,
  AlertCircle,
  ArrowUpDown,
  Loader2,
} from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";
import { Progress } from "../ui/progress";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import Spinner from "../common/Spinner";
import DocumentUsageBadge from "../common/DocumentUsageBadge";
import EnhancedDeleteWarning from "../common/EnhancedDeleteWarning";

// Returns colored icon config based on file extension
function getFileIcon(filename) {
  const ext = filename?.toLowerCase().split(".").pop();
  if (ext === "pdf") {
    return { Icon: FileText, bg: "bg-red-50 dark:bg-red-900/20", color: "text-red-500 dark:text-red-400" };
  }
  if (["xlsx", "xls"].includes(ext)) {
    return { Icon: FileSpreadsheet, bg: "bg-green-50 dark:bg-green-900/20", color: "text-green-600 dark:text-green-400" };
  }
  return { Icon: File, bg: "bg-blue-50 dark:bg-blue-900/20", color: "text-blue-500 dark:text-blue-400" };
}

function formatDate(isoString) {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function DocumentsTable({
  documents = [],
  loading = false,
  getToken,
  onDeleteDocument,
  onUpload,
  deletingDocId = null,
  page = 0,
  setPage,
  totalDocs = 0,
  pageSize = 50,
  sortBy = "created_at",
  setSortBy,
  sortOrder = "desc",
  setSortOrder,
  searchQuery = "",
  setSearchQuery,
  statusFilter = null,
  setStatusFilter,
}) {
  // Map UI sort names to API field names
  const sortFieldMap = {
    name: "filename",
    pages: "page_count",
    chunks: "chunk_count",
    status: "status",
    created_at: "created_at",
  };

  const toggleSort = (field) => {
    const apiField = sortFieldMap[field] || field;
    if (sortBy === apiField) {
      setSortOrder?.(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy?.(apiField);
      setSortOrder?.("asc");
    }
  };

  // Debounce search input
  const [localSearch, setLocalSearch] = useState(searchQuery);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearchQuery?.(localSearch);
    }, 300);
    return () => clearTimeout(timer);
  }, [localSearch, setSearchQuery]);

  const getStatusBadge = (doc) => {
    if (doc.status === "completed" && doc.has_embeddings) {
      return (
        <Badge variant="success" className="text-xs font-medium rounded-full gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          Ready
        </Badge>
      );
    } else if (doc.status === "processing") {
      return (
        <div className="min-w-0 sm:min-w-[140px] space-y-1.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-primary" />
              <span className="text-xs font-medium text-foreground">
                {doc.status_detail || "Processing"}
              </span>
            </div>
            <span className="text-xs text-muted-foreground">
              {doc.progress_percent || 0}%
            </span>
          </div>
          <Progress
            value={doc.progress_percent || 0}
            variant="primary"
            className="h-1.5"
            showShimmer={true}
          />
        </div>
      );
    } else if (doc.status === "failed") {
      return (
        <Badge variant="destructive" className="text-xs font-medium rounded-full gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-current" />
          Failed
        </Badge>
      );
    } else {
      return (
        <Badge variant="secondary" className="text-xs font-medium rounded-full gap-1.5">
          <AlertCircle className="w-3 h-3" />
          No Embeddings
        </Badge>
      );
    }
  };

  // Initial loading state (first load, no documents yet)
  if (loading && documents.length === 0) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  // Empty state (only show full empty state if not loading and no documents)
  if (!loading && documents.length === 0 && totalDocs === 0) {
    return (
      <div className="library-table-shell flex flex-col items-center justify-center py-20">
        <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-3xl bg-primary/10">
          <FileText className="w-10 h-10 text-primary opacity-60" />
        </div>
        <h3 className="mb-2 text-lg font-semibold text-foreground">
          No documents yet
        </h3>
        <p className="mb-6 text-sm text-muted-foreground">
          Upload documents to get started
        </p>
        <Button onClick={onUpload} className="rounded-full gap-2">
          <Upload className="w-4 h-4" />
          Upload Document
        </Button>
      </div>
    );
  }

  return (
    <div className="relative flex flex-col">
      {loading && documents.length > 0 && (
        <div className="absolute right-5 top-4 z-10 flex items-center gap-2 rounded-full border border-border/70 bg-background/90 px-3 py-1.5 shadow-sm backdrop-blur-sm">
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Loading...</span>
        </div>
      )}

      <div className="library-table-shell flex flex-col">
        <div className="library-toolbar">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          </div>

          <div className="flex flex-col gap-2.5 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search documents"
                value={localSearch}
                onChange={(e) => setLocalSearch(e.target.value)}
                className="h-10 rounded-xl border-border/70 bg-background/72 pl-9"
              />
            </div>

            <div className="flex flex-col gap-2.5 sm:flex-row">
              <Select
                value={statusFilter || "all"}
                onValueChange={(v) => setStatusFilter?.(v === "all" ? null : v)}
              >
                <SelectTrigger className="h-10 w-full rounded-xl border-border/70 bg-background/72 sm:w-[160px]">
                  <Filter className="mr-2 h-4 w-4" />
                  <SelectValue placeholder="All Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="completed">Ready</SelectItem>
                  <SelectItem value="processing">Processing</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>

              <Select value={sortBy} onValueChange={setSortBy}>
                <SelectTrigger className="h-10 w-full rounded-xl border-border/70 bg-background/72 sm:w-[160px]">
                  <ArrowUpDown className="mr-2 h-4 w-4" />
                  <SelectValue placeholder="Sort by" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="filename">Name</SelectItem>
                  <SelectItem value="page_count">Pages</SelectItem>
                  <SelectItem value="chunk_count">Chunks</SelectItem>
                  <SelectItem value="created_at">Date</SelectItem>
                </SelectContent>
              </Select>

              <Button onClick={onUpload} className="h-10 rounded-full px-5 gap-2">
                <Upload className="w-4 h-4" />
                Upload
              </Button>
            </div>
          </div>

          {(searchQuery || statusFilter) && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <span>
                Showing {documents.length} of {totalDocs} documents
              </span>
              <button
                onClick={() => {
                  setLocalSearch("");
                  setSearchQuery?.("");
                  setStatusFilter?.(null);
                }}
                className="text-primary hover:underline"
              >
                Clear filters
              </button>
            </div>
          )}
        </div>

        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="sticky top-0 z-[1] bg-card/95 backdrop-blur">
              <TableRow className="border-b border-border/70 bg-transparent hover:bg-transparent">
              <TableHead
                className="cursor-pointer text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:bg-muted/50"
                onClick={() => toggleSort("name")}
              >
                <div className="flex items-center gap-2">
                  Document Name
                  {sortBy === "filename" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead className="text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Status
              </TableHead>
              <TableHead
                className="hidden sm:table-cell cursor-pointer text-right text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:bg-muted/50"
                onClick={() => toggleSort("pages")}
              >
                <div className="flex items-center justify-end gap-2">
                  Pages
                  {sortBy === "page_count" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead
                className="hidden sm:table-cell cursor-pointer text-right text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground transition-colors hover:bg-muted/50"
                onClick={() => toggleSort("chunks")}
              >
                <div className="flex items-center justify-end gap-2">
                  Chunks
                  {sortBy === "chunk_count" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead className="hidden md:table-cell text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Date Added
              </TableHead>
              <TableHead className="hidden md:table-cell text-xs font-bold uppercase tracking-[0.18em] text-muted-foreground">
                Usage
              </TableHead>
              <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-10 text-center">
                    <p className="text-sm text-muted-foreground">
                      No documents match your filters
                    </p>
                  </TableCell>
                </TableRow>
              ) : (
                documents.map((doc) => {
                  const { Icon, bg, color } = getFileIcon(doc.filename);
                  return (
                    <TableRow
                      key={doc.id}
                      className={`library-table-row ${
                        deletingDocId === doc.id
                          ? "pointer-events-none bg-muted/50 opacity-50"
                          : ""
                      }`}
                    >
                      <TableCell className="library-table-cell">
                        <div className="flex items-center gap-3">
                          <div className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-xl ${bg}`}>
                            <Icon className={`h-4 w-4 ${color}`} />
                          </div>
                          <span className="max-w-[160px] sm:max-w-xs truncate text-sm font-medium">
                            {doc.filename}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="library-table-cell">{getStatusBadge(doc)}</TableCell>
                      <TableCell className="hidden sm:table-cell library-table-cell text-right text-sm text-muted-foreground">
                        {doc.page_count || 0}
                      </TableCell>
                      <TableCell className="hidden sm:table-cell library-table-cell text-right text-sm text-muted-foreground">
                        {doc.chunk_count || 0}
                      </TableCell>
                      <TableCell className="hidden md:table-cell library-table-cell whitespace-nowrap text-sm text-muted-foreground">
                        {formatDate(doc.created_at)}
                      </TableCell>
                      <TableCell className="hidden md:table-cell library-table-cell">
                        {doc.status === "completed" && doc.has_embeddings && (
                          <DocumentUsageBadge
                            documentId={doc.id}
                            getToken={getToken}
                          />
                        )}
                      </TableCell>
                      <TableCell className="library-table-cell" onClick={(e) => e.stopPropagation()}>
                        <EnhancedDeleteWarning
                          documentId={doc.id}
                          documentName={doc.filename}
                          getToken={getToken}
                          onConfirmDelete={() =>
                            onDeleteDocument?.(doc.id, doc.filename)
                          }
                          isDeleting={deletingDocId === doc.id}
                          trigger={
                            <button
                              className="rounded-lg p-1.5 transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
                              disabled={deletingDocId === doc.id}
                            >
                              <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                            </button>
                          }
                        />
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>

        {totalDocs > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border/70 px-5 py-4 sm:px-6">
            <div className="text-sm text-muted-foreground">
              Showing {page * pageSize + 1}-
              {Math.min((page + 1) * pageSize, totalDocs)} of {totalDocs} documents
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage?.(page - 1)}
                disabled={page === 0 || loading}
                className="rounded-full"
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage?.(page + 1)}
                disabled={(page + 1) * pageSize >= totalDocs || loading}
                className="rounded-full"
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
