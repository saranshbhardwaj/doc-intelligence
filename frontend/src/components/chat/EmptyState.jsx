/**
 * EmptyState Component - Redesigned
 *
 * Production-level UI for selecting documents across multiple collections.
 * ChatGPT-inspired design with elegant interactions.
 *
 * Input:
 *   - collections: Array<{id, name, document_count}>
 *   - collectionsLoading: boolean
 *   - selectedDocumentIds: string[]
 *   - onSelectDocuments: (documentIds: string[]) => void
 *   - onStartChat: (documentIds: string[]) => void
 *   - getToken: () => Promise<string>
 *
 * Output:
 *   - Renders empty state with multi-collection document selector
 *   - Triggers session creation with selected documents
 */

import { useState, useEffect, useMemo } from "react";
import {
  MessageSquare,
  FileText,
  CheckCircle,
  X,
  Sparkles,
  Folder,
  Search,
} from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Combobox } from "../ui/combobox";
import Spinner from "../common/Spinner";
import { getCollection } from "../../api/chat";

export default function EmptyState({
  collections = [],
  collectionsLoading = false,
  selectedDocumentIds = [],
  onSelectDocuments,
  onStartChat,
  getToken,
}) {
  const [selectedCollectionId, setSelectedCollectionId] = useState(null);
  const [collectionDocuments, setCollectionDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [localSelectedDocs, setLocalSelectedDocs] = useState(selectedDocumentIds);
  const [selectedDocsInfo, setSelectedDocsInfo] = useState([]); // Store {id, name, collection} for display

  // Search state
  const [documentSearchQuery, setDocumentSearchQuery] = useState("");

  // Auto-select first collection
  useEffect(() => {
    if (!selectedCollectionId && collections.length > 0) {
      setSelectedCollectionId(collections[0].id);
    }
  }, [collections, selectedCollectionId]);

  // Fetch collection documents when collection changes
  useEffect(() => {
    if (selectedCollectionId && getToken) {
      fetchCollectionDocuments(selectedCollectionId);
    }
  }, [selectedCollectionId]);

  // Sync with parent
  useEffect(() => {
    setLocalSelectedDocs(selectedDocumentIds);
  }, [selectedDocumentIds]);

  const fetchCollectionDocuments = async (collectionId) => {
    setLoadingDocuments(true);
    try {
      const collectionData = await getCollection(getToken, collectionId);
      setCollectionDocuments(collectionData.documents || []);
    } catch (error) {
      console.error("Failed to fetch collection documents:", error);
      setCollectionDocuments([]);
    } finally {
      setLoadingDocuments(false);
    }
  };

  const handleToggleDocument = (doc) => {
    const isCurrentlySelected = localSelectedDocs.includes(doc.id);
    const selectedCollection = collections.find((c) => c.id === selectedCollectionId);

    if (isCurrentlySelected) {
      // Remove document
      const newSelection = localSelectedDocs.filter((id) => id !== doc.id);
      const newDocsInfo = selectedDocsInfo.filter((d) => d.id !== doc.id);

      setLocalSelectedDocs(newSelection);
      setSelectedDocsInfo(newDocsInfo);
      onSelectDocuments?.(newSelection);
    } else {
      // Add document
      const newSelection = [...localSelectedDocs, doc.id];
      const newDocsInfo = [
        ...selectedDocsInfo,
        {
          id: doc.id,
          name: doc.filename,
          collection: selectedCollection?.name || "Unknown",
        },
      ];

      setLocalSelectedDocs(newSelection);
      setSelectedDocsInfo(newDocsInfo);
      onSelectDocuments?.(newSelection);
    }
  };

  const handleRemoveDocument = (docId) => {
    const newSelection = localSelectedDocs.filter((id) => id !== docId);
    const newDocsInfo = selectedDocsInfo.filter((d) => d.id !== docId);

    setLocalSelectedDocs(newSelection);
    setSelectedDocsInfo(newDocsInfo);
    onSelectDocuments?.(newSelection);
  };

  const handleStartChat = () => {
    if (localSelectedDocs.length > 0) {
      onStartChat?.(localSelectedDocs);
    }
  };

  const handleSelectAll = () => {
    const selectedCollection = collections.find((c) => c.id === selectedCollectionId);
    const allInView = filteredDocuments.map((doc) => doc.id);
    const allSelected = allInView.every((id) => localSelectedDocs.includes(id));

    if (allSelected) {
      const newSelection = localSelectedDocs.filter((id) => !allInView.includes(id));
      const newDocsInfo = selectedDocsInfo.filter((d) => !allInView.includes(d.id));
      setLocalSelectedDocs(newSelection);
      setSelectedDocsInfo(newDocsInfo);
      onSelectDocuments?.(newSelection);
    } else {
      const toAdd = filteredDocuments.filter((doc) => !localSelectedDocs.includes(doc.id));
      const newSelection = [...localSelectedDocs, ...toAdd.map((d) => d.id)];
      const newDocsInfo = [
        ...selectedDocsInfo,
        ...toAdd.map((d) => ({
          id: d.id,
          name: d.filename,
          collection: selectedCollection?.name || "Unknown",
        })),
      ];
      setLocalSelectedDocs(newSelection);
      setSelectedDocsInfo(newDocsInfo);
      onSelectDocuments?.(newSelection);
    }
  };

  // Only show completed documents, filtered by search
  const filteredDocuments = useMemo(() => {
    return collectionDocuments
      .filter((doc) => doc.status === "completed")
      .filter((doc) =>
        documentSearchQuery.trim()
          ? doc.filename.toLowerCase().includes(documentSearchQuery.toLowerCase())
          : true
      );
  }, [collectionDocuments, documentSearchQuery]);

  return (
    <div className="flex-1 flex flex-col bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 bg-primary/10 rounded-lg flex items-center justify-center">
              <MessageSquare className="w-5 h-5 text-primary" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                New Chat Session
              </h2>
              <p className="text-sm text-muted-foreground">
                Select documents to start chatting
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-4xl mx-auto p-6 space-y-6">
          {/* Selected Documents Preview */}
          {selectedDocsInfo.length > 0 && (
            <Card className="p-4 bg-primary/5 border-primary/20 animate-fade-in">
              <div className="flex items-start gap-3">
                <Sparkles className="w-5 h-5 text-primary mt-0.5 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-sm font-semibold text-foreground">
                      Selected Documents ({selectedDocsInfo.length})
                    </h3>
                    <Button
                      onClick={handleStartChat}
                      size="sm"
                      className="h-8"
                    >
                      Start Chat
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {selectedDocsInfo.map((doc, index) => (
                      <div
                        key={doc.id}
                        className="group flex items-center gap-2 px-3 py-1.5 bg-card border border-border rounded-lg hover:border-primary/50 transition-colors animate-chip-fade-in"
                        style={{ animationDelay: `${index * 50}ms` }}
                      >
                        <FileText className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                        <div className="flex flex-col min-w-0">
                          <span className="text-xs font-medium text-foreground truncate max-w-[200px]">
                            {doc.name}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {doc.collection}
                          </span>
                        </div>
                        <button
                          onClick={() => handleRemoveDocument(doc.id)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-destructive/10 rounded"
                        >
                          <X className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          )}

          {/* Collection & Document Selector */}
          <Card className="p-6 animate-scale-up">
            {/* Collection Selector */}
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-3">
                <Folder className="w-4 h-4 text-muted-foreground" />
                <label className="text-sm font-semibold text-foreground">
                  Choose Collection
                </label>
              </div>

              {collectionsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Spinner size="sm" />
                </div>
              ) : collections.length === 0 ? (
                <div className="text-center py-12 bg-muted/30 rounded-lg border border-dashed border-border">
                  <Folder className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
                  <p className="text-sm text-muted-foreground mb-1">
                    No collections found
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Create a collection in the Library to get started
                  </p>
                </div>
              ) : (
                <Combobox
                  items={collections.map((col) => ({
                    value: col.id,
                    label: col.name,
                    subtitle: `${col.document_count} docs`,
                  }))}
                  value={selectedCollectionId}
                  onValueChange={setSelectedCollectionId}
                  placeholder="Select a collection..."
                  searchPlaceholder="Search collections..."
                  emptyMessage="No collections found."
                />
              )}
            </div>

            {/* Documents List */}
            {selectedCollectionId && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4 text-muted-foreground" />
                    <label className="text-sm font-semibold text-foreground">
                      Select Documents
                    </label>
                  </div>
                  {filteredDocuments.length > 0 && (
                    <button
                      onClick={handleSelectAll}
                      className="text-xs text-primary hover:text-primary/80 font-medium transition-colors"
                    >
                      {filteredDocuments.every((doc) => localSelectedDocs.includes(doc.id))
                        ? "Deselect all"
                        : `Select all (${filteredDocuments.length})`}
                    </button>
                  )}
                </div>

                {/* Document Search */}
                <div className="mb-3">
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Search documents..."
                      value={documentSearchQuery}
                      onChange={(e) => setDocumentSearchQuery(e.target.value)}
                      className="pl-9 h-10"
                    />
                  </div>
                  {documentSearchQuery && (
                    <p className="text-xs text-muted-foreground mt-1.5">
                      Showing {filteredDocuments.length} of {collectionDocuments.filter((d) => d.status === "completed").length} documents
                    </p>
                  )}
                </div>

                {/* Change Collection Helper */}
                {collectionDocuments.filter((d) => d.status === "completed").length > 0 && collections.length > 1 && (
                  <p className="text-xs text-muted-foreground mb-3">
                    Switch collection above to add documents from other collections.
                  </p>
                )}

                {loadingDocuments ? (
                  <div className="flex items-center justify-center py-12">
                    <Spinner size="sm" />
                  </div>
                ) : filteredDocuments.length === 0 ? (
                  <div className="text-center py-12 bg-muted/30 rounded-lg border border-dashed border-border">
                    <FileText className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
                    <p className="text-sm text-muted-foreground mb-1">
                      {documentSearchQuery
                        ? "No documents match your search"
                        : "No completed documents in this collection"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {documentSearchQuery
                        ? "Try a different search term"
                        : "Upload and index documents from the Library page"}
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 scrollbar-thin">
                    {filteredDocuments.map((doc) => {
                      const isSelected = localSelectedDocs.includes(doc.id);

                      return (
                        <div
                          key={doc.id}
                          className={`group p-4 rounded-lg border transition-all cursor-pointer ${
                            isSelected
                              ? "border-primary bg-primary/5"
                              : "border-border hover:border-muted-foreground/30 hover:bg-muted/30"
                          }`}
                          onClick={() => handleToggleDocument(doc)}
                        >
                          <div className="flex items-start gap-3">
                            <Checkbox
                              id={`doc-${doc.id}`}
                              checked={isSelected}
                              onCheckedChange={() => handleToggleDocument(doc)}
                              className="mt-1"
                              onClick={(e) => e.stopPropagation()}
                            />

                            {/* Document Info */}
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-3">
                                <div className="flex-1 min-w-0">
                                  <h4 className="text-sm font-medium truncate text-foreground">
                                    {doc.filename}
                                  </h4>
                                  <div className="flex items-center gap-3 mt-1.5">
                                    <span className="text-xs text-muted-foreground">
                                      {doc.page_count || 0} pages
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                      {doc.chunk_count || 0} chunks
                                    </span>
                                  </div>
                                </div>

                                <div className="flex-shrink-0">
                                  <div className="flex items-center gap-1.5 px-2 py-1 bg-success/10 text-success rounded text-xs font-medium">
                                    <CheckCircle className="w-3 h-3" />
                                    Ready
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

              </div>
            )}
          </Card>

          {/* CTA Card */}
          {selectedDocsInfo.length === 0 && (
            <Card className="p-6 text-center bg-muted/30 border-dashed">
              <MessageSquare className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
              <h3 className="text-base font-medium text-foreground mb-1">
                Ready to start?
              </h3>
              <p className="text-sm text-muted-foreground">
                Select documents from any collection to begin your chat session
              </p>
            </Card>
          )}
        </div>
      </div>

      {/* Fixed Bottom Action Bar (shows when documents selected) */}
      {selectedDocsInfo.length > 0 && (
        <div className="border-t border-border bg-card px-6 py-4 shadow-lg">
          <div className="max-w-4xl mx-auto flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">
                  {selectedDocsInfo.length} document{selectedDocsInfo.length !== 1 ? "s" : ""} selected
                </span>
              </div>
              <div className="h-4 w-px bg-border" />
              <button
                onClick={() => {
                  setLocalSelectedDocs([]);
                  setSelectedDocsInfo([]);
                  onSelectDocuments?.([]);
                }}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
              >
                Clear all
              </button>
            </div>
            <Button onClick={handleStartChat} size="lg" className="min-w-[160px]">
              <Sparkles className="w-4 h-4 mr-2" />
              Start Chat
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
