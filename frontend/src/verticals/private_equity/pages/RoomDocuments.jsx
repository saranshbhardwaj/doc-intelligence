/**
 * RoomDocuments — Split-panel folder management + document table
 * Left: Folder sidebar navigation | Right: Documents in selected folder
 * Route: /app/pe/rooms/:roomId/documents
 */

import { useState, useEffect, useMemo, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  Upload, Play, AlertCircle, AlertTriangle, Link2, RefreshCw, Trash2,
  FileText, Clock, MoreHorizontal, Folder, FolderOpen, FolderPlus, Files, Search, ArrowUpDown, ChevronDown,
} from "lucide-react";
import { useAppAuth } from "@/hooks/useAppAuth";
import PELayout from "./PELayout";
import { Badge } from "../../../components/ui/badge";
import { Progress } from "../../../components/ui/progress";
import { Input } from "../../../components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "../../../components/ui/table";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "../../../components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../../../components/ui/dialog";
import {
  uploadRoomDocument,
  startAnalysis,
  removeRoomDocument,
  updateRoomDocumentFolder,
} from "../../../api/pe-diligence";
import { createAuthenticatedApi } from "../../../api/client";
import { streamJobProgress } from "@/api/sse-utils";
import { AnalysisTriggerButton } from "../components/AnalysisTriggerButton";
import { usePeDiligence, usePeDiligenceActions } from "../../../store";
import { DOC_TYPE_LABELS, DOC_TYPE_COLORS } from "../constants";

