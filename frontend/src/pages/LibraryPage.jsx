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

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { useAppAuth } from "@/hooks/useAppAuth";
import { toast } from "sonner";
import { Menu, Plus, Upload, UploadCloud } from "lucide-react";
import AppLayout from "../components/layout/AppLayout";
import StatsHeader from "../components/library/StatsHeader";
import CollectionsSidebar from "../components/library/CollectionsSidebar";
import DocumentsTable from "../components/library/DocumentsTable";
import UploadModal from "../components/library/UploadModal";
import { Button } from "../components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
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
  const { getToken, isLoaded, isSignedIn } = useAppAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  // Ref so fetchCollections can read the latest searchParams without being
  // in its useCallback deps (adding searchParams would cause it to re-create
  // every time the URL changes, triggering a second fetch mid-flight).
  const searchParamsRef = useRef(searchParams);
  useEffect(() => {
    searchParamsRef.current = searchParams;
  }, [searchParams]);

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
  const [mobileCollectionsOpen, setMobileCollectionsOpen] = useState(false);
  const [createRequestCount, setCreateRequestCount] = useState(0);

  // Overlay live progress from Zustand indexingJobs onto API-fetched documents.
  // Keeps progress accurate after SPA navigation: the SSE stream survives navigation
  // but the local `documents` state is re-fetched fresh from DB on every mount.
  const displayDocuments = useMemo(() => {
    if (Object.keys(indexingJobs).length === 0) return documents;
    return documents.map((doc) => {
      const job = indexingJobs[doc.id];
      if (!job || !job.isProcessing) return doc;
      return {
        ...doc,
        status: "processing",
        status_detail: job.current_stage || job.message || "Processing...",
        progress_percent: job.progress_percent || 0,
      };
    });
  }, [documents, indexingJobs]);

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
      const collectionIdFromUrl = searchParamsRef.current.get("collection");
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
  }, [getToken, setSearchParams]);

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

  // Re-fetch when a job is removed from the store (completed or cleared), so the
  // table shows the final DB status without requiring a manual refresh.
  // The length check exits early on every progress tick — only does work on removal.
  const prevIndexingJobKeysRef = useRef(Object.keys(indexingJobs));
  useEffect(() => {
    const currentKeys = Object.keys(indexingJobs);
    const prevKeys = prevIndexingJobKeysRef.current;
    prevIndexingJobKeysRef.current = currentKeys;

    if (currentKeys.length >= prevKeys.length) return; // no removals — skip

    const removed = prevKeys.filter((id) => !indexingJobs[id]);
    if (removed.length > 0 && selectedCollection) {
      fetchDocuments(selectedCollection.id);
      fetchCollections();
    }
  }, [indexingJobs, fetchDocuments, fetchCollections, selectedCollection]);

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
    setMobileCollectionsOpen(false);
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
      toast.error(error.response?.data?.detail || error.message || "Failed to create collection");
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
      toast.error(error.response?.data?.detail || "Failed to delete collection");
    }
  };

  const handleUploadFiles = async (files) => {
    if (!uploadCollection) {
      toast.warning("Please select a collection");
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

        const isImmediateComplete =
          response?.status === "completed" || response?.reuse === true;

        if (isImmediateComplete) {
          const existingName = response?.existing_filename || response?.filename || file.name;
          toast.info(
            `The file ${file.name} has the same content as ${existingName}.`
          );
          await fetchDocuments(targetCollectionId);
          await fetchCollections();
          return;
        }

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
            (_completeData) => {

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

              toast.error(`Failed to index ${file.name}`, { description: error.message });
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
        toast.error(`Failed to upload ${file.name}`);
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
      const deleteParams = new URLSearchParams();
      if (selectedCollection?.id) {
        deleteParams.set("collection_id", selectedCollection.id);
      }
      const deleteUrl = `${
        import.meta.env.VITE_API_URL || "http://localhost:8000"
      }/api/chat/documents/${docId}${deleteParams.toString() ? `?${deleteParams.toString()}` : ""}`;

      const response = await fetch(
        deleteUrl,
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

      const result = await response.json();

      if (result?.action === "unlinked") {
        toast.success(`Removed ${docFilename}`, {
          description: `Document removed from "${selectedCollection?.name || "this collection"}"`,
        });
      } else {
        toast.success(`Deleted ${docFilename}`, {
          description: "Document has been permanently removed",
        });
      }

      // Optimistically decrement document_count on the affected collection.
      // Avoids a stale-read race where fetchCollections() returns the old cached
      // count before the backend's recompute_collection_stats commit is visible.
      if (selectedCollection?.id) {
        setCollections((prev) =>
          prev.map((c) =>
            c.id === selectedCollection.id
              ? { ...c, document_count: Math.max(0, (c.document_count || 0) - 1) }
              : c
          )
        );
      }

      // Purge document references only for hard delete.
      if (result?.action === "deleted") {
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
    <AppLayout breadcrumbs={[{ label: "Library" }]} lockViewport>
      <div className="flex h-full min-h-0 flex-col px-3 pb-6 pt-4 sm:px-6">
        <StatsHeader
          totalDocuments={stats.totalDocuments}
          totalCollections={stats.totalCollections}
          processingCount={stats.processingCount}
          readyCount={stats.readyCount}
        />

        <div className="split-row">
          <div className="hidden w-72 flex-shrink-0 md:flex">
            <aside className="library-shell panel-shell w-full">
              <CollectionsSidebar
                collections={collections}
                selectedCollection={selectedCollection}
                loading={loadingCollections}
                onSelectCollection={handleSelectCollection}
                onCreateCollection={handleCreateCollection}
                onDeleteCollection={handleDeleteCollection}
                requestCreate={createRequestCount}
              />
            </aside>
          </div>

          <div className="min-w-0 flex-1">
            <div className="md:hidden mb-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setMobileCollectionsOpen(true)}
                className="w-full justify-start rounded-full"
              >
                <Menu className="w-4 h-4 mr-2" />
                {selectedCollection
                  ? `Collections: ${selectedCollection.name}`
                  : "Open Collections"}
              </Button>
            </div>

            {selectedCollection ? (
              <section className="library-shell-strong panel-shell h-full">
                <div className="border-b border-border/70 px-5 py-4 sm:px-6">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                    <div>
                      <h2 className="mt-2 page-title text-[1.7rem]">
                        {selectedCollection.name}
                      </h2>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                      <span className="rounded-full bg-muted px-3 py-1.5">
                        {stats.readyCount} ready
                      </span>
                      <span className="rounded-full bg-muted px-3 py-1.5">
                        {stats.processingCount} processing
                      </span>
                    </div>
                  </div>
                </div>

                <div className="panel-scroll px-4 py-4 sm:px-5 sm:py-5">
                  <DocumentsTable
                    documents={displayDocuments}
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
              </section>
            ) : (
              <div className="library-shell-strong flex h-full items-center justify-center px-6">
                <div className="text-center max-w-sm">
                  <div className="mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl bg-primary/10">
                    <UploadCloud className="w-10 h-10 text-primary" />
                  </div>
                  <h3 className="font-display text-xl font-bold text-foreground mb-2">
                    No Collection Selected
                  </h3>
                  <p className="text-sm text-muted-foreground mb-6">
                    Select a collection from the sidebar or start by creating your first workspace.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <Button
                      onClick={() => {
                        setCreateRequestCount((c) => c + 1);
                        setMobileCollectionsOpen(true);
                      }}
                      className="rounded-full gap-2"
                    >
                      <Plus className="w-4 h-4" />
                      Create Collection
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setShowUpload(true)}
                      className="rounded-full gap-2"
                    >
                      <Upload className="w-4 h-4" />
                      Upload Document
                    </Button>
                  </div>
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

      <Sheet open={mobileCollectionsOpen} onOpenChange={setMobileCollectionsOpen}>
        <SheetContent side="left" className="w-[90vw] max-w-sm p-0">
          <SheetTitle className="sr-only">Collections</SheetTitle>
          <SheetDescription className="sr-only">
            Select, create, or delete document collections.
          </SheetDescription>
          <CollectionsSidebar
            collections={collections}
            selectedCollection={selectedCollection}
            loading={loadingCollections}
            onSelectCollection={handleSelectCollection}
            onCreateCollection={handleCreateCollection}
            onDeleteCollection={handleDeleteCollection}
            requestCreate={createRequestCount}
          />
        </SheetContent>
      </Sheet>
    </AppLayout>
  );
}
