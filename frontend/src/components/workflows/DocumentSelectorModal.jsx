/**
 * Document Selector Modal
 *
 * Beautiful, professional modal for selecting documents and uploading new ones
 * Features: Tabs, Collapsible collections, Drag & drop, Live page counter
 */

import { useState, useEffect, useRef } from "react";
import { useAuth } from "@clerk/clerk-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Progress } from "../ui/progress";
import { Skeleton } from "../ui/skeleton";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import {
  FolderOpen,
  FolderClosed,
  FileText,
  Upload,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ChevronDown,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  listCollections,
  getCollection,
  uploadDocument,
  connectToIndexingProgress,
} from "../../api/chat";
import { useWorkflowDraft, useWorkflowDraftActions } from "../../store";

const MAX_PAGES = 700;

export default function DocumentSelectorModal({ open, onOpenChange }) {
  const { getToken } = useAuth();
  const fileInputRef = useRef(null);

  // Zustand store for workflow draft
  const { selectedDocuments } = useWorkflowDraft();
  const { addDocumentsToDraft, setSelectedDocuments } =
    useWorkflowDraftActions();

  // State
  const [collections, setCollections] = useState([]);
  const [documents, setDocuments] = useState([]); // All documents loaded from collections
  const [loading, setLoading] = useState(true);
  const [openCollections, setOpenCollections] = useState(new Set());
  const [loadedCollections, setLoadedCollections] = useState(new Set()); // Track which collections have loaded documents
  const [loadingCollections, setLoadingCollections] = useState(new Set()); // Track which collections are currently loading
  const [tempSelectedIds, setTempSelectedIds] = useState(new Set());
  const [uploadingFiles, setUploadingFiles] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(null);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (open) {
      fetchData();
      // Initialize temp selection from store
      setTempSelectedIds(new Set(selectedDocuments.map((d) => d.id)));
      // Reset state when modal opens
      setDocuments([]);
      setLoadedCollections(new Set());
      setLoadingCollections(new Set());
      setOpenCollections(new Set());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Only fetch collection metadata (no documents)
      const collectionsData = await listCollections(getToken);

      const cols = Array.isArray(collectionsData)
        ? collectionsData
        : collectionsData?.collections || [];

      setCollections(cols);

      // Auto-select "My Documents" for uploads
      const myDocs = cols.find((c) => c.name === "My Documents");
      if (myDocs) {
        setSelectedCollection(myDocs.id);
      } else {
        setSelectedCollection(cols[0]?.id || null);
      }
    } catch (error) {
      console.error("Failed to fetch data:", error);
      toast.error("Failed to load collections");
    } finally {
      setLoading(false);
    }
  };

  // Fetch documents for a specific collection (lazy load)
  const fetchCollectionDocuments = async (collectionId) => {
    if (loadedCollections.has(collectionId)) {
      return; // Already loaded
    }

    // Mark as loading
    setLoadingCollections((prev) => new Set(prev).add(collectionId));

    try {
      const fullCollection = await getCollection(getToken, collectionId);
      const collectionDocs = (fullCollection.documents || []).map((doc) => ({
        ...doc,
        collection_id: collectionId,
      }));

      // Add documents to the flat documents array
      setDocuments((prev) => [...prev, ...collectionDocs]);

      // Mark as loaded
      setLoadedCollections((prev) => new Set(prev).add(collectionId));
    } catch (error) {
      console.error(
        `Failed to fetch documents for collection ${collectionId}:`,
        error
      );
      toast.error("Failed to load collection documents");
    } finally {
      // Remove from loading
      setLoadingCollections((prev) => {
        const newSet = new Set(prev);
        newSet.delete(collectionId);
        return newSet;
      });
    }
  };

  // Toggle collection expand/collapse
  const toggleCollection = async (collectionId) => {
    const newOpen = new Set(openCollections);
    const isCurrentlyOpen = newOpen.has(collectionId);

    if (isCurrentlyOpen) {
      // Collapse
      newOpen.delete(collectionId);
      setOpenCollections(newOpen);
    } else {
      // Expand - fetch documents if not already loaded
      newOpen.add(collectionId);
      setOpenCollections(newOpen);

      if (!loadedCollections.has(collectionId)) {
        await fetchCollectionDocuments(collectionId);
      }
    }
  };

  // Toggle document selection
  const toggleDocument = (docId, docPages) => {
    const newSelected = new Set(tempSelectedIds);
    if (newSelected.has(docId)) {
      newSelected.delete(docId);
    } else {
      // Check page limit
      const currentPages = calculateTotalPages(newSelected);
      if (currentPages + docPages > MAX_PAGES) {
        toast.error(
          `Cannot add document: Would exceed ${MAX_PAGES} page limit`
        );
        return;
      }
      newSelected.add(docId);
    }
    setTempSelectedIds(newSelected);
  };

  // Calculate total pages from selected documents
  const calculateTotalPages = (selectedIds = tempSelectedIds) => {
    return documents
      .filter((doc) => selectedIds.has(doc.id))
      .reduce((sum, doc) => sum + (doc.page_count || 0), 0);
  };

  // Handle file upload
  const handleFileSelect = (files) => {
    if (!selectedCollection) {
      toast.error("Please select a collection first");
      return;
    }

    const fileArray = Array.from(files);
    const newUploads = fileArray.map((file) => ({
      file,
      id: `upload-${Date.now()}-${Math.random()}`,
      status: "uploading",
      progress: 0,
      docId: null,
    }));

    setUploadingFiles((prev) => [...prev, ...newUploads]);

    // Upload each file
    newUploads.forEach((upload) => uploadFile(upload));
  };

  const uploadFile = async (upload) => {
    try {
      // Use existing API abstraction for upload
      const res = await uploadDocument(
        getToken,
        selectedCollection,
        upload.file,
        (progressEvent) => {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id ? { ...u, progress: percent } : u
            )
          );
        }
      );

      const jobId = res.job_id;
      const docId = res.document_id;

      // Update status to processing
      setUploadingFiles((prev) =>
        prev.map((u) =>
          u.id === upload.id ? { ...u, status: "processing", docId } : u
        )
      );

      // Track processing via SSE using existing API function
      connectToIndexingProgress(
        getToken,
        jobId,
        // onProgress
        (progress) => {
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? { ...u, progress: progress.progress_percent || 0 }
                : u
            )
          );
        },
        // onComplete
        async () => {
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id ? { ...u, status: "completed" } : u
            )
          );

          // Refresh only the collection that was uploaded to
          if (loadedCollections.has(selectedCollection)) {
            // Mark as not loaded so it will be refetched
            setLoadedCollections((prev) => {
              const newSet = new Set(prev);
              newSet.delete(selectedCollection);
              return newSet;
            });
            // Refetch this collection's documents
            await fetchCollectionDocuments(selectedCollection);
          }

          // Auto-add to temp selection (full document will be added to store when modal closes)
          const newSelected = new Set(tempSelectedIds);
          newSelected.add(docId);
          setTempSelectedIds(newSelected);

          toast.success("Document ready!");
        },
        // onError
        (error) => {
          setUploadingFiles((prev) =>
            prev.map((u) =>
              u.id === upload.id
                ? {
                    ...u,
                    status: "failed",
                    error: error.message || "Processing failed",
                  }
                : u
            )
          );
          toast.error("Document processing failed");
        }
      );
    } catch (error) {
      console.error("Upload failed:", error);
      setUploadingFiles((prev) =>
        prev.map((u) =>
          u.id === upload.id
            ? { ...u, status: "failed", error: error.message }
            : u
        )
      );
      toast.error(`Failed to upload ${upload.file.name}`);
    }
  };

  // Drag and drop handlers
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    handleFileSelect(files);
  };

  // Group documents by collection
  const getDocumentsForCollection = (collectionId) => {
    return documents.filter((doc) => doc.collection_id === collectionId);
  };

  const totalPages = calculateTotalPages();
  const selectedCount = tempSelectedIds.size;

  const getPageLimitColor = () => {
    if (totalPages >= MAX_PAGES) return "text-red-600 dark:text-red-400";
    if (totalPages >= MAX_PAGES * 0.8)
      return "text-amber-600 dark:text-amber-400";
    return "text-green-600 dark:text-green-400";
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-2xl">
            Add Documents to Workflow
          </DialogTitle>
          <DialogDescription>
            Select existing documents or upload new ones. Max {MAX_PAGES} pages
            total.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="browse" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="browse" className="gap-2">
              <FolderOpen className="w-4 h-4" />
              Browse Collections
              {selectedCount > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {selectedCount}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="upload" className="gap-2">
              <Upload className="w-4 h-4" />
              Upload New
            </TabsTrigger>
          </TabsList>

          {/* Browse Collections Tab */}
          <TabsContent
            value="browse"
            className="flex-1 overflow-y-auto mt-4 space-y-2"
          >
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : collections.length === 0 ? (
              <div className="text-center py-12">
                <FolderClosed className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  No collections found
                </p>
              </div>
            ) : (
              collections.map((collection) => {
                const collectionDocs = getDocumentsForCollection(collection.id);
                const collectionPages = collectionDocs.reduce(
                  (sum, doc) => sum + (doc.page_count || 0),
                  0
                );
                const isOpen = openCollections.has(collection.id);

                return (
                  <Collapsible
                    key={collection.id}
                    open={isOpen}
                    onOpenChange={() => toggleCollection(collection.id)}
                  >
                    <CollapsibleTrigger className="w-full">
                      <div className="flex items-center gap-3 p-3 rounded-lg hover:bg-background dark:hover:bg-card transition-colors border border-border dark:border-gray-700">
                        {isOpen ? (
                          <ChevronDown className="w-4 h-4 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-muted-foreground" />
                        )}
                        {isOpen ? (
                          <FolderOpen className="w-5 h-5 text-blue-600" />
                        ) : (
                          <FolderClosed className="w-5 h-5 text-blue-600" />
                        )}
                        <div className="flex-1 text-left">
                          <p className="font-medium text-sm text-foreground">
                            {collection.name}
                          </p>
                          <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                            {collectionDocs.length} docs • {collectionPages}{" "}
                            pages
                          </p>
                        </div>
                      </div>
                    </CollapsibleTrigger>

                    <CollapsibleContent className="ml-7 mt-2 space-y-1">
                      {loadingCollections.has(collection.id) ? (
                        // Loading skeleton
                        <div className="space-y-2">
                          {[1, 2, 3].map((i) => (
                            <Skeleton key={i} className="h-16 w-full" />
                          ))}
                        </div>
                      ) : collectionDocs.length === 0 ? (
                        <p className="text-sm text-muted-foreground dark:text-muted-foreground py-2 px-3">
                          No documents in this collection
                        </p>
                      ) : (
                        collectionDocs.map((doc) => {
                          const isSelected = tempSelectedIds.has(doc.id);
                          const canSelect =
                            isSelected ||
                            totalPages + doc.page_count <= MAX_PAGES;

                          return (
                            <button
                              key={doc.id}
                              onClick={() =>
                                toggleDocument(doc.id, doc.page_count)
                              }
                              disabled={!canSelect && !isSelected}
                              className={`w-full text-left p-3 rounded-lg border transition-all ${
                                isSelected
                                  ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                                  : canSelect
                                  ? "border-border dark:border-gray-700 hover:border-blue-300"
                                  : "border-border dark:border-gray-700 opacity-50 cursor-not-allowed"
                              }`}
                            >
                              <div className="flex items-center gap-3">
                                <div
                                  className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                                    isSelected
                                      ? "border-blue-500 bg-primary"
                                      : "border-border dark:border-gray-600"
                                  }`}
                                >
                                  {isSelected && (
                                    <CheckCircle2 className="w-4 h-4 text-foreground" />
                                  )}
                                </div>
                                <FileText className="w-4 h-4 text-muted-foreground" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm font-medium text-foreground truncate">
                                    {doc.filename}
                                  </p>
                                  <div className="flex items-center gap-2 mt-0.5">
                                    <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                                      {doc.page_count} pages
                                    </p>
                                    {doc.status === "completed" && (
                                      <Badge
                                        variant="success"
                                        className="text-xs"
                                      >
                                        Ready
                                      </Badge>
                                    )}
                                    {doc.status === "processing" && (
                                      <Badge
                                        variant="secondary"
                                        className="text-xs"
                                      >
                                        Processing
                                      </Badge>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </button>
                          );
                        })
                      )}
                    </CollapsibleContent>
                  </Collapsible>
                );
              })
            )}
          </TabsContent>

          {/* Upload Tab */}
          <TabsContent value="upload" className="flex-1 overflow-y-auto mt-4">
            <div className="space-y-4">
              {/* Collection Selector */}
              <div>
                <label className="text-sm font-medium text-muted-foreground dark:text-gray-300 mb-2 block">
                  Upload to Collection
                </label>
                <select
                  value={selectedCollection || ""}
                  onChange={(e) => setSelectedCollection(e.target.value)}
                  className="w-full p-2 border border-border dark:border-gray-600 rounded-lg bg-card text-foreground"
                >
                  {collections.map((col) => (
                    <option key={col.id} value={col.id}>
                      {col.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Drag & Drop Zone */}
              <div
                onDragEnter={handleDragEnter}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${
                  isDragging
                    ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                    : "border-border dark:border-gray-600 hover:border-blue-400 hover:bg-background dark:hover:bg-card"
                }`}
              >
                <Upload
                  className={`w-12 h-12 mx-auto mb-4 ${
                    isDragging ? "text-blue-600" : "text-muted-foreground"
                  }`}
                />
                <p className="text-sm font-medium text-foreground mb-1">
                  {isDragging
                    ? "Drop files here"
                    : "Drop files here or click to browse"}
                </p>
                <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                  PDF documents only
                </p>
              </div>

              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf"
                className="hidden"
                onChange={(e) => handleFileSelect(e.target.files)}
              />

              {/* Upload Progress */}
              {uploadingFiles.length > 0 && (
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {uploadingFiles.map((upload) => (
                    <div
                      key={upload.id}
                      className="p-3 bg-background dark:bg-card rounded-lg border border-border dark:border-gray-700"
                    >
                      <div className="flex items-center gap-3 mb-2">
                        <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                        <p className="text-sm font-medium text-foreground flex-1 truncate">
                          {upload.file.name}
                        </p>
                        {upload.status === "completed" && (
                          <CheckCircle2 className="w-4 h-4 text-green-600" />
                        )}
                        {upload.status === "failed" && (
                          <AlertTriangle className="w-4 h-4 text-red-600" />
                        )}
                      </div>

                      {(upload.status === "uploading" ||
                        upload.status === "processing") && (
                        <div>
                          <Progress value={upload.progress} className="h-1.5" />
                          <p className="text-xs text-muted-foreground dark:text-muted-foreground mt-1">
                            {upload.status === "uploading"
                              ? `Uploading ${upload.progress}%`
                              : `Processing ${upload.progress}%`}
                          </p>
                        </div>
                      )}

                      {upload.status === "completed" && (
                        <p className="text-xs text-green-600 dark:text-green-400">
                          ✓ Ready
                        </p>
                      )}

                      {upload.status === "failed" && (
                        <p className="text-xs text-red-600 dark:text-red-400">
                          Failed: {upload.error}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>

        {/* Footer with Page Counter */}
        <DialogFooter className="flex-col sm:flex-row gap-3 pt-4 border-t border-border dark:border-gray-700">
          <div className="flex-1 text-sm">
            <p className={`font-medium ${getPageLimitColor()}`}>
              ✓ Selected: {selectedCount} docs • {totalPages} / {MAX_PAGES}{" "}
              pages
            </p>
            {totalPages >= MAX_PAGES * 0.8 && totalPages < MAX_PAGES && (
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                ⚠️ Approaching page limit
              </p>
            )}
            {totalPages >= MAX_PAGES && (
              <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                ❌ Page limit reached
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              onClick={() => {
                // Get full document objects for selected IDs
                const selectedDocs = documents.filter((doc) =>
                  tempSelectedIds.has(doc.id)
                );
                // Update store with selected documents
                setSelectedDocuments(selectedDocs);
                onOpenChange(false);
              }}
              disabled={selectedCount === 0}
              className="bg-blue-600 hover:bg-blue-700 text-foreground"
            >
              Add to Workflow ({selectedCount})
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
