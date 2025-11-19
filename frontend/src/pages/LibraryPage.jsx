/**
 * Library Page - Central document management
 *
 * Features:
 * - View all collections
 * - Browse documents within collections
 * - Upload new documents
 * - Create/delete collections
 * - Move documents between collections
 * - Quick actions: Chat, Workflow, Extract
 * - Document status and embedding indicators
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import {
  Folder,
  FileText,
  Plus,
  Upload,
  Trash2,
  MessageSquare,
  Play,
  Zap,
  CheckCircle,
  AlertCircle,
  Clock,
  X,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../components/ui/alert-dialog";
import { Badge } from "../components/ui/badge";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import {
  listCollections,
  createCollection as apiCreateCollection,
  deleteCollection as apiDeleteCollection,
  getCollection as apiGetCollection,
  uploadDocumentToCollection as apiUploadDocumentToCollection,
  connectToIndexingProgress,
} from "../api";

export default function LibraryPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const fileInputRef = useRef(null);
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
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const [uploadCollection, setUploadCollection] = useState(null);

  // API fetch helpers (define before useEffect to avoid TDZ)
  const fetchCollections = useCallback(async () => {
    setLoadingCollections(true);
    try {
      const res = await listCollections(getToken);
      // API returns { collections: [...], total, limit, offset }
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
        // Persist to URL
        setSearchParams({ collection: defaultCol.id });
      }
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    } finally {
      setLoadingCollections(false);
    }
  }, [getToken, searchParams, setSearchParams]);

  const fetchDocuments = useCallback(
    async (collectionId) => {
      setLoadingDocs(true);
      try {
        const res = await apiGetCollection(getToken, collectionId);
        // getCollection returns a collection object with documents array
        setDocuments(res?.documents || []);
      } catch (error) {
        console.error("Failed to fetch documents:", error);
      } finally {
        setLoadingDocs(false);
      }
    },
    [getToken]
  );

  useEffect(() => {
    fetchCollections();
  }, [fetchCollections]);

  useEffect(() => {
    if (selectedCollection) {
      fetchDocuments(selectedCollection.id);
    }
  }, [selectedCollection, fetchDocuments]);

  const handleCreateCollection = async () => {
    if (!newCollectionName.trim()) {
      alert("Please enter a collection name");
      return;
    }

    try {
      const res = await apiCreateCollection(getToken, {
        name: newCollectionName,
      });
      setCollections((prev) => [...prev, res]);
      setNewCollectionName("");
      setShowNewCollection(false);
      setSelectedCollection(res);
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

  const handleFileSelect = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    if (!uploadCollection) {
      alert("Please select a collection");
      return;
    }

    for (const file of Array.from(files)) {
      if (file.type !== "application/pdf") {
        alert(`${file.name} is not a PDF file`);
        continue;
      }

      if (file.size > 50 * 1024 * 1024) {
        alert(`${file.name} is too large (max 50MB)`);
        continue;
      }

      try {
        // Capture collection ID for closure
        const targetCollectionId = uploadCollection;

        // Use centralized API helper which handles auth
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
              // You can add UI progress indicators here if needed
            },
            (completeData) => {
              console.log("Indexing complete:", completeData);
              // Always refresh the target collection's documents
              fetchDocuments(targetCollectionId);
            },
            (error) => {
              console.error("Indexing error:", error);
              alert(`Failed to index ${file.name}: ${error.message}`);
            }
          );
        } else {
          // No job_id means immediate processing (cached), refresh now
          await fetchDocuments(targetCollectionId);
        }
      } catch (error) {
        console.error(`Failed to upload ${file.name}:`, error);
        alert(`Failed to upload ${file.name}`);
      }
    }

    setShowUpload(false);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const toggleDocSelection = (docId) => {
    setSelectedDocs((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
  };

  const handleChat = () => {
    if (selectedDocs.length === 0) {
      alert("Please select at least one document");
      return;
    }

    // Navigate to chat with selected collection
    if (selectedCollection) {
      navigate(`/app/chat/${selectedCollection.id}`);
    }
  };

  const handleWorkflow = () => {
    if (selectedDocs.length === 0) {
      alert("Please select at least one document");
      return;
    }

    // Navigate to workflow with pre-selected documents
    navigate(`/app/workflows/new?docs=${selectedDocs.join(",")}`);
  };

  const handleExtract = () => {
    if (selectedDocs.length !== 1) {
      alert("Please select exactly one document for extraction");
      return;
    }

    navigate(`/app/extract?doc=${selectedDocs[0]}`);
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

      // Refresh documents list
      await fetchDocuments(selectedCollection.id);

      // Remove from selected docs if it was selected
      setSelectedDocs((prev) => prev.filter((id) => id !== docId));
    } catch (error) {
      console.error("Failed to delete document:", error);
      alert(`Failed to delete ${docFilename}: ${error.message}`);
    }
  };

  return (
    <AppLayout breadcrumbs={[{ label: "Library" }]}>
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-12 gap-6">
          {/* Collections Sidebar */}
          <div className="col-span-3">
            <Card className="p-4">
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-semibold text-foreground">Collections</h2>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowNewCollection(true)}
                >
                  <Plus className="w-4 h-4" />
                </Button>
              </div>

              {loadingCollections ? (
                <div className="flex justify-center py-8">
                  <Spinner />
                </div>
              ) : (
                <div className="space-y-1">
                  {collections.map((col) => (
                    <button
                      key={col.id}
                      onClick={() => {
                        setSelectedCollection(col);
                        setSelectedDocs([]);
                        setSearchParams({ collection: col.id });
                      }}
                      className={`w-full flex items-center gap-3 p-3 rounded-lg transition-all text-left ${
                        selectedCollection?.id === col.id
                          ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800"
                          : "hover:bg-background dark:hover:bg-card"
                      }`}
                    >
                      <Folder className="w-5 h-5 text-muted-foreground flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {col.name}
                        </p>
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                          {col.document_count || 0} docs
                        </p>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* New Collection Dialog */}
              {showNewCollection && (
                <div className="mt-4 p-3 border dark:border-gray-700 rounded-lg">
                  <Input
                    placeholder="Collection name"
                    value={newCollectionName}
                    onChange={(e) => setNewCollectionName(e.target.value)}
                    onKeyPress={(e) =>
                      e.key === "Enter" && handleCreateCollection()
                    }
                    className="mb-2"
                  />
                  <div className="flex gap-2">
                    <Button size="sm" onClick={handleCreateCollection}>
                      Create
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setShowNewCollection(false);
                        setNewCollectionName("");
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Documents View */}
          <div className="col-span-9">
            {selectedCollection ? (
              <>
                {/* Actions Bar */}
                <Card className="p-4 mb-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <h2 className="text-lg font-semibold text-foreground">
                        {selectedCollection.name}
                      </h2>
                      {selectedDocs.length > 0 && (
                        <Badge variant="secondary">
                          {selectedDocs.length} selected
                        </Badge>
                      )}
                    </div>

                    <div className="flex gap-2">
                      {selectedDocs.length > 0 && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleChat}
                          >
                            <MessageSquare className="w-4 h-4 mr-2" />
                            Chat
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={handleWorkflow}
                          >
                            <Play className="w-4 h-4 mr-2" />
                            Workflow
                          </Button>
                          {selectedDocs.length === 1 && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={handleExtract}
                            >
                              <Zap className="w-4 h-4 mr-2" />
                              Extract
                            </Button>
                          )}
                        </>
                      )}

                      <Button size="sm" onClick={() => setShowUpload(true)}>
                        <Upload className="w-4 h-4 mr-2" />
                        Upload
                      </Button>

                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button size="sm" variant="ghost">
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>
                              Delete Collection?
                            </AlertDialogTitle>
                            <AlertDialogDescription>
                              This will delete the collection "
                              {selectedCollection.name}" and all its documents.
                              This action cannot be undone.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() =>
                                handleDeleteCollection(selectedCollection.id)
                              }
                              className="bg-red-600 hover:bg-red-700"
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                </Card>

                {/* Documents Grid */}
                {loadingDocs ? (
                  <div className="flex justify-center py-12">
                    <Spinner />
                  </div>
                ) : documents.length === 0 ? (
                  <Card className="p-12 text-center">
                    <FileText className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                    <h3 className="text-lg font-medium text-foreground mb-2">
                      No documents yet
                    </h3>
                    <p className="text-sm text-muted-foreground dark:text-muted-foreground mb-4">
                      Upload documents to get started
                    </p>
                    <Button onClick={() => setShowUpload(true)}>
                      <Upload className="w-4 h-4 mr-2" />
                      Upload Document
                    </Button>
                  </Card>
                ) : (
                  <div className="grid grid-cols-1 gap-3">
                    {documents.map((doc) => (
                      <Card
                        key={doc.id}
                        className={`p-4 cursor-pointer transition-all ${
                          selectedDocs.includes(doc.id)
                            ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                            : "hover:shadow-md"
                        }`}
                        onClick={() => toggleDocSelection(doc.id)}
                      >
                        <div className="flex items-center gap-4">
                          <div className="flex-shrink-0">
                            <div className="w-12 h-12 rounded-lg bg-popover dark:bg-card flex items-center justify-center">
                              <FileText className="w-6 h-6 text-muted-foreground" />
                            </div>
                          </div>

                          <div className="flex-1 min-w-0">
                            <h3 className="font-medium text-foreground truncate">
                              {doc.filename}
                            </h3>
                            <div className="flex items-center gap-3 mt-1">
                              <span className="text-sm text-muted-foreground dark:text-muted-foreground">
                                {doc.page_count} pages
                              </span>
                              {doc.status === "completed" &&
                              doc.has_embeddings ? (
                                <Badge variant="success" className="text-xs">
                                  <CheckCircle className="w-3 h-3 mr-1" />
                                  Ready
                                </Badge>
                              ) : doc.status === "processing" ? (
                                <Badge variant="warning" className="text-xs">
                                  <Clock className="w-3 h-3 mr-1" />
                                  Processing
                                </Badge>
                              ) : doc.status === "failed" ? (
                                <Badge
                                  variant="destructive"
                                  className="text-xs"
                                >
                                  <AlertCircle className="w-3 h-3 mr-1" />
                                  Failed
                                </Badge>
                              ) : (
                                <Badge variant="secondary" className="text-xs">
                                  <AlertCircle className="w-3 h-3 mr-1" />
                                  No Embeddings
                                </Badge>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center gap-2">
                            {selectedDocs.includes(doc.id) && (
                              <CheckCircle className="w-5 h-5 text-blue-600 flex-shrink-0" />
                            )}

                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <button
                                  onClick={(e) => e.stopPropagation()}
                                  className="p-2 text-muted-foreground hover:text-red-600 dark:hover:text-red-400 transition-colors rounded-lg hover:bg-popover dark:hover:bg-gray-700"
                                  title="Delete document"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>
                                    Delete Document?
                                  </AlertDialogTitle>
                                  <AlertDialogDescription>
                                    This will remove{" "}
                                    <strong>{doc.filename}</strong> from this
                                    collection. This action cannot be undone.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                                  <AlertDialogAction
                                    onClick={() =>
                                      handleDeleteDocument(doc.id, doc.filename)
                                    }
                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                  >
                                    Delete
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                )}

                {/* Upload Modal */}
                {showUpload && (
                  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
                    <Card className="p-6 max-w-md w-full mx-4">
                      <div className="flex items-center justify-between mb-4">
                        <h3 className="text-lg font-semibold text-foreground">
                          Upload Documents
                        </h3>
                        <button
                          onClick={() => setShowUpload(false)}
                          className="text-muted-foreground hover:text-muted-foreground"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <Label className="mb-2 block">
                            Upload to Collection
                          </Label>
                          <Select
                            value={uploadCollection || ""}
                            onValueChange={setUploadCollection}
                          >
                            <SelectTrigger>
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

                        <div>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept=".pdf"
                            multiple
                            onChange={handleFileSelect}
                            className="hidden"
                          />
                          <Button
                            onClick={() => fileInputRef.current?.click()}
                            className="w-full"
                            disabled={!uploadCollection}
                          >
                            <Upload className="w-4 h-4 mr-2" />
                            Choose PDF Files
                          </Button>
                          <p className="text-xs text-muted-foreground dark:text-muted-foreground mt-2">
                            Documents will be parsed, chunked, and embedded
                            automatically
                          </p>
                        </div>
                      </div>
                    </Card>
                  </div>
                )}
              </>
            ) : (
              <Card className="p-12 text-center">
                <Folder className="w-12 h-12 mx-auto mb-4 text-muted-foreground" />
                <h3 className="text-lg font-medium text-foreground mb-2">
                  No Collection Selected
                </h3>
                <p className="text-sm text-muted-foreground dark:text-muted-foreground mb-4">
                  Select a collection from the sidebar or create a new one
                </p>
                <Button onClick={() => setShowNewCollection(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  New Collection
                </Button>
              </Card>
            )}
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
