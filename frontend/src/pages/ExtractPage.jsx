/**
 * Extract Page - Simplified Two-Panel Layout
 * Left: Source selection and upload
 * Right: Recent extractions list
 */
import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import {
  Upload,
  FileText,
  CheckCircle,
  Play,
  X,
  Clock,
  AlertCircle,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Progress } from "../components/ui/progress";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import { listCollections } from "../api";
import ExtractionDocumentSelectorModal from "../components/extractions/ExtractionDocumentSelectorModal";
import { Textarea } from "../components/ui/textarea";
import ExtractionResultSheet from "../components/extractions/ExtractionResultSheet";
import {
  useExtraction,
  useExtractionHistory,
  useExtractionActions,
} from "../store";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function ExtractPage() {
  const { getToken } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef(null);

  // Preselected doc id from query param
  const preselectedDocId = searchParams.get("doc");

  // Local UI state
  const [mode, setMode] = useState("upload"); // 'upload' | 'library'
  const [selectedFile, setSelectedFile] = useState(null);
  const [saveToLibrary, setSaveToLibrary] = useState(true);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [selectedDocMeta, setSelectedDocMeta] = useState(null);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [extractionContext, setExtractionContext] = useState("");
  const [sheetOpen, setSheetOpen] = useState(false);
  const [selectedExtractionId, setSelectedExtractionId] = useState(null);

  // Extraction slice
  const extraction = useExtraction();
  const extractionHistory = useExtractionHistory();

  // Add defensive checks
  const historyItems = extractionHistory?.items || [];
  const historyTotal = extractionHistory?.total || 0;
  const historyLoading = extractionHistory?.isLoading || false;
  const historyError = extractionHistory?.error || null;

  const {
    uploadDocument,
    extractTempDocument: extractTemp,
    extractLibraryDocument,
    cancelExtraction,
    resetExtraction,
    fetchExtractionHistory,
  } = useExtractionActions();

  // Load collections on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await listCollections(getToken);
        const cols = res?.collections || [];
        setCollections(cols);
        const defaultCol =
          cols.find((c) => c.name === "My Documents") || cols[0];
        if (defaultCol) setSelectedCollection(defaultCol.id);
      } catch (err) {
        console.error("Failed to fetch collections", err);
      }
    })();
  }, [getToken]);

  // When entering library mode, prompt selector immediately
  useEffect(() => {
    if (mode === "library") {
      setSelectorOpen(true);
    }
  }, [mode]);

  // Handle preselected doc
  useEffect(() => {
    if (preselectedDocId) {
      setMode("library");
      setSelectedDocId(preselectedDocId);
    }
  }, [preselectedDocId]);

  // Load extraction history on mount
  useEffect(() => {
    fetchExtractionHistory(getToken);
  }, [getToken, fetchExtractionHistory]);

  // Refresh history after extraction completes
  useEffect(() => {
    if (
      !extraction.isProcessing &&
      extraction.progress?.status === "completed"
    ) {
      fetchExtractionHistory(getToken);
    }
  }, [
    extraction.isProcessing,
    extraction.progress?.status,
    getToken,
    fetchExtractionHistory,
  ]);

  // const handleFileSelect = (e) => {
  //   const file = e.target.files?.[0];
  //   if (!file) return;
  //   if (file.type !== "application/pdf") {
  //     alert("Please select a PDF file");
  //     return;
  //   }
  //   if (file.size > 50 * 1024 * 1024) {
  //     alert("File size must be < 50MB");
  //     return;
  //   }
  //   setSelectedFile(file);
  // };

  const handleExtract = async () => {
    if (mode === "upload" && !selectedFile) {
      alert("Select a file");
      return;
    }
    if (mode === "library" && !selectedDocId) {
      alert("Select a document");
      return;
    }

    try {
      await extractLibraryDocument(selectedDocId, getToken, extractionContext);
    } catch (err) {
      console.error("Extraction start failed", err);
    }
  };

  const handleCancel = () => {
    cancelExtraction();
  };

  const resetForm = () => {
    setSelectedFile(null);
    setSelectedDocId(null);
    setExtractionContext("");
    resetExtraction();
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleSelectHistoryItem = async (id) => {
    setSelectedExtractionId(id);
    setSheetOpen(true);
  };

  const handleViewAllHistory = () => {
    navigate("/app/extractions");
  };

  const handleDeleteExtraction = (extractionId) => {
    console.log("🗑️ Extraction deleted:", extractionId);
    fetchExtractionHistory(getToken);
  };

  return (
    <AppLayout breadcrumbs={[{ label: "Extract" }]}>
      <div className="flex-1 flex gap-4">
        {/* LEFT PANEL - Source Selection */}
        <div className="w-[420px] flex-shrink-0 bg-card rounded-lg border border-border p-6 overflow-y-auto">
          <h2 className="text-lg font-semibold text-foreground mb-4">
            Extract Document
          </h2>

          {/* Mode Selection */}
          <div className="grid grid-cols-1 gap-3 mb-4">
            <button
              onClick={() => setMode("library")}
              className={`p-3 border rounded-lg text-sm transition-all ${
                mode === "library"
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-border"
              }`}
            >
              <FileText className="w-5 h-5 mb-1 mx-auto text-primary" />
              Library
            </button>
          </div>

          {/* Library Mode */}
          {mode === "library" && (
            <div className="space-y-3">
              <Button variant="outline" onClick={() => setSelectorOpen(true)}>
                Choose from Library
              </Button>
              {selectedDocId && (
                <div className="p-3 border rounded text-xs flex items-center gap-2">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                  <span className="truncate flex-1">
                    {selectedDocMeta?.filename || `Document ${selectedDocId}`}
                  </span>
                  {typeof selectedDocMeta?.page_count === "number" && (
                    <span className="text-[10px] text-muted-foreground">
                      {selectedDocMeta.page_count}p
                    </span>
                  )}
                  <CheckCircle className="w-4 h-4 text-primary" />
                </div>
              )}
            </div>
          )}

          {/* Context */}
          {((mode === "upload" && selectedFile) ||
            (mode === "library" && selectedDocId)) && (
            <div className="mt-5 space-y-2">
              <Label className="text-sm font-medium text-foreground">
                Extraction Context (optional)
              </Label>
              <Textarea
                value={extractionContext}
                onChange={(e) => setExtractionContext(e.target.value)}
                placeholder="Instructions, prompt, focus areas..."
                disabled={extraction.isProcessing}
                className="min-h-[90px] text-xs"
              />
              <p className="text-[10px] text-muted-foreground">
                Guides parsing, summarization & analysis.
              </p>
            </div>
          )}

          {/* Action Buttons */}
          <div className="mt-4 flex gap-2">
            <Button
              onClick={handleExtract}
              disabled={
                extraction.isProcessing ||
                !(
                  (mode === "upload" && selectedFile) ||
                  (mode === "library" && selectedDocId)
                ) ||
                (mode === "upload" && saveToLibrary && !selectedCollection)
              }
              className="flex-1"
            >
              <Play className="w-4 h-4 mr-2" />
              {extraction.isProcessing ? "Processing..." : "Extract"}
            </Button>
            {extraction.isProcessing && (
              <Button variant="outline" onClick={handleCancel}>
                <X className="w-4 h-4" />
              </Button>
            )}
            {(extraction.result || extraction.error) && (
              <Button variant="outline" onClick={resetForm}>
                Reset
              </Button>
            )}
          </div>

          {/* Progress Indicator */}
          {extraction.isProcessing && (
            <div className="mt-4 p-4 bg-primary/5 rounded-lg border border-primary/20">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">
                  {extraction.progress?.message || "Processing..."}
                </span>
                <span className="text-xs text-muted-foreground">
                  {extraction.progress?.percent || 0}%
                </span>
              </div>
              <Progress
                value={extraction.progress?.percent || 0}
                variant="primary"
                className="h-2"
                showShimmer={true}
              />
            </div>
          )}

          {/* Error Display */}
          {extraction.error && !extraction.isProcessing && (
            <div className="mt-4 p-4 bg-destructive/5 rounded-lg border border-destructive/20">
              <div className="flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-destructive mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-destructive-foreground">
                    Extraction Failed
                  </p>
                  <p className="text-xs text-destructive mt-1">
                    {extraction.error}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* RIGHT PANEL - Recent Extractions */}
        <div className="flex-1 bg-card rounded-lg border border-border p-6 overflow-y-auto">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-foreground">
              Recent Extractions
            </h3>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleViewAllHistory}
              disabled={historyLoading}
            >
              View All →
            </Button>
          </div>

          {historyLoading ? (
            <div className="flex items-center justify-center py-12">
              <Spinner size="lg" />
            </div>
          ) : historyItems.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-4 opacity-50" />
              <p className="text-sm text-muted-foreground mb-1">
                No extractions yet
              </p>
              <p className="text-xs text-muted-foreground">
                Upload a document to get started
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {historyItems.map((item) => (
                <ExtractionCard
                  key={item.id}
                  item={item}
                  onSelect={handleSelectHistoryItem}
                />
              ))}
            </div>
          )}

          {historyTotal > 10 && (
            <div className="mt-4 text-center">
              <p className="text-xs text-muted-foreground mb-2">
                Showing {historyItems.length} of {historyTotal} extractions
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleViewAllHistory}
              >
                View All History
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Selector Modal */}
      <ExtractionDocumentSelectorModal
        open={selectorOpen}
        onOpenChange={setSelectorOpen}
        onSelect={(doc) => {
          setSelectedDocId(doc.id);
          setSelectedDocMeta({
            filename: doc.filename,
            page_count: doc.page_count,
          });
        }}
      />

      {/* Extraction Result Sheet */}
      <ExtractionResultSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        extractionId={selectedExtractionId}
        onDelete={handleDeleteExtraction}
      />
    </AppLayout>
  );
}

