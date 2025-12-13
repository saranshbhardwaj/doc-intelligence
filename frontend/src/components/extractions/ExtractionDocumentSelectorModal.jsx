/**
 * ExtractionDocumentSelectorModal
 *
 * Single-select document picker for ExtractPage, collection-first UX.
 * Reuses chat collections APIs; no upload here to keep flow focused.
 */

import { useState, useEffect } from "react";
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
import { Badge } from "../ui/badge";
import { Skeleton } from "../ui/skeleton";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../ui/collapsible";
import { Button } from "../ui/button";
import {
  FolderOpen,
  FolderClosed,
  FileText,
  ChevronRight,
  ChevronDown,
  CheckCircle2,
} from "lucide-react";
import { listCollections, getCollection } from "../../api/chat";

export default function ExtractionDocumentSelectorModal({
  open,
  onOpenChange,
  onSelect,
}) {
  const { getToken } = useAuth();
  const [collections, setCollections] = useState([]);
  const [documentsByCollection, setDocumentsByCollection] = useState({});
  const [loading, setLoading] = useState(true);
  const [openCollections, setOpenCollections] = useState(new Set());
  const [loadingCollections, setLoadingCollections] = useState(new Set());
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [quickDocs, setQuickDocs] = useState([]);

  useEffect(() => {
    if (open) {
      fetchCollections();
      setDocumentsByCollection({});
      setOpenCollections(new Set());
      setLoadingCollections(new Set());
      setSelectedDocId(null);
      setSearchQuery("");
      // Load quick access document from localStorage
      try {
        const lastDoc = localStorage.getItem("extractionLastDoc");
        if (lastDoc) {
          const parsed = JSON.parse(lastDoc);
          setQuickDocs([parsed]);
        } else {
          setQuickDocs([]);
        }
      } catch {
        setQuickDocs([]);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const fetchCollections = async () => {
    setLoading(true);
    try {
      const data = await listCollections(getToken);
      const cols = Array.isArray(data) ? data : data?.collections || [];
      setCollections(cols);
    } catch (e) {
      console.error("Failed to fetch collections:", e);
    } finally {
      setLoading(false);
    }
  };

  const fetchCollectionDocs = async (collectionId) => {
    if (documentsByCollection[collectionId]) return;

    setLoadingCollections((prev) => new Set(prev).add(collectionId));
    try {
      const col = await getCollection(getToken, collectionId);
      setDocumentsByCollection((prev) => ({
        ...prev,
        [collectionId]: col.documents || [],
      }));
    } catch (e) {
      console.error("Failed to fetch collection docs:", e);
    } finally {
      setLoadingCollections((prev) => {
        const ns = new Set(prev);
        ns.delete(collectionId);
        return ns;
      });
    }
  };

  const toggleCollection = async (collectionId) => {
    const next = new Set(openCollections);
    if (next.has(collectionId)) {
      next.delete(collectionId);
      setOpenCollections(next);
    } else {
      next.add(collectionId);
      setOpenCollections(next);
      await fetchCollectionDocs(collectionId);
    }
  };

  const handleConfirm = () => {
    if (!selectedDocId) return;
    const colId = [...Object.keys(documentsByCollection)].find((cid) =>
      (documentsByCollection[cid] || []).some((d) => d.id === selectedDocId)
    );
    const doc = (documentsByCollection[colId] || []).find(
      (d) => d.id === selectedDocId
    );
    if (doc) {
      // Cache last selection for quick access
      try {
        localStorage.setItem(
          "extractionLastDoc",
          JSON.stringify({
            id: doc.id,
            filename: doc.filename,
            page_count: doc.page_count,
            collection_id: colId,
          })
        );
      } catch {}
      onSelect?.(doc);
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-2xl">
            Select Document for Extraction
          </DialogTitle>
          <DialogDescription>
            Choose a document from your collections. Extraction supports a
            single document.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="browse" className="flex-1 flex flex-col min-h-0">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="browse" className="gap-2">
              <FolderOpen className="w-4 h-4" />
              Browse Collections
            </TabsTrigger>
            <TabsTrigger value="quick" className="gap-2">
              <FileText className="w-4 h-4" />
              Quick Access
              {quickDocs.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {quickDocs.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent
            value="browse"
            className="flex-1 overflow-y-auto mt-4 space-y-2"
          >
            {/* Search across loaded documents (non-blocking) */}
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search loaded documents..."
                className="w-full px-3 py-2 border border-input rounded-lg bg-background text-foreground placeholder:text-muted-foreground"
              />
            </div>
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <Skeleton key={i} className="h-16 w-full" />
                ))}
              </div>
            ) : collections.length === 0 ? (
              <div className="text-center py-12">
                <FolderClosed className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  No collections found
                </p>
              </div>
            ) : (
              collections.map((collection) => {
                const isOpen = openCollections.has(collection.id);
                const docsCount =
                  typeof collection.document_count === "number"
                    ? collection.document_count
                    : 0;
                const docs = documentsByCollection[collection.id] || [];

                return (
                  <Collapsible
                    key={collection.id}
                    open={isOpen}
                    onOpenChange={() => toggleCollection(collection.id)}
                  >
                    <CollapsibleTrigger className="w-full">
                      <div className="flex items-center gap-3 p-3 rounded-lg hover:bg-background transition-colors border border-border">
                        {isOpen ? (
                          <ChevronDown className="w-4 h-4 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-muted-foreground" />
                        )}
                        {isOpen ? (
                          <FolderOpen className="w-5 h-5 text-primary" />
                        ) : (
                          <FolderClosed className="w-5 h-5 text-primary" />
                        )}
                        <div className="flex-1 text-left">
                          <p className="font-medium text-sm text-foreground">
                            {collection.name}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {docsCount} docs
                          </p>
                        </div>
                      </div>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="ml-7 mt-2 space-y-1">
                      {loadingCollections.has(collection.id) ? (
                        <div className="space-y-2">
                          {[1, 2, 3].map((i) => (
                            <Skeleton key={i} className="h-14 w-full" />
                          ))}
                        </div>
                      ) : docs.length === 0 ? (
                        <p className="text-sm text-muted-foreground py-2 px-3">
                          No documents in this collection
                        </p>
                      ) : (
                        docs
                          .filter((doc) => {
                            if (!searchQuery.trim()) return true;
                            const q = searchQuery.toLowerCase();
                            return (doc.filename || "")
                              .toLowerCase()
                              .includes(q);
                          })
                          .map((doc) => {
                            const isSelected = selectedDocId === doc.id;
                            return (
                              <button
                                key={doc.id}
                                onClick={() => setSelectedDocId(doc.id)}
                                className={`w-full text-left p-3 rounded-lg border transition-all ${
                                  isSelected
                                    ? "border-primary bg-primary/5"
                                    : "border-border hover:border-primary/40"
                                }`}
                              >
                                <div className="flex items-center gap-3">
                                  <div
                                    className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                                      isSelected
                                        ? "border-primary bg-primary"
                                        : "border-border"
                                    }`}
                                  >
                                    {isSelected && (
                                      <CheckCircle2 className="w-4 h-4 text-primary-foreground" />
                                    )}
                                  </div>
                                  <FileText className="w-4 h-4 text-muted-foreground" />
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-medium text-foreground truncate">
                                      {doc.filename}
                                    </p>
                                    {typeof doc.page_count === "number" && (
                                      <p className="text-xs text-muted-foreground">
                                        {doc.page_count} pages
                                      </p>
                                    )}
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

          {/* Quick Access */}
          <TabsContent value="quick" className="flex-1 overflow-y-auto mt-4">
            {quickDocs.length === 0 ? (
              <div className="text-center py-12">
                <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground">
                  No quick access documents yet
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Select a document once to save it here
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {quickDocs.map((doc) => (
                  <button
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    className={`w-full text-left p-3 rounded-lg border transition-all ${
                      selectedDocId === doc.id
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${
                          selectedDocId === doc.id
                            ? "border-primary bg-primary"
                            : "border-border"
                        }`}
                      >
                        {selectedDocId === doc.id && (
                          <CheckCircle2 className="w-4 h-4 text-primary-foreground" />
                        )}
                      </div>
                      <FileText className="w-4 h-4 text-muted-foreground" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">
                          {doc.filename}
                        </p>
                        {typeof doc.page_count === "number" && (
                          <p className="text-xs text-muted-foreground">
                            {doc.page_count} pages
                          </p>
                        )}
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter className="flex-col sm:flex-row gap-3 pt-4 border-t border-border">
          <div className="flex-1 text-xs text-muted-foreground">
            {selectedDocId ? (
              <span className="font-medium">One document selected</span>
            ) : (
              <span>Select exactly one document</span>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button disabled={!selectedDocId} onClick={handleConfirm}>
              Use Document
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
