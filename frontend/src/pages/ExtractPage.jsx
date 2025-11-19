/**
 * Extract Page - Full document extraction and analysis
 *
 * Features:
 * - Upload new document OR select from library
 * - Optional "Save to Library" for new uploads
 * - Full extraction: parsing, chunking, summarization, analysis
 * - Real-time progress via SSE
 * - View and export results
 */

import { useState, useEffect, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import axios from "axios";
import {
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
  Download,
  Loader2,
  Play,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Checkbox } from "../components/ui/checkbox";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../components/ui/select";
import { Progress } from "../components/ui/progress";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import { listCollections } from "../api";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function ExtractPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const [searchParams] = useSearchParams();
  const fileInputRef = useRef(null);

  // Check for pre-selected document from URL (from Library quick action)
  const preselectedDocId = searchParams.get("doc");

  // Mode selection
  const [mode, setMode] = useState("upload"); // 'upload' | 'library'

  // Upload state
  const [selectedFile, setSelectedFile] = useState(null);
  const [saveToLibrary, setSaveToLibrary] = useState(true);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);

  // Library selection state
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [loadingDocs, setLoadingDocs] = useState(false);

  // Processing state
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStage, setCurrentStage] = useState("");
  const [jobId, setJobId] = useState(null);

  // Results state
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchCollections();
  }, []);

  useEffect(() => {
    if (mode === "library") {
      fetchDocuments();
    }
  }, [mode]);

  // Auto-select library mode and document if pre-selected from URL
  useEffect(() => {
    if (preselectedDocId) {
      setMode("library");
      setSelectedDocId(preselectedDocId);
    }
  }, [preselectedDocId]);

  const fetchCollections = async () => {
    try {
      const res = await listCollections(getToken);
      const cols = res?.collections || [];
      setCollections(cols);

      // Auto-select "My Documents" or first collection
      let defaultCol = cols.find((c) => c.name === "My Documents");
      if (!defaultCol && cols.length > 0) {
        defaultCol = cols[0];
      }

      if (defaultCol) {
        setSelectedCollection(defaultCol.id);
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    }
  };

  const fetchDocuments = async () => {
    setLoadingDocs(true);
    try {
      const token = await getToken();
      const res = await axios.get(`${API_BASE}/api/workflows/documents`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setDocuments(res.data);
    } catch (error) {
      console.error("Failed to fetch documents:", error);
      alert("Failed to load documents");
    } finally {
      setLoadingDocs(false);
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      if (file.type !== "application/pdf") {
        alert("Please select a PDF file");
        return;
      }
      if (file.size > 50 * 1024 * 1024) {
        // 50MB limit
        alert("File size must be less than 50MB");
        return;
      }
      setSelectedFile(file);
      setError(null);
    }
  };

  const handleExtract = async () => {
    if (mode === "upload" && !selectedFile) {
      alert("Please select a file");
      return;
    }

    if (mode === "library" && !selectedDocId) {
      alert("Please select a document");
      return;
    }

    if (mode === "upload" && saveToLibrary && !selectedCollection) {
      alert("Please select a collection");
      return;
    }

    setProcessing(true);
    setProgress(0);
    setCurrentStage("Initializing...");
    setError(null);
    setResult(null);

    try {
      const token = await getToken();

      if (mode === "upload") {
        // Upload new document
        const formData = new FormData();
        formData.append("file", selectedFile);

        if (saveToLibrary) {
          // Upload to collection with full pipeline (parse → chunk → embed)
          const uploadRes = await axios.post(
            `${API_BASE}/api/chat/collections/${selectedCollection}/documents`,
            formData,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "multipart/form-data",
              },
            }
          );

          const uploadJobId = uploadRes.data.job_id;
          const docId = uploadRes.data.document_id;

          // Track upload progress via SSE
          await trackJobProgress(uploadJobId, token);

          // Run extraction on uploaded document
          await runExtraction(docId, token);
        } else {
          // Temp upload - extraction only (no embeddings)
          const tempRes = await axios.post(
            `${API_BASE}/api/extract/temp`,
            formData,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "multipart/form-data",
              },
            }
          );

          const extractJobId = tempRes.data.job_id;
          setJobId(extractJobId);

          // Track extraction progress
          await trackJobProgress(extractJobId, token);
        }
      } else {
        // Extract from library document (already parsed/chunked)
        await runExtraction(selectedDocId, token);
      }
    } catch (error) {
      console.error("Extraction failed:", error);
      setError(
        error.response?.data?.detail || error.message || "Extraction failed"
      );
      setProcessing(false);
    }
  };

  const runExtraction = async (docId, token) => {
    setCurrentStage("Running extraction...");
    setProgress(50);

    try {
      const res = await axios.post(
        `${API_BASE}/api/extract/documents/${docId}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      );

      const extractJobId = res.data.job_id;
      setJobId(extractJobId);

      // Track extraction progress
      await trackJobProgress(extractJobId, token);
    } catch (error) {
      throw error;
    }
  };

  const trackJobProgress = (jobId, token) => {
    return new Promise((resolve, reject) => {
      const eventSource = new EventSource(
        `${API_BASE}/api/jobs/${jobId}/stream?token=${token}`
      );

      eventSource.addEventListener("progress", (e) => {
        const data = JSON.parse(e.data);
        setProgress(data.progress_percent || 0);
        setCurrentStage(data.message || "Processing...");
      });

      eventSource.addEventListener("complete", (e) => {
        const data = JSON.parse(e.data);
        setProgress(100);
        setCurrentStage("Complete");
        setResult(data.result || { status: "completed" });
        setProcessing(false);
        eventSource.close();
        resolve();
      });

      eventSource.addEventListener("error", (e) => {
        const data = e.data ? JSON.parse(e.data) : {};
        setError(data.error_message || "Processing failed");
        setProcessing(false);
        eventSource.close();
        reject(new Error(data.error_message || "Processing failed"));
      });

      eventSource.onerror = () => {
        setError("Connection lost");
        setProcessing(false);
        eventSource.close();
        reject(new Error("Connection lost"));
      };
    });
  };

  const resetForm = () => {
    setSelectedFile(null);
    setSelectedDocId(null);
    setResult(null);
    setError(null);
    setProgress(0);
    setCurrentStage("");
    setJobId(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <AppLayout breadcrumbs={[{ label: "Extract" }]}>
      <div className="max-w-6xl mx-auto px-6 py-8">
        {!result && !processing && (
          <>
            {/* Mode Selection */}
            <Card className="p-6 mb-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">
                Select Source
              </h2>
              <div className="grid grid-cols-2 gap-4">
                <button
                  onClick={() => setMode("upload")}
                  className={`p-4 border-2 rounded-lg transition-all ${
                    mode === "upload"
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-border"
                  }`}
                >
                  <Upload className="w-6 h-6 mb-2 mx-auto text-primary" />
                  <p className="font-medium text-foreground">
                    Upload New Document
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Extract from a new PDF file
                  </p>
                </button>

                <button
                  onClick={() => setMode("library")}
                  className={`p-4 border-2 rounded-lg transition-all ${
                    mode === "library"
                      ? "border-primary bg-primary/10"
                      : "border-border hover:border-border"
                  }`}
                >
                  <FileText className="w-6 h-6 mb-2 mx-auto text-primary" />
                  <p className="font-medium text-foreground">
                    Select from Library
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Extract from existing documents
                  </p>
                </button>
              </div>
            </Card>

            {/* Upload Mode */}
            {mode === "upload" && (
              <Card className="p-6 mb-6">
                <h2 className="text-lg font-semibold text-foreground mb-4">
                  Upload Document
                </h2>

                {/* File Input */}
                <div className="mb-4">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                  <Button
                    variant="outline"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="w-4 h-4 mr-2" />
                    Choose PDF File
                  </Button>
                  {selectedFile && (
                    <div className="mt-3 flex items-center gap-2 text-sm">
                      <FileText className="w-4 h-4 text-muted-foreground" />
                      <span className="text-foreground">
                        {selectedFile.name}
                      </span>
                      <span className="text-muted-foreground">
                        ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                      </span>
                    </div>
                  )}
                </div>

                {/* Save to Library Option */}
                <div className="border-t border-border pt-4">
                  <div className="flex items-start gap-3 mb-3">
                    <Checkbox
                      checked={saveToLibrary}
                      onCheckedChange={setSaveToLibrary}
                      id="save-to-library"
                    />
                    <div className="flex-1">
                      <Label
                        htmlFor="save-to-library"
                        className="text-sm font-medium text-foreground cursor-pointer"
                      >
                        Save to Library
                      </Label>
                      <p className="text-xs text-muted-foreground mt-1">
                        Store document for future use in Chat and Workflows
                        (creates embeddings)
                      </p>
                    </div>
                  </div>

                  {saveToLibrary && (
                    <div className="ml-6 mt-3">
                      <Label className="text-sm text-muted-foreground mb-2 block">
                        Collection
                      </Label>
                      <Select
                        value={selectedCollection || ""}
                        onValueChange={setSelectedCollection}
                      >
                        <SelectTrigger className="w-64">
                          <SelectValue placeholder="Select collection" />
                        </SelectTrigger>
                        <SelectContent>
                          {collections.map((col) => (
                            <SelectItem key={col.id} value={col.id}>
                              {col.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}
                </div>
              </Card>
            )}

            {/* Library Mode */}
            {mode === "library" && (
              <Card className="p-6 mb-6">
                <h2 className="text-lg font-semibold text-foreground mb-4">
                  Select Document
                </h2>

                {loadingDocs ? (
                  <div className="flex justify-center py-8">
                    <Spinner />
                  </div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FileText className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>No documents in your library</p>
                    <Button
                      variant="link"
                      onClick={() => setMode("upload")}
                      className="mt-2"
                    >
                      Upload a document
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {documents.map((doc) => (
                      <div
                        key={doc.id}
                        onClick={() => setSelectedDocId(doc.id)}
                        className={`p-4 border rounded-lg cursor-pointer transition-all ${
                          selectedDocId === doc.id
                            ? "border-primary bg-primary/10"
                            : "border-border hover:border-border"
                        }`}
                      >
                        <div className="flex items-center gap-3">
                          <FileText className="w-5 h-5 text-muted-foreground" />
                          <div className="flex-1">
                            <p className="font-medium text-foreground">
                              {doc.filename}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              {doc.page_count} pages
                            </p>
                          </div>
                          {selectedDocId === doc.id && (
                            <CheckCircle className="w-5 h-5 text-primary" />
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            )}

            {/* Extract Button */}
            {((mode === "upload" && selectedFile) ||
              (mode === "library" && selectedDocId)) && (
              <div className="flex justify-end">
                <Button
                  onClick={handleExtract}
                  size="lg"
                  disabled={
                    processing ||
                    (mode === "upload" && saveToLibrary && !selectedCollection)
                  }
                >
                  <Play className="w-4 h-4 mr-2" />
                  Run Extraction
                </Button>
              </div>
            )}
          </>
        )}

        {/* Processing State */}
        {processing && (
          <Card className="p-8">
            <div className="text-center">
              <Loader2 className="w-12 h-12 animate-spin mx-auto mb-4 text-primary" />
              <h3 className="text-lg font-semibold text-foreground mb-2">
                {currentStage}
              </h3>
              <Progress value={progress} className="w-full max-w-md mx-auto" />
              <p className="text-sm text-muted-foreground mt-2">
                {progress}% complete
              </p>
            </div>
          </Card>
        )}

        {/* Error State */}
        {error && !processing && (
          <Card className="p-6 border border-destructive/30">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-6 h-6 text-destructive flex-shrink-0 mt-1" />
              <div className="flex-1">
                <h3 className="font-semibold text-destructive mb-1">
                  Extraction Failed
                </h3>
                <p className="text-sm text-muted-foreground">{error}</p>
              </div>
            </div>
            <div className="mt-4">
              <Button variant="outline" onClick={resetForm}>
                Try Again
              </Button>
            </div>
          </Card>
        )}

        {/* Results */}
        {result && !processing && (
          <Card className="p-6 border border-success/30">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <CheckCircle className="w-6 h-6 text-success-foreground" />
                <h3 className="text-lg font-semibold text-success">
                  Extraction Complete
                </h3>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm">
                  <Download className="w-4 h-4 mr-2" />
                  Export
                </Button>
                <Button variant="outline" size="sm" onClick={resetForm}>
                  New Extraction
                </Button>
              </div>
            </div>

            <div className="border border-border rounded-lg p-4 max-h-96 overflow-y-auto">
              <pre className="text-sm text-foreground whitespace-pre-wrap">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
          </Card>
        )}
      </div>
    </AppLayout>
  );
}