// Extraction Card Component
function ExtractionCard({ item, onSelect }) {
  const getStatusBadge = () => {
    switch (item.status) {
      case "completed":
        return (
          <div className="flex items-center gap-1.5 px-2 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs font-medium">
            <CheckCircle className="w-3 h-3" />
            Completed
          </div>
        );
      case "processing":
        return (
          <div className="flex items-center gap-1.5 px-2 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">
            <Clock className="w-3 h-3 animate-spin" />
            Processing
          </div>
        );
      case "failed":
        return (
          <div className="flex items-center gap-1.5 px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded text-xs font-medium">
            <AlertCircle className="w-3 h-3" />
            Failed
          </div>
        );
      default:
        return (
          <div className="px-2 py-1 bg-muted text-muted-foreground rounded text-xs font-medium capitalize">
            {item.status}
          </div>
        );
    }
  };

  return (
    <Card
      className="p-4 hover:shadow-md transition-all cursor-pointer border-2 hover:border-primary/50"
      onClick={() => onSelect(item.id)}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <FileText className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p
              className="text-sm font-medium text-foreground truncate"
              title={item.filename}
            >
              {item.filename}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs text-muted-foreground">
                {item.page_count} pages
              </span>
            </div>
          </div>
        </div>
        {getStatusBadge()}
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {new Date(item.created_at).toLocaleDateString()} at{" "}
          {new Date(item.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
        {item.from_cache && (
          <span className="px-2 py-0.5 bg-muted rounded text-[10px]">
            Cached
          </span>
        )}
      </div>

      {item.error_message && (
        <p className="mt-2 text-xs text-red-600 dark:text-red-400 line-clamp-2">
          {item.error_message}
        </p>
      )}
    </Card>
  );
}
