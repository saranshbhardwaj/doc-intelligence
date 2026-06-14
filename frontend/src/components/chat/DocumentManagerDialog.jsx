/**
 * DocumentManagerDialog
 *
 * Shared modal for adding documents to a chat session.
 * Filters out already-in-session docs and only allows completed documents.
 */

import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Clock, FileText, Search, X, XCircle } from "lucide-react";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Input } from "../ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../ui/tabs";
import { Combobox } from "../ui/combobox";
import Spinner from "../common/Spinner";
import { getCollection } from "../../api/chat";

const getStatusBadge = (status) => {
  if (status === "completed") return { Icon: CheckCircle, className: "text-success" };
  if (status === "processing") return { Icon: Clock, className: "text-warning" };
  return { Icon: XCircle, className: "text-destructive" };
};

const getPageLabel = (doc) => {
  const rawPageCount = doc.page_count ?? doc.pages ?? doc.num_pages ?? doc.metadata?.pages;
  const pageCount = Number(rawPageCount);
  return Number.isFinite(pageCount) && pageCount > 0
    ? `${pageCount} pages`
    : "Pages n/a";
};

export default function DocumentManagerDialog({
  open,
  onOpenChange,
  collections = [],
  currentSessionDocuments = [],
  getToken,
  onAddDocuments,
  onRemoveDocument,
}) {
  const [selectedCollectionId, setSelectedCollectionId] = useState(null);
  const [collectionDocuments, setCollectionDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [removingDocumentId, setRemovingDocumentId] = useState(null);
  const [docsToAdd, setDocsToAdd] = useState([]);
  const [manageSearchQuery, setManageSearchQuery] = useState("");
  const [addSearchQuery, setAddSearchQuery] = useState("");

  const sessionDocIds = useMemo(
    () => new Set((currentSessionDocuments || []).map((doc) => doc.id)),
    [currentSessionDocuments]
  );

  useEffect(() => {
    if (!open) return;
    if (!selectedCollectionId && collections.length > 0) {
      setSelectedCollectionId(collections[0].id);
    }
  }, [open, selectedCollectionId, collections]);

  useEffect(() => {
    if (!open || !selectedCollectionId) return;
    const fetchDocuments = async () => {
      setLoadingDocuments(true);
      try {
        const collectionData = await getCollection(getToken, selectedCollectionId);
        setCollectionDocuments(collectionData.documents || []);
      } catch (error) {
        console.error("Failed to fetch collection documents:", error);
        setCollectionDocuments([]);
      } finally {
        setLoadingDocuments(false);
      }
    };
    fetchDocuments();
  }, [open, selectedCollectionId, getToken]);

  const availableDocuments = useMemo(() => {
    const docs = collectionDocuments.filter(
      (doc) => doc.status === "completed" && !sessionDocIds.has(doc.id)
    );
    if (!addSearchQuery.trim()) return docs;
    const query = addSearchQuery.toLowerCase();
    return docs.filter((doc) => doc.filename?.toLowerCase().includes(query));
  }, [collectionDocuments, sessionDocIds, addSearchQuery]);

  const sessionDocuments = useMemo(() => {
    const docs = currentSessionDocuments || [];
    if (!manageSearchQuery.trim()) return docs;
    const query = manageSearchQuery.toLowerCase();
    return docs.filter((doc) => (doc.filename || doc.name || "").toLowerCase().includes(query));
  }, [currentSessionDocuments, manageSearchQuery]);

  const handleToggleDoc = (docId) => {
    setDocsToAdd((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    );
  };

  const handleClose = (nextOpen) => {
    if (!nextOpen) {
      setDocsToAdd([]);
      setManageSearchQuery("");
      setAddSearchQuery("");
    }
    onOpenChange?.(nextOpen);
  };

  const handleAddDocuments = () => {
    if (docsToAdd.length === 0) return;
    onAddDocuments?.(docsToAdd);
    setDocsToAdd([]);
    handleClose(false);
  };

  const handleRemoveDocument = async (documentId) => {
    if (!onRemoveDocument) return;
    try {
      setRemovingDocumentId(documentId);
      await onRemoveDocument(documentId);
      setDocsToAdd((prev) => prev.filter((id) => id !== documentId));
    } finally {
      setRemovingDocumentId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-4xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="w-4 h-4" />
            Manage Documents
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="current" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="current">
              Current Files ({currentSessionDocuments.length})
            </TabsTrigger>
            <TabsTrigger value="add">Add New</TabsTrigger>
          </TabsList>

          <TabsContent value="current" className="mt-4 min-h-0 flex-1 overflow-hidden">
            <div className="flex h-full min-h-0 flex-col">
              <div className="relative mb-3">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Search current session files..."
                  value={manageSearchQuery}
                  onChange={(e) => setManageSearchQuery(e.target.value)}
                  className="pl-8 h-9 text-sm"
                />
              </div>

              <div className="min-h-0 flex-1 overflow-y-auto pr-1">
                {currentSessionDocuments.length === 0 ? (
                  <div className="text-center py-8 bg-muted/30 rounded-lg border border-dashed">
                    <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
                    <p className="text-sm text-muted-foreground">
                      No documents in this session yet.
                    </p>
                  </div>
                ) : sessionDocuments.length === 0 ? (
                  <div className="text-center py-8 bg-muted/30 rounded-lg border border-dashed">
                    <p className="text-sm text-muted-foreground">
                      No current session documents match your search.
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 rounded-lg border border-border/70 p-2">
                    {sessionDocuments.map((doc) => (
                      <div
                        key={doc.id}
                        className="flex items-center gap-3 rounded-lg border border-border/60 px-3 py-2.5 transition-colors hover:bg-muted/30"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm text-foreground">
                            {doc.filename || doc.name || "Untitled"}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {getPageLabel(doc)}
                          </p>
                        </div>
                        {onRemoveDocument && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 shrink-0 rounded-full text-muted-foreground hover:text-destructive"
                            disabled={removingDocumentId === doc.id}
                            onClick={() => handleRemoveDocument(doc.id)}
                            title="Remove document"
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </TabsContent>

          <TabsContent value="add" className="mt-4 min-h-0 flex-1 overflow-hidden">
            <div className="flex h-full min-h-0 flex-col space-y-4 pr-1">
              <div>
                <label className="text-xs font-medium text-foreground mb-1.5 flex items-center gap-2">
                  <FileText className="w-3.5 h-3.5" />
                  Select Collection
                </label>
                {collections.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic py-2">
                    No collections available
                  </p>
                ) : (
                  <Combobox
                    items={collections.map((col) => ({
                      value: col.id,
                      label: col.name,
                      subtitle: `${col.document_count} docs`,
                    }))}
                    value={selectedCollectionId}
                    onValueChange={setSelectedCollectionId}
                    placeholder="Choose collection..."
                    searchPlaceholder="Search collections..."
                    emptyMessage="No collections found."
                    className="h-9 text-sm"
                  />
                )}
              </div>

              {selectedCollectionId && (
                <div className="flex min-h-0 flex-1 flex-col">
                  <label className="text-xs font-medium text-foreground mb-1.5 block">
                    Add Documents ({docsToAdd.length} selected)
                  </label>

                  <div className="relative mb-3">
                    <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      placeholder="Search documents..."
                      value={addSearchQuery}
                      onChange={(e) => setAddSearchQuery(e.target.value)}
                      className="pl-8 h-9 text-sm"
                    />
                  </div>

                  <div className="min-h-0 flex-1 overflow-y-auto">
                    {loadingDocuments ? (
                      <div className="flex items-center justify-center py-8">
                        <Spinner size="sm" />
                      </div>
                    ) : availableDocuments.length === 0 ? (
                      <div className="text-center py-8 bg-muted/30 rounded-lg border border-dashed">
                        <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
                        <p className="text-sm text-muted-foreground">
                          {addSearchQuery
                            ? "No documents match your search"
                            : collectionDocuments.length === 0
                            ? "No documents in this collection"
                            : "All documents are already added"}
                        </p>
                      </div>
                    ) : (
                      <div className="space-y-1.5 max-h-full overflow-y-auto scrollbar-thin">
                        {availableDocuments.map((doc) => {
                          const isSelected = docsToAdd.includes(doc.id);
                          const { Icon, className } = getStatusBadge(doc.status);

                          return (
                            <div
                              key={doc.id}
                              className={`p-3 rounded-lg border transition-all cursor-pointer ${
                                isSelected
                                  ? "bg-primary/5 border-primary"
                                  : "border-border hover:border-muted-foreground/30 hover:bg-muted/30"
                              }`}
                              onClick={() => handleToggleDoc(doc.id)}
                            >
                              <div className="flex items-center gap-2">
                                <Checkbox
                                  id={`add-doc-${doc.id}`}
                                  checked={isSelected}
                                  onCheckedChange={() => handleToggleDoc(doc.id)}
                                  onClick={(e) => e.stopPropagation()}
                                />

                                <div className="flex-1 min-w-0">
                                  <label
                                    htmlFor={`add-doc-${doc.id}`}
                                    className="text-xs truncate block text-foreground cursor-pointer"
                                  >
                                    {doc.filename}
                                  </label>
                                  <div className="flex items-center gap-2 mt-0.5">
                                    <span className="text-xs text-muted-foreground">
                                      {getPageLabel(doc)}
                                    </span>
                                    <Icon className={`w-3 h-3 ${className}`} />
                                  </div>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </TabsContent>
        </Tabs>

        <DialogFooter className="pt-2 border-t mt-4">
          <Button variant="outline" onClick={() => handleClose(false)}>
            Cancel
          </Button>
          <Button onClick={handleAddDocuments} disabled={docsToAdd.length === 0}>
            Add {docsToAdd.length} Document{docsToAdd.length !== 1 ? "s" : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
