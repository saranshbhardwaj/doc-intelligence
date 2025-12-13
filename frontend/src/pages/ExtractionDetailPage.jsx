/**
 * Extraction Detail Page
 * Shows a single extraction result with metadata & actions.
 */
import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import AppLayout from "../components/layout/AppLayout";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import Spinner from "../components/common/Spinner";
import ResultViews from "../components/results/ResultViews";
import { fetchExtractionResult, deleteExtraction } from "../api/extraction";
import { exportToExcel } from "../utils/excelExport";
import { useExtractionActions } from "../store";
import { saveAs } from "file-saver";
import {
  ArrowLeft,
  Download,
  Trash2,
  RotateCcw,
  CheckCircle,
  AlertCircle,
} from "lucide-react";

export default function ExtractionDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const { retryExtraction } = useExtractionActions();

  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [exporting, setExporting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchExtractionResult(id, getToken);
      setData(res);
    } catch (err) {
      console.error("Failed to fetch extraction", err);
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, [id, getToken]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExport = () => {
    if (!data) return;
    setExporting(true);
    try {
      const filename = data?.metadata?.filename || `${id}.json`;
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
    if (!window.confirm("Delete this extraction permanently?")) return;
    setDeleting(true);
    try {
      await deleteExtraction(id, getToken);
      navigate("/app/extractions");
    } catch (err) {
      console.error("Delete failed", err);
      alert(
        "Failed to delete extraction: " +
          (err.response?.data?.detail || err.message)
      );
      setDeleting(false);
    }
  };

  const handleRetry = async () => {
    setRetrying(true);
    try {
      const token = await getToken();
      await retryExtraction(id, token);
      navigate("/app/extract?retry=" + id);
    } catch (err) {
      console.error("Retry failed", err);
      alert("Retry failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setRetrying(false);
    }
  };

  const breadcrumbs = [
    { label: "Extractions", href: "/app/extractions" },
    { label: "Detail" },
  ];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="px-6 py-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
              <ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
          </div>
          <div className="flex gap-2">
            {data && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExport}
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
            {data && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleDelete}
                disabled={deleting}
                className="text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                <Trash2 className="w-4 h-4 mr-2" /> Delete
              </Button>
            )}
          </div>
        </div>

        {loading && (
          <Card className="p-10 flex items-center justify-center">
            <Spinner size="lg" />
          </Card>
        )}

        {!loading && error && (
          <Card className="p-6 border border-destructive/40">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-destructive mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-destructive mb-1">
                  Failed to load extraction
                </h3>
                <p className="text-xs text-muted-foreground">{error}</p>
              </div>
            </div>
          </Card>
        )}

        {!loading && data && (
          <div className="space-y-6">
            <ResultViews result={data} />
          </div>
        )}
      </div>
    </AppLayout>
  );
}

function MetaItem({ label, value }) {
  return (
    <div className="space-y-1">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="text-xs text-foreground break-all">{value ?? "-"}</p>
    </div>
  );
}
