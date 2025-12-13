/**
 * DocumentsTable Component
 *
 * Table view for documents with search, filter, and sort
 * ChatGPT-inspired design with compact rows
 *
 * Input:
 *   - documents: Array<{id, filename, status, page_count, chunk_count, has_embeddings}>
 *   - loading: boolean
 *   - selectedDocs: string[]
 *   - getToken: () => Promise<string>
 *   - onToggleSelection: (docId) => void
 *   - onDeleteDocument: (docId, filename) => void
 *   - onUpload: () => void
 */

import { useState, useMemo } from "react";
import {
  FileText,
  Search,
  Filter,
  Upload,
  Trash2,
  CheckCircle,
  Clock,
  AlertCircle,
  XCircle,
  ArrowUpDown,
} from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";
import { Checkbox } from "../ui/checkbox";
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

export default function DocumentsTable({
  documents = [],
  loading = false,
  selectedDocs = [],
  getToken,
  onToggleSelection,
  onDeleteDocument,
  onUpload,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortBy, setSortBy] = useState("name");
  const [sortOrder, setSortOrder] = useState("asc");

  // Filter and sort documents
  const processedDocuments = useMemo(() => {
    let filtered = [...documents];

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((doc) =>
        doc.filename.toLowerCase().includes(query)
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter((doc) => doc.status === statusFilter);
    }

    // Sort
    filtered.sort((a, b) => {
      let comparison = 0;

      switch (sortBy) {
        case "name":
          comparison = a.filename.localeCompare(b.filename);
          break;
        case "pages":
          comparison = (a.page_count || 0) - (b.page_count || 0);
          break;
        case "status":
          comparison = a.status.localeCompare(b.status);
          break;
        case "chunks":
          comparison = (a.chunk_count || 0) - (b.chunk_count || 0);
          break;
        default:
          comparison = 0;
      }

      return sortOrder === "asc" ? comparison : -comparison;
    });

    return filtered;
  }, [documents, searchQuery, statusFilter, sortBy, sortOrder]);

  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("asc");
    }
  };

  const getStatusBadge = (doc) => {
    if (doc.status === "completed" && doc.has_embeddings) {
      return (
        <Badge variant="success" className="text-xs font-normal">
          <CheckCircle className="w-3 h-3 mr-1" />
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
        <Badge variant="destructive" className="text-xs font-normal">
          <XCircle className="w-3 h-3 mr-1" />
          Failed
        </Badge>
      );
    } else {
      return (
        <Badge variant="secondary" className="text-xs font-normal">
          <AlertCircle className="w-3 h-3 mr-1" />
          No Embeddings
        </Badge>
      );
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <Spinner />
      </div>
    );
  }

  // Empty state
  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 bg-muted/30 rounded-lg border-2 border-dashed border-border">
        <FileText className="w-16 h-16 text-muted-foreground mb-4 opacity-40" />
        <h3 className="text-lg font-medium text-foreground mb-2">
          No documents yet
        </h3>
        <p className="text-sm text-muted-foreground mb-6">
          Upload documents to get started
        </p>
        <Button onClick={onUpload}>
          <Upload className="w-4 h-4 mr-2" />
          Upload Document
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search documents..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-10"
          />
        </div>

        {/* Status Filter */}
        <Select value={statusFilter} onValueChange={setStatusFilter}>
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
            <SelectItem value="name">Name</SelectItem>
            <SelectItem value="pages">Pages</SelectItem>
            <SelectItem value="chunks">Chunks</SelectItem>
            <SelectItem value="status">Status</SelectItem>
          </SelectContent>
        </Select>

        {/* Upload Button */}
        <Button onClick={onUpload} className="h-10">
          <Upload className="w-4 h-4 mr-2" />
          Upload
        </Button>
      </div>

      {/* Filter info */}
      {(searchQuery || statusFilter !== "all") && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <span>
            Showing {processedDocuments.length} of {documents.length} documents
          </span>
          {(searchQuery || statusFilter !== "all") && (
            <button
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
              }}
              className="text-primary hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border border-border overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/50 hover:bg-muted/50">
              <TableHead className="w-12">
                <Checkbox disabled className="opacity-50" />
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors"
                onClick={() => toggleSort("name")}
              >
                <div className="flex items-center gap-2">
                  Name
                  {sortBy === "name" && <ArrowUpDown className="w-3.5 h-3.5" />}
                </div>
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors"
                onClick={() => toggleSort("status")}
              >
                <div className="flex items-center gap-2">
                  Status
                  {sortBy === "status" && (
                    <ArrowUpDown className="w-3.5 h-3.5" />
                  )}
                </div>
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors text-right"
                onClick={() => toggleSort("pages")}
              >
                <div className="flex items-center justify-end gap-2">
                  Pages
                  {sortBy === "pages" && (
                    <ArrowUpDown className="w-3.5 h-3.5" />
                  )}
                </div>
              </TableHead>
              <TableHead
                className="cursor-pointer hover:bg-muted/80 transition-colors text-right"
                onClick={() => toggleSort("chunks")}
              >
                <div className="flex items-center justify-end gap-2">
                  Chunks
                  {sortBy === "chunks" && (
                    <ArrowUpDown className="w-3.5 h-3.5" />
                  )}
                </div>
              </TableHead>
              <TableHead>Usage</TableHead>
              <TableHead className="w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {processedDocuments.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-8">
                  <p className="text-sm text-muted-foreground">
                    No documents match your filters
                  </p>
                </TableCell>
              </TableRow>
            ) : (
              processedDocuments.map((doc) => (
                <TableRow
                  key={doc.id}
                  className={`cursor-pointer transition-colors ${
                    selectedDocs.includes(doc.id)
                      ? "bg-primary/5 border-l-2 border-l-primary"
                      : "hover:bg-muted/30"
                  }`}
                  onClick={() => onToggleSelection?.(doc.id)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedDocs.includes(doc.id)}
                      onCheckedChange={() => onToggleSelection?.(doc.id)}
                    />
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                      <span className="font-medium text-sm truncate max-w-md">
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
                      trigger={
                        <button className="p-1.5 hover:bg-destructive/10 rounded transition-colors">
                          <Trash2 className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                        </button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Selection info */}
      {selectedDocs.length > 0 && (
        <div className="flex items-center justify-between p-3 bg-primary/5 border border-primary/30 rounded-lg">
          <span className="text-sm font-medium text-foreground">
            {selectedDocs.length} document{selectedDocs.length !== 1 ? "s" : ""}{" "}
            selected
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              selectedDocs.forEach((id) => onToggleSelection?.(id))
            }
          >
            Clear selection
          </Button>
        </div>
      )}
    </div>
  );
}
