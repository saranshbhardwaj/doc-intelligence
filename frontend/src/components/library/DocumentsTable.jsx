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
  CheckCircle,
  Clock,
  AlertCircle,
  XCircle,
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
        <div className="min-w-[140px] space-y-1.5">
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
      <div className="flex flex-col items-center justify-center py-16 rounded-2xl border-2 border-dashed border-border">
        <div className="w-20 h-20 bg-primary/10 rounded-3xl flex items-center justify-center mb-5">
          <FileText className="w-10 h-10 text-primary opacity-60" />
        </div>
        <h3 className="text-lg font-semibold text-foreground mb-2">
          No documents yet
        </h3>
        <p className="text-sm text-muted-foreground mb-6">
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
    <div className="space-y-4 relative">
      {/* Loading indicator for subsequent loads */}
      {loading && documents.length > 0 && (
        <div className="absolute top-0 right-0 z-10 flex items-center gap-2 bg-background/80 backdrop-blur-sm px-3 py-1.5 rounded-md border border-border shadow-sm">
          <Loader2 className="w-4 h-4 animate-spin text-primary" />
          <span className="text-sm text-muted-foreground">Loading...</span>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={localSearch}
            onChange={(e) => setLocalSearch(e.target.value)}
            className="pl-9 h-10"
          />
        </div>

        {/* Status Filter */}
        <Select
          value={statusFilter || "all"}
          onValueChange={(v) => setStatusFilter?.(v === "all" ? null : v)}
        >
          <SelectTrigger className="w-full sm:w-[160px] h-10">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="All Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="completed">Ready</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>

        {/* Sort */}
        <Select value={sortBy} onValueChange={setSortBy}>
          <SelectTrigger className="w-full sm:w-[160px] h-10">
            <ArrowUpDown className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Sort by" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="filename">Name</SelectItem>
            <SelectItem value="page_count">Pages</SelectItem>
            <SelectItem value="chunk_count">Chunks</SelectItem>
            <SelectItem value="created_at">Date</SelectItem>
          </SelectContent>
        </Select>

        {/* Upload Button */}
        <Button onClick={onUpload} className="h-10 rounded-full px-5 gap-2">
          <Upload className="w-4 h-4" />
          Upload
        </Button>
      </div>

      {/* Filter info */}
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

      {/* Table */}
      <div className="rounded-2xl border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors text-xs uppercase tracking-wide font-bold text-muted-foreground"
                onClick={() => toggleSort("name")}
              >
                <div className="flex items-center gap-2">
                  Document Name
                  {sortBy === "filename" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wide font-bold text-muted-foreground">
                Status
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors text-right text-xs uppercase tracking-wide font-bold text-muted-foreground"
                onClick={() => toggleSort("pages")}
              >
                <div className="flex items-center justify-end gap-2">
                  Pages
                  {sortBy === "page_count" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors text-right text-xs uppercase tracking-wide font-bold text-muted-foreground"
                onClick={() => toggleSort("chunks")}
              >
                <div className="flex items-center justify-end gap-2">
                  Chunks
                  {sortBy === "chunk_count" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wide font-bold text-muted-foreground">
                Date Added
              </TableHead>
              <TableHead className="text-xs uppercase tracking-wide font-bold text-muted-foreground">
                Usage
              </TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
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
                    className={`transition-all duration-300 ${
                      deletingDocId === doc.id
                        ? "opacity-50 pointer-events-none bg-muted/50"
                        : "hover:bg-muted/30"
                    }`}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <div className={`w-9 h-9 rounded-lg ${bg} flex items-center justify-center flex-shrink-0`}>
                          <Icon className={`w-4 h-4 ${color}`} />
                        </div>
                        <span className="font-medium text-sm truncate max-w-xs">
                          {doc.filename}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>{getStatusBadge(doc)}</TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">
                      {doc.page_count || 0}
                    </TableCell>
                    <TableCell className="text-right text-sm text-muted-foreground">
                      {doc.chunk_count || 0}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                      {formatDate(doc.created_at)}
                    </TableCell>
                    <TableCell>
                      {doc.status === "completed" && doc.has_embeddings && (
                        <DocumentUsageBadge
                          documentId={doc.id}
                          getToken={getToken}
                        />
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
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
                            className="p-1.5 hover:bg-destructive/10 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            disabled={deletingDocId === doc.id}
                          >
                            <Trash2 className="w-4 h-4 text-muted-foreground hover:text-destructive" />
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

      {/* Pagination */}
      {totalDocs > 0 && (
        <div className="flex items-center justify-between pt-2">
          <div className="text-sm text-muted-foreground">
            Showing {page * pageSize + 1}–
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
  );
}
