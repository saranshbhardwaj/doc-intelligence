// src/components/dashboard/ExtractionHistory.jsx
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { deleteExtraction } from "../../api";
import { Trash2, Eye, Download, FileText } from "lucide-react";

export default function ExtractionHistory({
  extractions,
  pagination,
  onLoadMore,
  onDeleteSuccess,
  getToken
}) {
  const navigate = useNavigate();
  const [deletingId, setDeletingId] = useState(null);
  const [deleteError, setDeleteError] = useState(null);

  const handleDelete = async (extractionId, filename) => {
    setDeletingId(extractionId);
    setDeleteError(null);

    try {
      await deleteExtraction(getToken, extractionId);
      onDeleteSuccess();
    } catch (err) {
      console.error("Failed to delete extraction:", err);
      setDeleteError(err.response?.data?.detail || "Failed to delete extraction");
    } finally {
      setDeletingId(null);
    }
  };

  const handleView = (extractionId) => {
    navigate(`/app?extraction=${extractionId}`);
  };

  const getStatusBadge = (status) => {
    const variants = {
      completed: "success",
      processing: "warning",
      failed: "destructive",
    };

    return (
      <Badge variant={variants[status] || "outline"}>
        {status.charAt(0).toUpperCase() + status.slice(1)}
      </Badge>
    );
  };

  const formatDate = (dateString) => {
    if (!dateString) return "-";
    const date = new Date(dateString);
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  };

  const formatProcessingTime = (ms) => {
    if (!ms) return "-";
    const seconds = Math.floor(ms / 1000);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  if (!extractions || extractions.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Extraction History</CardTitle>
          <CardDescription>Your past document extractions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12">
            <FileText className="mx-auto h-12 w-12 text-muted-foreground mb-4" />
            <h3 className="text-lg font-semibold mb-2">No extractions yet</h3>
            <p className="text-muted-foreground mb-4">
              Start by uploading your first document
            </p>
            <Button onClick={() => navigate("/app")}>
              Upload Document
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Extraction History</CardTitle>
        <CardDescription>
          {pagination.total} extraction{pagination.total !== 1 ? "s" : ""} total
        </CardDescription>
      </CardHeader>
      <CardContent>
        {deleteError && (
          <div className="mb-4 p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive">
            {deleteError}
          </div>
        )}

        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>File</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Pages</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Date</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {extractions.map((extraction) => (
                <TableRow key={extraction.id}>
                  <TableCell className="font-medium max-w-xs truncate">
                    {extraction.filename}
                    {extraction.from_cache && (
                      <Badge variant="outline" className="ml-2 text-xs">
                        Cached
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {getStatusBadge(extraction.status)}
                  </TableCell>
                  <TableCell>
                    {extraction.page_count || "-"}
                  </TableCell>
                  <TableCell>
                    {extraction.pdf_type ? (
                      <Badge variant="outline" className="text-xs">
                        {extraction.pdf_type}
                      </Badge>
                    ) : (
                      "-"
                    )}
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-sm text-muted-foreground">
                    {extraction.context ? (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span>
                            {extraction.context.length > 40
                              ? extraction.context.slice(0, 40) + "…"
                              : extraction.context}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>
                          <span className="whitespace-pre-line">{extraction.context}</span>
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <span className="italic text-xs text-muted-foreground">No context</span>
                    )}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(extraction.created_at)}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-2">
                      {extraction.status === "completed" && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleView(extraction.id)}
                          title="View extraction"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      )}

                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={deletingId === extraction.id}
                            title="Delete extraction"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              Delete Extraction?
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              This will permanently delete the extraction for{" "}
                              <strong>{extraction.filename}</strong> and all associated
                              files. This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => handleDelete(extraction.id, extraction.filename)}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              {deletingId === extraction.id ? "Deleting..." : "Delete"}
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        {pagination.has_more && (
          <div className="flex justify-center mt-6">
            <Button variant="outline" onClick={onLoadMore}>
              Load More
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
