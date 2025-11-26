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

export default function LibraryPage() {
  const { getToken } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Collections state
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [loadingCollections, setLoadingCollections] = useState(true);

  // Documents state
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [selectedDocs, setSelectedDocs] = useState([]);

  // UI state
  const [showUpload, setShowUpload] = useState(false);
  const [uploadCollection, setUploadCollection] = useState(null);

  // Calculate stats from documents
  const stats = useMemo(() => {
    const allDocs = documents;
    return {
      totalDocuments: allDocs.length,
      totalCollections: collections.length,
      processingCount: allDocs.filter((d) => d.status === "processing").length,
      readyCount: allDocs.filter(
        (d) => d.status === "completed" && d.has_embeddings
      ).length,
    };
  }, [documents, collections]);

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
        const res = await apiGetCollection(getToken, collectionId);
        setDocuments(res?.documents || []);
      } catch (error) {
        console.error("Failed to fetch documents:", error);
        setDocuments([]);
      } finally {
        setLoadingDocs(false);
      }
    },
    [getToken]
  );

  // Initial load
  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  // Load documents when collection changes
  useEffect(() => {
    if (selectedCollection) {
      fetchDocuments(selectedCollection.id);
      setSelectedDocs([]);
    }
  }, [selectedCollection, fetchDocuments]);

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

    for (const file of files) {
      try {
        const targetCollectionId = uploadCollection;

        const response = await apiUploadDocumentToCollection(
          getToken,
          targetCollectionId,
          file
        );

        // Connect to SSE for progress tracking
        if (response.job_id) {
          connectToIndexingProgress(
            getToken,
            response.job_id,
            (progressData) => {
              console.log("Indexing progress:", progressData);
            },
            (completeData) => {
              console.log("Indexing complete:", completeData);
              fetchDocuments(targetCollectionId);
              fetchCollections(); // Refresh collection counts
            },
            (error) => {
              console.error("Indexing error:", error);
              alert(`Failed to index ${file.name}: ${error.message}`);
            }
          );
        } else {
          await fetchDocuments(targetCollectionId);
          await fetchCollections();
        }
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        alert(`Failed to upload ${file.name}`);
      }
    }
  };

  const handleDeleteDocument = async (docId, docFilename) => {
    try {
      const token = await getToken();
      const response = await fetch(
        `${
          import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
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

      // Refresh documents and collections (for counts)
      await fetchDocuments(selectedCollection.id);
      await fetchCollections();

      // Remove from selected docs if it was selected
      setSelectedDocs((prev) => prev.filter((id) => id !== docId));
    } catch (error) {
      console.error("Failed to delete document:", error);
      alert(`Failed to delete ${docFilename}: ${error.message}`);
    }
  };

  const toggleDocSelection = (docId) => {
    setSelectedDocs((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
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
                    selectedDocs={selectedDocs}
                    getToken={getToken}
                    onToggleSelection={toggleDocSelection}
                    onDeleteDocument={handleDeleteDocument}
                    onUpload={() => setShowUpload(true)}
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
