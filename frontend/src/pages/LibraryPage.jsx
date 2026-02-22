/**
 * Library Page - Redesigned
 *
 * Professional document management with ChatGPT-inspired design
 *
 * Features:
 * - Stats header with key metrics
 * - Compact collections sidebar with search
 * - Table view for documents with filtering and sorting
 * - Beautiful upload modal with drag-and-drop
 * - Enhanced delete warnings
 * - Document usage tracking
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import { toast } from "sonner";
import AppLayout from "../components/layout/AppLayout";
import StatsHeader from "../components/library/StatsHeader";
import CollectionsSidebar from "../components/library/CollectionsSidebar";
import DocumentsTable from "../components/library/DocumentsTable";
import UploadModal from "../components/library/UploadModal";
import {
  listCollections,
  createCollection as apiCreateCollection,
  deleteCollection as apiDeleteCollection,
  getCollection as apiGetCollection,
  uploadDocumentToCollection as apiUploadDocumentToCollection,
  connectToIndexingProgress,
} from "../api";
import { useChat, useChatActions } from "../store";

export default function LibraryPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Zustand store for document indexing
  const { indexingJobs } = useChat();
  const {
    startDocumentIndexing,
    updateIndexingProgress,
    completeIndexing,
    failIndexing,
    reconnectAllIndexingJobs,
    clearIndexingJob,
  } = useChatActions();

  // Collections state
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [loadingCollections, setLoadingCollections] = useState(true);

  // Documents state
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [totalDocs, setTotalDocs] = useState(0);

  // Pagination and filters
  const [page, setPage] = useState(0);
  const [pageSize] = useState(50);
  const [sortBy, setSortBy] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState(null);

  // UI state
  const [showUpload, setShowUpload] = useState(false);
  const [uploadCollection, setUploadCollection] = useState(null);
  const [deletingDocId, setDeletingDocId] = useState(null);

  // Calculate stats from current page of documents
  const stats = useMemo(() => {
    return {
      totalDocuments: totalDocs, // Use total from server, not just current page
      totalCollections: collections.length,
      processingCount: documents.filter((d) => d.status === "processing").length,
      readyCount: documents.filter(
        (d) => d.status === "completed" && d.has_embeddings
      ).length,
    };
  }, [totalDocs, documents, collections]);

  // Fetch collections
  const fetchCollections = useCallback(async () => {
    setLoadingCollections(true);
    try {
      const res = await listCollections(getToken);
      const cols = res?.collections || [];
      setCollections(cols);

      // Try to restore collection from URL params first
      const collectionIdFromUrl = searchParams.get("collection");
      if (collectionIdFromUrl && cols.length > 0) {
        const restoredCol = cols.find((c) => c.id === collectionIdFromUrl);
        if (restoredCol) {
          setSelectedCollection(restoredCol);
          setUploadCollection(restoredCol.id);
          return;
        }
      }

      // Otherwise auto-select first collection or "My Documents"
      if (cols.length > 0) {
        const defaultCol =
          cols.find((c) => c.name === "My Documents") || cols[0];
        setSelectedCollection(defaultCol);
        setUploadCollection(defaultCol.id);
        setSearchParams({ collection: defaultCol.id });
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    } finally {
      setLoadingCollections(false);
    }
  }, [getToken, searchParams, setSearchParams]);

  // Fetch documents for a collection
  const fetchDocuments = useCallback(
    async (collectionId) => {
      setLoadingDocs(true);
      try {
        const res = await apiGetCollection(getToken, collectionId, {
          limit: pageSize,
          offset: page * pageSize,
          sort_by: sortBy,
          sort_order: sortOrder,
          search: searchQuery || null,
          status: statusFilter,
        });
        setDocuments(res?.documents || []);
        setTotalDocs(res?.total || 0);
      } catch (error) {
        console.error("Failed to fetch documents:", error);
        setDocuments([]);
        setTotalDocs(0);
      } finally {
        setLoadingDocs(false);
      }
    },
    [getToken, page, pageSize, sortBy, sortOrder, searchQuery, statusFilter]
  );

  // Initial load
  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  // Reset page when collection or filters change
  useEffect(() => {
    setPage(0);
  }, [selectedCollection, searchQuery, statusFilter, sortBy, sortOrder]);

  // Load documents when collection or page/filters change
  useEffect(() => {
    if (selectedCollection) {
      fetchDocuments(selectedCollection.id);
    }
  }, [selectedCollection, fetchDocuments]);

  // Reconnect to all active document indexing jobs on mount (for page refresh support)
  // Wait for Clerk auth to be ready before reconnecting
  useEffect(() => {
    if (!isLoaded || !isSignedIn) {
      return; // Wait for auth to be ready
    }

    if (indexingJobs && Object.keys(indexingJobs).length > 0) {
      reconnectAllIndexingJobs(getToken);
    }
  }, [isLoaded, isSignedIn]); // eslint-disable-line react-hooks/exhaustive-deps

  // Handlers
  const handleSelectCollection = (collection) => {
    setSelectedCollection(collection);
    setSearchParams({ collection: collection.id });
  };

  const handleCreateCollection = async (name) => {
    try {
      const res = await apiCreateCollection(getToken, { name });
      setCollections((prev) => [...prev, res]);
      setSelectedCollection(res);
      setUploadCollection(res.id);
      setSearchParams({ collection: res.id });
    } catch (error) {
      console.error("Failed to create collection:", error);
      alert(
        error.response?.data?.detail ||
          error.message ||
          "Failed to create collection"
      );
    }
  };

  const handleDeleteCollection = async (collectionId) => {
    try {
      await apiDeleteCollection(getToken, collectionId);

      const updated = collections.filter((c) => c.id !== collectionId);
      setCollections(updated);

      if (selectedCollection?.id === collectionId) {
        const newSelection = updated.length > 0 ? updated[0] : null;
        setSelectedCollection(newSelection);
        if (newSelection) {
          setSearchParams({ collection: newSelection.id });
        } else {
          setSearchParams({});
        }
      }
    } catch (error) {
      console.error("Failed to delete collection:", error);
      alert(error.response?.data?.detail || "Failed to delete collection");
    }
  };

  const handleUploadFiles = async (files) => {
    if (!uploadCollection) {
      alert("Please select a collection");
      return;
    }

    // Start all uploads in parallel
    const uploadPromises = files.map(async (file) => {
      try {
        const targetCollectionId = uploadCollection;

        const response = await apiUploadDocumentToCollection(
          getToken,
          targetCollectionId,
          file
        );

        // Connect to SSE for progress tracking
        if (response.job_id) {
          // Add document with processing status immediately
          const tempDoc = {
            id: response.document_id,
            filename: file.name,
            status: "processing",
            status_detail: "Uploading...",
            progress_percent: 0,
            page_count: 0,
            chunk_count: 0,
            has_embeddings: false,
            created_at: new Date().toISOString(),
          };
          setDocuments((prev) => [tempDoc, ...prev]);

          const cleanup = await connectToIndexingProgress(
            getToken,
            response.job_id,
            (progressData) => {

              // Update Zustand store for specific document
              updateIndexingProgress(response.document_id, progressData);

              // Update local documents state for UI
              setDocuments((prev) =>
                prev.map((doc) =>
                  doc.id === response.document_id
                    ? {
                        ...doc,
                        status: "processing",
                        status_detail:
                          progressData.current_stage ||
                          progressData.message ||
                          "Processing...",
                        progress_percent: progressData.progress_percent || 0,
                      }
                    : doc
                )
              );
            },
            (completeData) => {

              // Update store - mark specific document as complete
              completeIndexing(response.document_id);

              // Refresh documents
              fetchDocuments(targetCollectionId);
              fetchCollections();

              // Clear from store after short delay
              setTimeout(() => clearIndexingJob(response.document_id), 1000);
            },
            (error) => {
              console.error("Indexing error:", error);

              // Update store - mark specific document as failed
              failIndexing(response.document_id, error.message);

              // Update local UI
              setDocuments((prev) =>
                prev.map((doc) =>
                  doc.id === response.document_id
                    ? {
                        ...doc,
                        status: "failed",
                        status_detail: error.message,
                      }
                    : doc
                )
              );

              alert(`Failed to index ${file.name}: ${error.message}`);
            },
            {
              autoReconnect: true,
              fetchInitialState: false,
            }
          );

          // Store in Zustand for reconnection
          startDocumentIndexing(
            response.job_id,
            response.document_id,
            targetCollectionId,
            cleanup
          );
        } else {
          await fetchDocuments(targetCollectionId);
          await fetchCollections();
        }
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        alert(`Failed to upload ${file.name}`);
      }
    });

    // Wait for all uploads to initiate (not complete)
    await Promise.allSettled(uploadPromises);
  };

  const handleDeleteDocument = async (docId, docFilename) => {
    // Store original documents for potential rollback
    const originalDocuments = documents;

    try {
      // Set deleting state
      setDeletingDocId(docId);

      // Optimistic update: Remove document from UI immediately
      setDocuments((prev) => prev.filter((doc) => doc.id !== docId));

      // Make API call
      const token = await getToken();
      const response = await fetch(
        `${
          import.meta.env.VITE_API_URL || "http://localhost:8000"
        }/api/chat/documents/${docId}`,
        {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to delete document");
      }

      // Success toast
      toast.success(`Deleted ${docFilename}`, {
        description: "Document has been permanently removed",
      });

      // Refresh collections (for counts) - don't refresh documents, already updated optimistically
      await fetchCollections();

      // Purge document references from localStorage used by other pages
      try {
        // 1) ExtractPage quick access cache
        const lastDocRaw = localStorage.getItem("extractionLastDoc");
        if (lastDocRaw) {
          const lastDoc = JSON.parse(lastDocRaw);
          if (lastDoc?.id === docId) {
            localStorage.removeItem("extractionLastDoc");
          }
        }

        // 2) WorkflowSimplePage persisted draft (selectedDocuments array)
        const storeKey = "sand-cloud-storage"; // zustand persist key
        const persistedRaw = localStorage.getItem(storeKey);
        if (persistedRaw) {
          const persisted = JSON.parse(persistedRaw);
          const wf = persisted?.state?.workflowDraft;
          if (wf?.selectedDocuments && Array.isArray(wf.selectedDocuments)) {
            const filtered = wf.selectedDocuments.filter(
              (d) => d?.id !== docId
            );
            if (filtered.length !== wf.selectedDocuments.length) {
              const next = {
                ...persisted,
                state: {
                  ...persisted.state,
                  workflowDraft: {
                    ...wf,
                    selectedDocuments: filtered,
                  },
                },
              };
              localStorage.setItem(storeKey, JSON.stringify(next));
            }
          }
        }
      } catch (e) {
        console.warn("LocalStorage cleanup after delete failed:", e);
      }
    } catch (error) {
      console.error("Failed to delete document:", error);

      // Rollback optimistic update
      setDocuments(originalDocuments);

      // Error toast
      toast.error(`Failed to delete ${docFilename}`, {
        description: error.message || "Please try again",
      });
    } finally {
      // Clear deleting state
      setDeletingDocId(null);
    }
  };

  return (
    <AppLayout breadcrumbs={[{ label: "Library" }]}>
      <div className="h-full flex flex-col p-6">
        {/* Stats Header */}
        <StatsHeader
          totalDocuments={stats.totalDocuments}
          totalCollections={stats.totalCollections}
          processingCount={stats.processingCount}
          readyCount={stats.readyCount}
        />

        {/* Main Content */}
        <div className="flex-1 flex gap-6 min-h-0">
          {/* Collections Sidebar */}
          <div className="w-64 flex-shrink-0">
            <CollectionsSidebar
              collections={collections}
              selectedCollection={selectedCollection}
              loading={loadingCollections}
              onSelectCollection={handleSelectCollection}
              onCreateCollection={handleCreateCollection}
              onDeleteCollection={handleDeleteCollection}
            />
          </div>

          {/* Documents Area */}
          <div className="flex-1 min-w-0">
            {selectedCollection ? (
              <div className="h-full flex flex-col">
                {/* Collection Header */}
                <div className="mb-4">
                  <h1 className="text-2xl font-semibold text-foreground mb-1">
                    {selectedCollection.name}
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    Manage documents in this collection
                  </p>
                </div>

                {/* Documents Table */}
                <div className="flex-1 overflow-y-auto">
                  <DocumentsTable
                    documents={documents}
                    loading={loadingDocs}
                    getToken={getToken}
                    onDeleteDocument={handleDeleteDocument}
                    onUpload={() => setShowUpload(true)}
                    deletingDocId={deletingDocId}
                    page={page}
                    setPage={setPage}
                    totalDocs={totalDocs}
                    pageSize={pageSize}
                    sortBy={sortBy}
                    setSortBy={setSortBy}
                    sortOrder={sortOrder}
                    setSortOrder={setSortOrder}
                    searchQuery={searchQuery}
                    setSearchQuery={setSearchQuery}
                    statusFilter={statusFilter}
                    setStatusFilter={setStatusFilter}
                  />
                </div>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <h3 className="text-lg font-medium text-foreground mb-2">
                    No Collection Selected
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Select a collection from the sidebar or create a new one
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Upload Modal */}
      <UploadModal
        open={showUpload}
        collections={collections}
        selectedCollectionId={uploadCollection}
        onOpenChange={setShowUpload}
        onCollectionChange={setUploadCollection}
        onUpload={handleUploadFiles}
      />
    </AppLayout>
  );
}
