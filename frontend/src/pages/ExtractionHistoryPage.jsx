/**
 * Extraction History Page
 * Lists past extractions with pagination and actions.
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import AppLayout from "../components/layout/AppLayout";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import Spinner from "../components/common/Spinner";
import { Badge } from "../components/ui/badge";
import {
  FileText,
  Download,
  Trash2,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { useUser, useUserActions } from "../store";
import { deleteExtraction, fetchExtractionResult } from "../api/extraction";
import { exportToExcel } from "../utils/excelExport";
import { saveAs } from "file-saver";

export default function ExtractionHistoryPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const user = useUser();
  const { fetchExtractions, loadMoreExtractions } = useUserActions();

  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [exportingId, setExportingId] = useState(null);

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

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this extraction permanently?")) return;
    setDeletingId(id);
    try {
      await deleteExtraction(id, getToken);
      // Refresh list
      await loadInitial();
    } catch (err) {
      console.error("Delete failed", err);
      alert(
        "Failed to delete extraction: " +
          (err.response?.data?.detail || err.message)
      );
    } finally {
      setDeletingId(null);
    }
  };

  const handleExport = async (id) => {
    setExportingId(id);
    try {
      const data = await fetchExtractionResult(id, getToken);
      const filename = data?.metadata?.filename || `${id}.json`;
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      saveAs(blob, filename);
    } catch (err) {
      console.error("Export failed", err);
      alert("Export failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setExportingId(null);
    }
  };

  const handleExportExcel = async (id) => {
    setExportingId(id);
    try {
      const data = await fetchExtractionResult(id, getToken);
      await exportToExcel(data.data || data, data.metadata);
    } catch (err) {
      console.error("Excel export failed", err);
      alert(
        "Excel export failed: " + (err.response?.data?.detail || err.message)
      );
    } finally {
      setExportingId(null);
    }
  };

  const columns = ["File", "Pages", "Started", "Status", "Actions"];
  const breadcrumbs = [{ label: "Extractions" }];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="px-6 py-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-semibold text-foreground">
            Extraction History
          </h1>
          <Button
            size="sm"
            variant="outline"
            onClick={loadInitial}
            disabled={loading}
          >
            <RefreshCw className="w-4 h-4 mr-2" /> Refresh
          </Button>
        </div>

        <Card className="p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 border-b border-border">
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col}
                      className="text-left px-4 py-2 font-medium text-muted-foreground"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && user.extractions.length === 0 && (
                  <tr>
                    <td colSpan={columns.length} className="p-8 text-center">
                      <Spinner />
                    </td>
                  </tr>
                )}
                {user.extractions.length === 0 && !loading && (
                  <tr>
                    <td
                      colSpan={columns.length}
                      className="p-8 text-center text-muted-foreground text-xs"
                    >
                      No extractions yet.
                    </td>
                  </tr>
                )}
                {user.extractions.map((ex) => (
                  <tr
                    key={ex.extraction_id}
                    className="border-b border-border hover:bg-muted/40 transition-colors"
                  >
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2 max-w-[280px]">
                        <FileText className="w-4 h-4 text-muted-foreground" />
                        <span className="truncate" title={ex.filename}>
                          {ex.filename || ex.extraction_id}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {ex.pages ?? ex.page_count ?? "-"}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {ex.started_at
                        ? new Date(ex.started_at).toLocaleString()
                        : "-"}
                    </td>
                    <td className="px-4 py-2">
                      <StatusBadge status={ex.status} />
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex gap-2 flex-wrap">
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() =>
                            navigate(`/app/extractions/${ex.extraction_id}`)
                          }
                        >
                          <ArrowRight className="w-3 h-3 mr-1" /> View
                        </Button>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => handleExport(ex.extraction_id)}
                          disabled={exportingId === ex.extraction_id}
                        >
                          <Download className="w-3 h-3 mr-1" /> JSON
                        </Button>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => handleExportExcel(ex.extraction_id)}
                          disabled={exportingId === ex.extraction_id}
                        >
                          <Download className="w-3 h-3 mr-1" /> Excel
                        </Button>
                        <Button
                          variant="outline"
                          size="xs"
                          onClick={() => handleDelete(ex.extraction_id)}
                          disabled={deletingId === ex.extraction_id}
                          className="text-red-600 hover:text-red-700 hover:bg-red-50"
                        >
                          <Trash2 className="w-3 h-3 mr-1" /> Del
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {user.pagination.has_more && (
            <div className="p-3 border-t border-border flex justify-center">
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={user.isLoadingExtractions}
              >
                Load More
              </Button>
            </div>
          )}
        </Card>
      </div>
    </AppLayout>
  );
}

function StatusBadge({ status }) {
  const normalized = status || "unknown";
  const styles = {
    completed: "bg-green-600 text-foreground",
    running: "bg-blue-600 text-foreground",
    failed: "bg-red-600 text-foreground",
    queued: "bg-yellow-600 text-foreground",
    unknown: "bg-muted text-muted-foreground",
  };
  return (
    <Badge
      className={`text-[10px] px-2 py-0.5 ${
        styles[normalized] || styles.unknown
      }`}
    >
      {normalized}
    </Badge>
  );
}
