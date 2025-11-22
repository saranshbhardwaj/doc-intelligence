/**
 * Extraction Result Sheet
 *
 * Side sheet (opens from left) to display full extraction output
 * without leaving the ExtractPage.
 */
import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";
import {
  Download,
  Trash2,
  RotateCcw,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "../ui/sheet";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import Spinner from "../common/Spinner";
import ResultViews from "../results/ResultViews";
import { fetchExtractionResult, deleteExtraction } from "../../api/extraction";
import { exportToExcel } from "../../utils/excelExport";
import { saveAs } from "file-saver";
import { useExtraction, useExtractionActions } from "../../store";

export default function ExtractionResultSheet({
  open,
  onOpenChange,
  extractionId: propExtractionId,
  onDelete,
}) {
  const { getToken } = useAuth();
  const extraction = useExtraction();
  const { retryExtraction, resetExtraction } = useExtractionActions();

  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [exporting, setExporting] = useState(false);

  const effectiveExtractionId = propExtractionId || extraction.extractionId;

  const loadData = useCallback(async () => {
    if (!effectiveExtractionId || !open) return;

    // ✅ ALWAYS fetch fresh data when sheet opens
    setLoading(true);
    try {
      const res = await fetchExtractionResult(effectiveExtractionId, getToken);
      setData(res); // Store full response including metadata
    } catch (err) {
      console.error("Failed to load extraction result", err);
    } finally {
      setLoading(false);
    }
  }, [effectiveExtractionId, open, getToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExportJSON = () => {
    if (!data) return;
    setExporting(true);
    try {
      const filename =
        data?.metadata?.filename ||
        `${effectiveExtractionId || "extraction"}.json`;
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      saveAs(blob, filename);
    } finally {
      setExporting(false);
    }
  };

  const handleExportExcel = async () => {
    if (!data) return;
    setExporting(true);
    try {
      await exportToExcel(data.data || data, data.metadata);
    } catch (err) {
      console.error("Excel export failed", err);
      alert("Excel export failed: " + (err.message || "Unknown error"));
    } finally {
      setExporting(false);
    }
  };

  const handleDelete = async () => {
    if (!effectiveExtractionId) return;
    setDeleting(true);
    try {
      await deleteExtraction(effectiveExtractionId, getToken);

      // ✅ Refresh the history list in parent component
      // You'll need to pass a callback from ExtractPage
      onOpenChange(false); // Close sheet

      // Trigger history refresh in parent
      if (onDelete) {
        onDelete(effectiveExtractionId);
      }
    } catch (err) {
      console.error("Delete failed", err);
      alert(
        "Failed to delete extraction: " +
          (err.response?.data?.detail || err.message)
      );
    } finally {
      setDeleting(false);
    }
  };

  const handleRetry = async () => {
    if (!effectiveExtractionId) return;
    try {
      const token = await getToken();
      await retryExtraction(effectiveExtractionId, token);
    } catch (err) {
      console.error("Retry failed", err);
    }
  };

  const statusIcon = () => {
    if (extraction.isProcessing)
      return <Loader2 className="w-5 h-5 animate-spin text-primary" />;
    if (extraction.error)
      return <AlertCircle className="w-5 h-5 text-destructive" />;
    if (data)
      return <CheckCircle className="w-5 h-5 text-success-foreground" />;
    return <AlertCircle className="w-5 h-5 text-muted-foreground" />;
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="left"
        className="w-[900px] sm:max-w-[900px] overflow-y-auto bg-background"
      >
        <SheetHeader>
          <div className="flex items-center gap-3">
            {statusIcon()}
            <div className="flex-1">
              <SheetTitle className="text-xl font-bold text-foreground">
                Extraction Result
              </SheetTitle>
              {effectiveExtractionId && (
                <p className="text-xs text-muted-foreground mt-1">
                  ID: {effectiveExtractionId}
                </p>
              )}
            </div>
          </div>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            {data && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportJSON}
                  disabled={exporting}
                >
                  <Download className="w-4 h-4 mr-2" /> JSON
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportExcel}
                  disabled={exporting}
                >
                  <Download className="w-4 h-4 mr-2" /> Excel
                </Button>
              </>
            )}
            {extraction.error && effectiveExtractionId && (
              <Button variant="outline" size="sm" onClick={handleRetry}>
                <RotateCcw className="w-4 h-4 mr-2" /> Retry
              </Button>
            )}
            {effectiveExtractionId && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={deleting}
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                {deleting ? "Deleting..." : "Delete"}
              </Button>
            )}
          </div>

          {/* Progress / Error */}
          {extraction.isProcessing && (
            <Card className="p-4">
              <p className="text-sm font-medium text-foreground mb-2">
                {extraction.progress.message || "Processing..."}
              </p>
              <div className="w-full bg-muted h-2 rounded overflow-hidden">
                <div
                  className="bg-primary h-2 transition-all"
                  style={{ width: `${extraction.progress.percent}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {extraction.progress.percent}% complete
              </p>
            </Card>
          )}

          {extraction.error && !extraction.isProcessing && (
            <Card className="p-4 border border-destructive/40">
              <p className="text-sm font-semibold text-destructive mb-1">
                Extraction Failed
              </p>
              <p className="text-xs text-muted-foreground">
                {extraction.error}
              </p>
            </Card>
          )}

          {/* Result */}
          {loading && (
            <div className="flex items-center justify-center h-64">
              <Spinner size="lg" />
            </div>
          )}

          {!loading && data && <ResultViews result={data} />}

          {!loading &&
            !data &&
            !extraction.isProcessing &&
            !extraction.error && (
              <p className="text-sm text-muted-foreground">
                No result loaded yet.
              </p>
            )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