function getFileIcon(filename) {
  const ext = filename?.toLowerCase().split(".").pop();
  if (ext === "pdf") {
    return { bg: "bg-red-50 dark:bg-red-900/20", color: "text-red-500 dark:text-red-400" };
  }
  if (["docx", "doc"].includes(ext)) {
    return { bg: "bg-blue-50 dark:bg-blue-900/20", color: "text-blue-500 dark:text-blue-400" };
  }
  if (["pptx", "ppt"].includes(ext)) {
    return { bg: "bg-orange-50 dark:bg-orange-900/20", color: "text-orange-500 dark:text-orange-400" };
  }
  if (["jpg", "jpeg", "png", "bmp", "tif", "tiff", "heif", "heic"].includes(ext)) {
    return { bg: "bg-green-50 dark:bg-green-900/20", color: "text-green-600 dark:text-green-400" };
  }
  return { bg: "bg-gray-50 dark:bg-gray-800/40", color: "text-gray-500 dark:text-gray-400" };
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function StatusCell({ doc }) {
  if (doc.ingest_status === "processing" || doc.progress_percent != null) {
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
        <Progress value={doc.progress_percent || 0} variant="primary" className="h-1.5" showShimmer />
      </div>
    );
  }
  if (doc.ingest_status === "ready") {
    return (
      <Badge variant="success" className="text-xs font-medium rounded-full gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-current" />
        Ready
      </Badge>
    );
  }
  if (doc.ingest_status === "failed") {
    return (
      <Badge variant="destructive" className="text-xs font-medium rounded-full gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-current" />
        Failed
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="text-xs font-medium rounded-full gap-1.5">
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {doc.ingest_status || "linked"}
    </Badge>
  );
}

// ─── Folder Item ──────────────────────────────────────────────────────────────

function FolderItem({ label, count, active, onClick, icon, muted }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-sm transition-colors text-left ${
        active
          ? "bg-primary/10 text-primary font-medium"
          : muted
            ? "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
            : "text-foreground hover:bg-muted/50"
      }`}
    >
      <span className={`shrink-0 ${active ? "text-primary" : "text-muted-foreground"}`}>{icon}</span>
      <span className="flex-1 truncate">{label}</span>
      <span className="text-xs text-muted-foreground">{count}</span>
    </button>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function RoomDocuments() {
  const { roomId } = useParams();
  const { getToken } = useAppAuth();
  const fileInputRef = useRef(null);

  // Shared store — docs, loading, analysis job, analysis status
  const peDiligence = usePeDiligence();
  const actions = usePeDiligenceActions();
  const docs = peDiligence.documents;
  const loading = peDiligence.documentsLoading;
  const isRunning = peDiligence.analysisJobId != null;
  const analysisStatus = {
    ...peDiligence.analysisStatus,
    loading: peDiligence.analysisStatusLoading,
    refresh: () => actions.peRefreshAnalysisStatus(roomId, getToken),
  };

  // Local transient state for ingest-progress overrides and optimistic inserts
  const [docProgressOverrides, setDocProgressOverrides] = useState({});
  const [optimisticDocs, setOptimisticDocs] = useState([]);

  // Main state
  const [error, setError]                   = useState(null);
  const [uploadStatus, setUploadStatus]     = useState(null);
  const [uploadProgress, setUploadProgress] = useState({ done: 0, total: 0 });
  const [analyzeStatus, setAnalyzeStatus]   = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleting, setDeleting]             = useState(false);

  // Folder management
  const [selectedFolder, setSelectedFolder]         = useState(null);  // null = All
  const [newFolderInputVisible, setNewFolderInputVisible] = useState(false);
  const [newFolderName, setNewFolderName]         = useState("");
  const [localFolders, setLocalFolders]           = useState([]);  // transient empty folders
  const [movingDoc, setMovingDoc]                 = useState(null);  // {id, currentFolder}
  const [moveTarget, setMoveTarget]               = useState("");

  // Table controls
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Track active SSE cleanup functions keyed by document_id
  const sseCleanups = useRef({});

  // Effective docs = store docs with per-document ingest-progress overrides applied,
  // plus any optimistic rows for newly uploaded docs not yet in the store.
  const effectiveDocs = useMemo(() => {
    const storeIds = new Set(docs.map(d => d.document_id));
    const pending = optimisticDocs.filter(d => !storeIds.has(d.document_id));
    return [
      ...pending,
      ...docs.map(d => {
        const ov = docProgressOverrides[d.document_id];
        return ov ? { ...d, ...ov } : d;
      }),
    ];
  }, [docs, docProgressOverrides, optimisticDocs]);

  useEffect(() => {
    // Docs/room are loaded by PELayout on roomId change.
    // Only restore local folder state and ensure analysis status is populated.
    const stored = localStorage.getItem(`room_local_folders_${roomId}`);
    if (stored) {
      try {
        setLocalFolders(JSON.parse(stored));
      } catch {}
    }
    if (!peDiligence.analysisStatus) {
      actions.peRefreshAnalysisStatus(roomId, getToken);
    }
  }, [roomId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Persist local folders to localStorage
  useEffect(() => {
    localStorage.setItem(`room_local_folders_${roomId}`, JSON.stringify(localFolders));
  }, [localFolders, roomId]);

  // Cleanup all SSE connections on unmount
  useEffect(() => {
    return () => {
      Object.values(sseCleanups.current).forEach((fn) => { try { fn(); } catch {} });
    };
  }, []);

  // Folder derivation — all derived from effectiveDocs so optimistic rows count
  const docFolders = [...new Set(effectiveDocs.map((d) => d.folder).filter(Boolean))].sort();
  const allFolders = [...new Set([...docFolders, ...localFolders])].sort();
  const uncategorizedCount = effectiveDocs.filter((d) => !d.folder).length;

  const visibleDocs = selectedFolder === null
    ? effectiveDocs
    : selectedFolder === "__uncategorized__"
      ? effectiveDocs.filter((d) => !d.folder)
      : effectiveDocs.filter((d) => d.folder === selectedFolder);

  useEffect(() => {
    setPage(0);
  }, [searchQuery, sortBy, sortOrder, selectedFolder]);

  const filteredDocs = useMemo(() => {
    if (!searchQuery.trim()) return visibleDocs;
    const q = searchQuery.toLowerCase();
    return visibleDocs.filter((doc) => {
      const filename = doc.filename || "";
      const docType = doc.metadata?.document_classification?.document_type || "";
      return filename.toLowerCase().includes(q) || docType.toLowerCase().includes(q);
    });
  }, [visibleDocs, searchQuery]);

  const sortedDocs = useMemo(() => {
    const direction = sortOrder === "asc" ? 1 : -1;
    const getSortValue = (doc) => {
      switch (sortBy) {
        case "name":
          return (doc.filename || doc.document_id || "").toLowerCase();
        case "type":
          return (doc.metadata?.document_classification?.document_type || "").toLowerCase();
        case "status":
          return (doc.ingest_status || "").toLowerCase();
        case "created_at":
        default:
          return doc.created_at ? new Date(doc.created_at).getTime() : 0;
      }
    };
    return [...filteredDocs].sort((a, b) => {
      const av = getSortValue(a);
      const bv = getSortValue(b);
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * direction;
      }
      return String(av).localeCompare(String(bv)) * direction;
    });
  }, [filteredDocs, sortBy, sortOrder]);

  const totalFiltered = sortedDocs.length;
  const pageStart = page * pageSize;
  const pageEnd = Math.min(pageStart + pageSize, totalFiltered);
  const paginatedDocs = sortedDocs.slice(pageStart, pageEnd);

  async function getJobStatus(jobId) {
    const api = createAuthenticatedApi(getToken);
    const response = await api.get(`/api/jobs/${jobId}/status`);
    return response.data;
  }

  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortBy(field);
    setSortOrder(field === "created_at" ? "desc" : "asc");
  };

  function connectSSE(jobId, documentId) {
    if (!jobId || !documentId || sseCleanups.current[documentId]) {
      return;
    }
    streamJobProgress(jobId, getToken, {
      fetchInitialState: true,
      getJobStatus,
      onProgress: (data) => {
        setDocProgressOverrides(prev => ({
          ...prev,
          [documentId]: {
            ingest_status: "processing",
            status_detail: data.current_stage || data.message || "Processing",
            progress_percent: data.progress_percent || 0,
          },
        }));
      },
      onComplete: () => {
        setDocProgressOverrides(prev => { const n = { ...prev }; delete n[documentId]; return n; });
        setOptimisticDocs(prev => prev.filter(d => d.document_id !== documentId));
        delete sseCleanups.current[documentId];
        actions.peRefreshDocuments(roomId, getToken);
        actions.peRefreshAnalysisStatus(roomId, getToken);
      },
      onError: () => {
        setDocProgressOverrides(prev => ({ ...prev, [documentId]: { ingest_status: "failed" } }));
        delete sseCleanups.current[documentId];
      },
    }).then((cleanup) => {
      if (cleanup) sseCleanups.current[documentId] = cleanup;
    });
  }

  useEffect(() => {
    const processingDocs = effectiveDocs.filter(
      (doc) => doc.document_id && doc.job_id && doc.ingest_status === "processing"
    );

    processingDocs.forEach((doc) => {
      setDocProgressOverrides((prev) => {
        if (prev[doc.document_id]) return prev;
        return {
          ...prev,
          [doc.document_id]: {
            ingest_status: "processing",
            status_detail: doc.status_detail || "Processing",
            progress_percent: doc.progress_percent || 0,
          },
        };
      });
      connectSSE(doc.job_id, doc.document_id);
    });

    const activeIds = new Set(processingDocs.map((doc) => doc.document_id));
    Object.entries(sseCleanups.current).forEach(([documentId, cleanup]) => {
      if (!activeIds.has(documentId)) {
        try {
          cleanup();
        } catch {}
        delete sseCleanups.current[documentId];
      }
    });
  }, [effectiveDocs]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleUpload(e) {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setError(null);
    setUploadStatus("uploading");
    setUploadProgress({ done: 0, total: files.length });

    let completed = 0;
    const results = await Promise.allSettled(
      files.map(async (file) => {
        const fd = new FormData();
        fd.append("file", file);
        const folderToUse = (selectedFolder && selectedFolder !== "__uncategorized__") ? selectedFolder : null;
        if (folderToUse) {
          fd.append("folder", folderToUse);
        }
        const res = await uploadRoomDocument(getToken, roomId, fd);

        completed++;
        setUploadProgress({ done: completed, total: files.length });

        if (res.room_document_id) {
          // If already fully indexed, refresh immediately
          if (res.status === "completed") {
            actions.peRefreshDocuments(roomId, getToken);
            actions.peRefreshAnalysisStatus(roomId, getToken);
            return;
          }
          // If reused but still processing, connect SSE to track progress
          if (res.reuse && res.status === "processing" && res.job_id) {
            connectSSE(res.job_id, res.document_id);
            actions.peRefreshDocuments(roomId, getToken);
            return;
          }
          if (res.reuse) {
            actions.peRefreshDocuments(roomId, getToken);
            return;
          }

          // Document is processing — add optimistic row and track per-document progress
          setOptimisticDocs(prev => {
            const exists = prev.some(d => d.document_id === res.document_id);
            if (exists) return prev;
            return [
              {
                id: res.room_document_id,
                document_id: res.document_id,
                filename: res.filename,
                folder: folderToUse,
                ingest_status: "processing",
                status_detail: "Queued for indexing...",
                progress_percent: 0,
                created_at: new Date().toISOString(),
              },
              ...prev,
            ];
          });

          if (res.job_id) {
            connectSSE(res.job_id, res.document_id);
          }
        }
      })
    );

    fileInputRef.current.value = "";

    // Collect and log detailed failure information
    const failures = results
      .map((r, i) => r.status === "rejected" ? { file: files[i].name, error: r.reason } : null)
      .filter(Boolean);

    if (failures.length > 0) {
      console.error("Upload failures:", failures);

      // Build user-friendly error message
      let errorMsg = "";
      const fileTypeErrors = failures.filter(f => f.error.message?.includes("not supported"));
      const otherErrors = failures.filter(f => !f.error.message?.includes("not supported"));

      if (fileTypeErrors.length > 0) {
        const unsupportedFiles = fileTypeErrors.map(f => `"${f.file}"`).join(", ");
        errorMsg = `${unsupportedFiles}: Supported formats are PDF, Word (.docx), PowerPoint (.pptx), and images (.jpg, .jpeg, .png, .bmp, .tif, .tiff, .heif, .heic).`;
      }
      if (otherErrors.length > 0) {
        if (errorMsg) errorMsg += " ";
        const otherDetails = otherErrors.map(f => `${f.file}: ${f.error.message || "Upload failed"}`).join("; ");
        errorMsg += otherDetails;
      }

      setUploadStatus(`Upload failed: ${errorMsg}`);
    } else {
      setUploadStatus("done");
    }
  }

  async function handleAnalyze(incremental = false) {
    setError(null);
    setAnalyzeStatus(null);
    try {
      const result = await startAnalysis(getToken, roomId, !incremental, incremental);
      actions.peSetAnalysisJob(roomId, result.job_id);
    } catch (err) {
      setAnalyzeStatus(err.response?.data?.detail || "Failed to start analysis");
    }
  }

  async function handleDelete(roomDocId) {
    setDeleting(true);
    try {
      await removeRoomDocument(getToken, roomId, roomDocId);
      setConfirmDeleteId(null);
      actions.peRefreshDocuments(roomId, getToken);
      actions.peRefreshAnalysisStatus(roomId, getToken);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to remove document");
    } finally {
      setDeleting(false);
    }
  }

  async function handleFolderUpdate(roomDocId, newFolder) {
    try {
      await updateRoomDocumentFolder(getToken, roomId, roomDocId, newFolder);
      actions.peRefreshDocuments(roomId, getToken);
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to move document");
    }
  }

  // ─── Layout ──────────────────────────────────────────────────────────────

  return (
    <PELayout>
      <div className="flex flex-col h-full bg-background">
        {/* Page header */}
        <div className="px-6 py-4 border-b border-border flex items-center justify-between shrink-0 bg-card/60">
          <div>
            <h1 className="text-xl font-semibold font-display">Documents</h1>
            <p className="text-xs text-muted-foreground">{effectiveDocs.length} total</p>
          </div>
          <AnalysisTriggerButton
            roomId={roomId}
            isRunning={isRunning}
            onStart={handleAnalyze}
            status={analysisStatus}
            loading={analysisStatus?.loading}
          />
        </div>

        {/* Status messages */}
        {uploadStatus === "done" && (
          <div className="mx-6 mt-4 flex items-center gap-2 text-sm text-green-600 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-3">
            Files uploaded — indexing pipeline started.
          </div>
        )}
        {uploadStatus && uploadStatus !== "uploading" && uploadStatus !== "done" && (
          <div className="mx-6 mt-4 flex items-start gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1 break-words max-h-20 overflow-y-auto">
              {uploadStatus}
            </div>
          </div>
        )}
        {analyzeStatus && analyzeStatus !== "started" && !isRunning && (
          <div className="mx-6 mt-4 flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {analyzeStatus}
          </div>
        )}
        {error && (
          <div className="mx-6 mt-4 flex items-center gap-2 border border-destructive/30 bg-destructive/10 text-destructive rounded-lg p-3 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </div>
        )}

        {loading && <p className="px-6 py-4 text-sm text-muted-foreground">Loading documents…</p>}

        {!loading && (
          <div className="flex flex-1 overflow-hidden">
            {/* Left sidebar — folders */}
            <aside className="w-56 shrink-0 border-r border-border flex flex-col overflow-hidden bg-muted/20">
              {/* New Folder button */}
              <div className="p-3 border-b border-border shrink-0">
                {newFolderInputVisible ? (
                  <div className="flex items-center gap-1">
                    <input
                      autoFocus
                      type="text"
                      placeholder="Folder name"
                      value={newFolderName}
                      onChange={(e) => setNewFolderName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && newFolderName.trim()) {
                          setLocalFolders((prev) => [...prev, newFolderName.trim()]);
                          setSelectedFolder(newFolderName.trim());
                          setNewFolderName("");
                          setNewFolderInputVisible(false);
                        }
                        if (e.key === "Escape") {
                          setNewFolderInputVisible(false);
                          setNewFolderName("");
                        }
                      }}
                      className="flex-1 text-xs px-2 py-1 border rounded bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                    <button
                      onClick={() => setNewFolderInputVisible(false)}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setNewFolderInputVisible(true)}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors w-full"
                  >
                    <FolderPlus className="w-3.5 h-3.5" />
                    New Folder
                  </button>
                )}
              </div>

              {/* Folder list */}
              <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
                {/* All Documents */}
                <FolderItem
                  label="All Documents"
                  count={effectiveDocs.length}
                  active={selectedFolder === null}
                  onClick={() => setSelectedFolder(null)}
                  icon={<Files className="w-4 h-4" />}
                />

                {/* Named folders */}
                {allFolders.map((folder) => (
                  <FolderItem
                    key={folder}
                    label={folder}
                    count={effectiveDocs.filter((d) => d.folder === folder).length}
                    active={selectedFolder === folder}
                    onClick={() => setSelectedFolder(folder)}
                    icon={<Folder className="w-4 h-4" />}
                  />
                ))}

                {/* Uncategorized */}
                {uncategorizedCount > 0 && (
                  <FolderItem
                    label="Uncategorized"
                    count={uncategorizedCount}
                    active={selectedFolder === "__uncategorized__"}
                    onClick={() => setSelectedFolder("__uncategorized__")}
                    icon={<FolderOpen className="w-4 h-4" />}
                    muted
                  />
                )}
              </nav>
            </aside>

            {/* Right panel — document list */}
            <div className="flex-1 overflow-y-auto flex flex-col">
              {/* Panel header */}
              <div className="p-4 border-b border-border shrink-0 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold">
                    {selectedFolder === null
                      ? "All Documents"
                      : selectedFolder === "__uncategorized__"
                        ? "Uncategorized"
                        : selectedFolder}
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    {filteredDocs.length} document{filteredDocs.length !== 1 ? "s" : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative hidden lg:block">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                    <Input
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Search documents…"
                      className="h-8 pl-7 text-xs w-[220px]"
                    />
                  </div>
                  <button
                    onClick={() => { actions.peRefreshDocuments(roomId, getToken); actions.peRefreshAnalysisStatus(roomId, getToken); }}
                    className="p-1.5 rounded hover:bg-muted transition-colors"
                    title="Refresh"
                  >
                    <RefreshCw className="w-3.5 h-3.5 text-muted-foreground" />
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.pptx,.jpg,.jpeg,.png,.bmp,.tif,.tiff,.heif,.heic"
                    className="hidden"
                    onChange={handleUpload}
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadStatus === "uploading"}
                    className="pe-action-ghost text-xs px-3 py-1.5 disabled:opacity-50"
                    title="Supported formats: PDF, Word (.docx), PowerPoint (.pptx), and images (.jpg, .jpeg, .png, .bmp, .tif, .tiff, .heif, .heic)"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    {uploadStatus === "uploading"
                      ? `Uploading ${uploadProgress.done}/${uploadProgress.total}…`
                      : selectedFolder && selectedFolder !== "__uncategorized__"
                        ? `Upload to "${selectedFolder}"`
                        : "Upload"}
                  </button>
                </div>
              </div>

              {/* Document table or empty state */}
              {visibleDocs.length === 0 ? (
                <div className="flex-1 flex items-center justify-center p-6">
                  {effectiveDocs.length === 0 ? (
                    <div className="pe-card-muted flex flex-col items-center justify-center py-16 rounded-xl max-w-sm">
                      <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-4">
                        <Upload className="w-8 h-8 text-primary opacity-60" />
                      </div>
                      <p className="text-sm font-semibold">No documents yet</p>
                      <p className="text-xs text-muted-foreground mt-1 text-center">Create folders to organize your documents, then upload PDF, Word, PowerPoint, or image files.</p>
                      <button
                        onClick={() => setNewFolderInputVisible(true)}
                        className="mt-4 flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                      >
                        <FolderPlus className="w-3.5 h-3.5" />
                        Create First Folder
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">
                      {selectedFolder === null ? "No documents" : "No documents in this folder"}
                    </p>
                  )}
                </div>
              ) : (
                <div className="flex-1 overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50 border-b">
                        <TableHead
                          className="text-xs uppercase tracking-wide font-bold text-muted-foreground cursor-pointer"
                          onClick={() => toggleSort("name")}
                        >
                          <div className="flex items-center gap-1.5">
                            Document Name
                            {sortBy === "name" && <ArrowUpDown className="w-3 h-3" />}
                          </div>
                        </TableHead>
                        <TableHead
                          className="text-xs uppercase tracking-wide font-bold text-muted-foreground cursor-pointer"
                          onClick={() => toggleSort("type")}
                        >
                          <div className="flex items-center gap-1.5">
                            Type
                            {sortBy === "type" && <ArrowUpDown className="w-3 h-3" />}
                          </div>
                        </TableHead>
                        <TableHead
                          className="text-xs uppercase tracking-wide font-bold text-muted-foreground cursor-pointer"
                          onClick={() => toggleSort("status")}
                        >
                          <div className="flex items-center gap-1.5">
                            Status
                            {sortBy === "status" && <ArrowUpDown className="w-3 h-3" />}
                          </div>
                        </TableHead>
                        <TableHead className="text-xs uppercase tracking-wide font-bold text-muted-foreground w-16">
                          Pages
                        </TableHead>
                        <TableHead
                          className="text-xs uppercase tracking-wide font-bold text-muted-foreground cursor-pointer"
                          onClick={() => toggleSort("created_at")}
                        >
                          <div className="flex items-center gap-1.5">
                            Date Added
                            {sortBy === "created_at" && <ArrowUpDown className="w-3 h-3" />}
                          </div>
                        </TableHead>
                        <TableHead className="w-12" />
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedDocs.map((doc) => {
                        const { bg, color } = getFileIcon(doc.filename);
                        const classification = doc.metadata?.document_classification;
                        const docType = classification?.document_type;
                        const amendmentLink = doc.metadata?.amendment_link;
                        const amendmentParent = amendmentLink?.parent_document_id;
                        const parentDoc = amendmentParent
                          ? effectiveDocs.find((d) => d.document_id === amendmentParent)
                          : null;
                        const needsReview = classification?.needs_review;
                        const isConfirming = confirmDeleteId === doc.id;

                        return (
                          <TableRow
                            key={doc.id}
                            id={`doc-row-${doc.document_id}`}
                            className={`transition-all duration-200 group ${
                              isConfirming ? "bg-destructive/5" : "hover:bg-muted/30"
                            }`}
                          >
                            <TableCell>
                              <div className="flex items-center gap-3">
                                <div className={`w-9 h-9 rounded-lg ${bg} flex items-center justify-center shrink-0`}>
                                  <FileText className={`w-4 h-4 ${color}`} />
                                </div>
                                <div className="min-w-0">
                                  <div className="flex items-center gap-1.5">
                                    <span className="font-medium text-sm truncate max-w-xs">
                                      {doc.filename || doc.document_id || doc.id}
                                    </span>
                                    {needsReview && (
                                      <span title="Classification needs review" className="text-yellow-500 shrink-0">
                                        <AlertTriangle className="w-3.5 h-3.5" />
                                      </span>
                                    )}
                                  </div>
                                  {amendmentParent && (
                                    <button
                                      onClick={() => {
                                        const el = document.getElementById(`doc-row-${amendmentParent}`);
                                        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
                                      }}
                                      className="flex items-center gap-1 mt-0.5 text-xs text-blue-500 hover:text-blue-600 hover:underline transition-colors"
                                      title={`Amends: ${parentDoc?.filename || amendmentParent}`}
                                    >
                                      <Link2 className="w-3 h-3" />
                                      <span className="truncate max-w-[160px]">
                                        {parentDoc?.filename || "Parent document"}
                                      </span>
                                    </button>
                                  )}
                                </div>
                              </div>
                            </TableCell>

                            <TableCell>
                              {docType ? (
                                <span className={`text-xs px-2 py-0.5 rounded-full font-medium whitespace-nowrap ${DOC_TYPE_COLORS[docType] || DOC_TYPE_COLORS.other}`}>
                                  {DOC_TYPE_LABELS[docType] || docType}
                                </span>
                              ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                              )}
                            </TableCell>

                            <TableCell>
                              <StatusCell doc={doc} />
                            </TableCell>

                            {isConfirming ? (
                              <TableCell colSpan={4}>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs text-muted-foreground">Remove from room?</span>
                                  <button
                                    onClick={() => handleDelete(doc.id)}
                                    disabled={deleting}
                                    className="text-xs px-2 py-1 bg-destructive text-destructive-foreground rounded font-medium disabled:opacity-50 hover:brightness-105 transition-all"
                                  >
                                    {deleting ? "Removing…" : "Remove"}
                                  </button>
                                  <button
                                    onClick={() => setConfirmDeleteId(null)}
                                    className="text-xs px-2 py-1 border rounded hover:bg-muted transition-colors"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </TableCell>
                            ) : (
                              <>
                                <TableCell className="text-sm text-muted-foreground">
                                  {doc.page_count || "—"}
                                </TableCell>
                                <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                                  {formatDate(doc.created_at)}
                                </TableCell>
                                <TableCell onClick={(e) => e.stopPropagation()}>
                                  <DropdownMenu>
                                    <DropdownMenuTrigger asChild>
                                      <button className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 hover:bg-muted rounded-lg">
                                        <MoreHorizontal className="w-4 h-4 text-muted-foreground" />
                                      </button>
                                    </DropdownMenuTrigger>
                                    <DropdownMenuContent align="end" className="w-44">
                                      <DropdownMenuItem
                                        onSelect={() => setMovingDoc({ id: doc.id, currentFolder: doc.folder })}
                                      >
                                        <Folder className="w-3.5 h-3.5 mr-2" />
                                        Move to folder…
                                      </DropdownMenuItem>
                                      <DropdownMenuSeparator />
                                      <DropdownMenuItem
                                        onSelect={() => setConfirmDeleteId(doc.id)}
                                        className="text-destructive focus:text-destructive"
                                      >
                                        <Trash2 className="w-3.5 h-3.5 mr-2" />
                                        Remove from room
                                      </DropdownMenuItem>
                                    </DropdownMenuContent>
                                  </DropdownMenu>
                                </TableCell>
                              </>
                            )}
                          </TableRow>
                        );
                      })}
                      {paginatedDocs.length === 0 && (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">
                            No documents match your search.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                  {totalFiltered > 0 && (
                    <div className="flex items-center justify-between px-4 py-3 border-t border-border text-xs text-muted-foreground">
                      <span>
                        Showing {pageStart + 1}–{pageEnd} of {totalFiltered}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setPage((p) => Math.max(0, p - 1))}
                          disabled={page === 0}
                          className="px-2 py-1 border rounded hover:bg-muted disabled:opacity-50"
                        >
                          Previous
                        </button>
                        <button
                          onClick={() => setPage((p) => ((p + 1) * pageSize < totalFiltered ? p + 1 : p))}
                          disabled={(page + 1) * pageSize >= totalFiltered}
                          className="px-2 py-1 border rounded hover:bg-muted disabled:opacity-50"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Move to folder dialog */}
        <Dialog open={movingDoc !== null} onOpenChange={(open) => !open && setMovingDoc(null)}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>Move to Folder</DialogTitle>
            </DialogHeader>
            <div className="space-y-2 py-4">
              {/* Existing folders */}
              {allFolders.map((folder) => (
                <button
                  key={folder}
                  onClick={() => {
                    handleFolderUpdate(movingDoc.id, folder);
                    setMovingDoc(null);
                  }}
                  className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-sm hover:bg-muted transition-colors ${
                    movingDoc?.currentFolder === folder ? "border-primary bg-primary/5" : ""
                  }`}
                >
                  <Folder className="w-4 h-4 text-muted-foreground" />
                  <span className="flex-1">{folder}</span>
                  {movingDoc?.currentFolder === folder && (
                    <span className="text-xs text-primary font-medium">Current</span>
                  )}
                </button>
              ))}

              {/* Remove from folder */}
              {movingDoc?.currentFolder && (
                <>
                  <hr className="my-1" />
                  <button
                    onClick={() => {
                      handleFolderUpdate(movingDoc.id, null);
                      setMovingDoc(null);
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border text-sm hover:bg-muted text-muted-foreground transition-colors"
                  >
                    <FolderOpen className="w-4 h-4" />
                    Remove from folder
                  </button>
                </>
              )}

              {/* New folder inline */}
              <div className="flex items-center gap-2 pt-2 border-t">
                <input
                  type="text"
                  placeholder="New folder name…"
                  value={moveTarget}
                  onChange={(e) => setMoveTarget(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && moveTarget.trim()) {
                      setLocalFolders((prev) => [...new Set([...prev, moveTarget.trim()])]);
                      handleFolderUpdate(movingDoc.id, moveTarget.trim());
                      setMovingDoc(null);
                      setMoveTarget("");
                    }
                  }}
                  className="flex-1 text-xs px-2 py-1.5 border rounded bg-background focus:outline-none focus:ring-1 focus:ring-primary"
                />
                <button
                  onClick={() => {
                    if (!moveTarget.trim()) return;
                    setLocalFolders((prev) => [...new Set([...prev, moveTarget.trim()])]);
                    handleFolderUpdate(movingDoc.id, moveTarget.trim());
                    setMovingDoc(null);
                    setMoveTarget("");
                  }}
                  disabled={!moveTarget.trim()}
                  className="px-2 py-1.5 text-xs border rounded hover:bg-muted disabled:opacity-50 transition-colors"
                >
                  Move
                </button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </PELayout>
  );
}
