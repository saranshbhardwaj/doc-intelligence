/**
 * EmptyState Component - Dialog Version
 *
 * Document selector for starting a new chat session, presented as a Dialog modal.
 * Left pane: collections list (click to select).
 * Right pane: document grid with file-type icons + selection state.
 * Footer: always visible — overlapping doc avatar circles + count + Cancel / Start Chat.
 *
 * Input:
 *   - open: boolean — controls dialog visibility
 *   - onOpenChange: (open: boolean) => void — called to open/close dialog
 *   - collections: Array<{id, name, document_count}>
 *   - collectionsLoading: boolean
 *   - selectedDocumentIds: string[]
 *   - onSelectDocuments: (documentIds: string[]) => void
 *   - onStartChat: (documentIds: string[]) => void
 *   - getToken: () => Promise<string>
 */

import { useState, useEffect, useMemo } from "react";
import {
  FileText,
  FileSpreadsheet,
  File,
  CheckCircle,
  Folder,
  Search,
  ChevronRight,
  Plus,
  Send,
} from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import Spinner from "../common/Spinner";
import { getCollection } from "../../api/chat";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "../ui/dialog";

const getDocFileIcon = (filename) => {
  const ext = filename?.toLowerCase().split(".").pop();
  if (ext === "pdf")
    return {
      Icon: FileText,
      bg: "bg-red-50 dark:bg-red-900/20",
      color: "text-red-500 dark:text-red-400",
    };
  if (["xlsx", "xls"].includes(ext))
    return {
      Icon: FileSpreadsheet,
      bg: "bg-green-50 dark:bg-green-900/20",
      color: "text-green-600 dark:text-green-400",
    };
  return {
    Icon: File,
    bg: "bg-blue-50 dark:bg-blue-900/20",
    color: "text-blue-500 dark:text-blue-400",
  };
};

export default function EmptyState({
  open = false,
  onOpenChange,
  collections = [],
  collectionsLoading = false,
  selectedDocumentIds = [],
  onSelectDocuments,
  onStartChat,
  isCreating = false,
  getToken,
}) {
  const [selectedCollectionId, setSelectedCollectionId] = useState(null);
  const [collectionDocuments, setCollectionDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [localSelectedDocs, setLocalSelectedDocs] = useState(selectedDocumentIds);
  const [selectedDocsInfo, setSelectedDocsInfo] = useState([]);
  const [documentSearchQuery, setDocumentSearchQuery] = useState("");
  const [sessionTitle, setSessionTitle] = useState("");

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
      const newSelection = localSelectedDocs.filter((id) => id !== doc.id);
      const newDocsInfo = selectedDocsInfo.filter((d) => d.id !== doc.id);
      setLocalSelectedDocs(newSelection);
      setSelectedDocsInfo(newDocsInfo);
      onSelectDocuments?.(newSelection);
    } else {
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

  const handleStartChat = () => {
    if (localSelectedDocs.length > 0) {
      onStartChat?.(localSelectedDocs, sessionTitle.trim() || null);
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

  const handleCancel = () => {
    setLocalSelectedDocs([]);
    setSelectedDocsInfo([]);
    setSessionTitle("");
    onSelectDocuments?.([]);
    onOpenChange?.(false);
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

  const allInViewSelected =
    filteredDocuments.length > 0 &&
    filteredDocuments.every((doc) => localSelectedDocs.includes(doc.id));

  const activeCollectionName = collections.find((c) => c.id === selectedCollectionId)?.name;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-full h-[88vh] max-h-[900px] p-0 flex flex-col overflow-hidden gap-0">
        {/* Header */}
        <div className="p-6 md:p-8 border-b border-border flex-shrink-0 space-y-4">
          <div className="flex justify-between items-start flex-wrap gap-4">
            <div>
              <DialogTitle className="text-2xl md:text-3xl font-black text-foreground tracking-tight leading-tight">
                Start a New Chat
              </DialogTitle>
              <DialogDescription className="text-muted-foreground mt-1 text-sm">
                Select documents from your collections to begin analyzing.
              </DialogDescription>
            </div>
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search files..."
                value={documentSearchQuery}
                onChange={(e) => setDocumentSearchQuery(e.target.value)}
                className="pl-9 h-9 w-44 md:w-56"
              />
            </div>
          </div>
          {/* Session name */}
          <div className="flex items-center gap-3 max-w-md">
            <label className="text-sm font-medium text-foreground whitespace-nowrap">
              Session name
            </label>
            <Input
              placeholder="e.g. Q3 Deal Review"
              value={sessionTitle}
              onChange={(e) => setSessionTitle(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !isCreating && handleStartChat()}
              className="h-9 text-sm"
              autoFocus={false}
            />
          </div>
        </div>

        {/* Two-pane body */}
        <div className="flex-1 flex overflow-hidden flex-col md:flex-row min-h-0">
          {/* Left pane: Collections */}
          <div className="md:w-72 flex-shrink-0 md:border-r border-b md:border-b-0 border-border flex md:flex-col flex-row overflow-x-auto md:overflow-hidden bg-muted/20">
            {/* Sticky header — desktop only */}
            <div className="hidden md:flex p-4 border-b border-border bg-card flex-shrink-0 items-center">
              <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Collections
              </p>
            </div>

            {/* List */}
            <div className="flex md:flex-col flex-row md:flex-1 md:overflow-y-auto overflow-x-auto px-2 py-2 md:py-2 gap-1 md:gap-1 md:space-y-0">
              {collectionsLoading ? (
                <div className="flex items-center justify-center p-4 w-full">
                  <Spinner size="sm" />
                </div>
              ) : collections.length === 0 ? (
                <div className="flex items-center justify-center p-4 w-full">
                  <p className="text-xs text-muted-foreground">No collections</p>
                </div>
              ) : (
                collections.map((col) => {
                  const isActive = selectedCollectionId === col.id;
                  return (
                    <button
                      key={col.id}
                      onClick={() => setSelectedCollectionId(col.id)}
                      className={`flex items-center justify-between p-3 rounded-lg cursor-pointer transition-all text-left shrink-0 md:w-full
                        ${
                          isActive
                            ? "bg-card shadow-sm border border-border"
                            : "hover:bg-card border border-transparent hover:border-border"
                        }`}
                    >
                      <div className="flex items-center gap-2.5 min-w-0 flex-1">
                        <Folder className={`w-4 h-4 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                        <div className="flex flex-col min-w-0">
                          <span className={`font-semibold text-sm truncate ${isActive ? "text-foreground" : "text-foreground/80"}`}>
                            {col.name}
                          </span>
                          <span className="hidden md:block text-xs text-muted-foreground">
                            {col.document_count} Documents
                          </span>
                        </div>
                      </div>
                      {isActive && (
                        <ChevronRight className="w-4 h-4 text-primary shrink-0 ml-2 hidden md:block" />
                      )}
                    </button>
                  );
                })
              )}
            </div>

            {/* New Collection link — desktop footer */}
            <div className="hidden md:flex p-4 border-t border-border bg-card flex-shrink-0">
              <a
                href="/app/library"
                className="w-full py-2 flex items-center justify-center gap-2 text-primary hover:bg-primary/10 rounded-lg transition-colors text-sm font-semibold"
              >
                <Plus className="w-4 h-4" />
                New Collection
              </a>
            </div>
          </div>

          {/* Right pane: Documents */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Sub-header */}
            <div className="px-4 py-3 border-b border-border flex items-center justify-between bg-card flex-shrink-0">
              <div className="flex items-center gap-2">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Documents
                  {activeCollectionName && (
                    <>
                      {" in "}
                      <span className="text-primary">{activeCollectionName}</span>
                    </>
                  )}
                </h3>
                {filteredDocuments.length > 0 && (
                  <span className="bg-muted text-foreground text-[10px] font-bold px-1.5 py-0.5 rounded">
                    {filteredDocuments.length}
                  </span>
                )}
              </div>
              {filteredDocuments.length > 0 && (
                <button
                  onClick={handleSelectAll}
                  className="text-xs font-medium text-primary hover:underline transition-colors"
                >
                  {allInViewSelected ? "Deselect All" : "Select All"}
                </button>
              )}
            </div>

            {/* Doc list */}
            <div className="flex-1 overflow-y-auto p-3 space-y-1.5">
              {!selectedCollectionId ? (
                <div className="flex flex-col items-center justify-center h-full text-center py-12">
                  <Folder className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
                  <p className="text-sm text-muted-foreground">
                    Select a collection to view documents
                  </p>
                </div>
              ) : loadingDocuments ? (
                <div className="flex items-center justify-center py-12">
                  <Spinner size="sm" />
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center py-12">
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
                filteredDocuments.map((doc) => {
                  const isSelected = localSelectedDocs.includes(doc.id);
                  const { Icon, bg, color } = getDocFileIcon(doc.filename);
                  return (
                    <div
                      key={doc.id}
                      onClick={() => handleToggleDocument(doc)}
                      className={`flex items-center gap-4 p-3 rounded-lg border cursor-pointer transition-colors group
                        ${
                          isSelected
                            ? "border-primary/30 bg-primary/5 hover:bg-primary/10"
                            : "border-border hover:border-primary/30 hover:bg-muted/30"
                        }`}
                    >
                      {/* File icon — colored when selected, muted when not */}
                      <div
                        className={`p-2 rounded-lg transition-colors flex-shrink-0 ${
                          isSelected ? bg : "bg-muted"
                        }`}
                      >
                        <Icon
                          className={`w-5 h-5 ${
                            isSelected ? color : "text-muted-foreground"
                          }`}
                        />
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <p
                          className={`font-medium text-sm truncate transition-colors ${
                            isSelected
                              ? "text-primary"
                              : "text-foreground group-hover:text-primary"
                          }`}
                        >
                          {doc.filename}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {doc.page_count || 0} pages &bull; {doc.chunk_count || 0} chunks
                        </p>
                      </div>

                      {/* Right indicator */}
                      {isSelected ? (
                        <CheckCircle className="w-5 h-5 text-primary shrink-0" />
                      ) : (
                        <div className="w-5 h-5 rounded-full border-2 border-muted-foreground/30 opacity-0 group-hover:opacity-60 shrink-0 transition-opacity" />
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Footer — always visible */}
        <div className="border-t border-border bg-muted/30 px-5 md:px-8 py-4 flex flex-col md:flex-row items-center justify-between gap-4 flex-shrink-0">
          {/* Left: overlapping circles + status text */}
          <div className="flex items-center gap-4">
            <div className="flex -space-x-2 overflow-hidden">
              {selectedDocsInfo.slice(0, 2).map((doc) => {
                const { Icon, bg, color } = getDocFileIcon(doc.name);
                return (
                  <div
                    key={doc.id}
                    className={`w-8 h-8 rounded-full ring-2 ring-background ${bg} flex items-center justify-center shadow-sm`}
                  >
                    <Icon className={`w-4 h-4 ${color}`} />
                  </div>
                );
              })}
              {selectedDocsInfo.length > 2 && (
                <div className="w-8 h-8 rounded-full ring-2 ring-background bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground shadow-sm">
                  +{selectedDocsInfo.length - 2}
                </div>
              )}
            </div>
            <div className="flex flex-col">
              <span className="text-foreground font-bold text-sm">
                {selectedDocsInfo.length > 0
                  ? `${selectedDocsInfo.length} Document${selectedDocsInfo.length !== 1 ? "s" : ""} Selected`
                  : "No documents selected"}
              </span>
              <span className="text-muted-foreground text-xs">
                {selectedDocsInfo.length > 0
                  ? "Ready to analyze"
                  : "Select documents to begin"}
              </span>
            </div>
          </div>

          {/* Right: Cancel + Start Chat */}
          <div className="flex items-center gap-3 w-full md:w-auto">
            <Button
              variant="outline"
              onClick={handleCancel}
              className="flex-1 md:flex-none"
            >
              Cancel
            </Button>
            <Button
              onClick={handleStartChat}
              disabled={selectedDocsInfo.length === 0 || isCreating}
              className="flex-1 md:flex-none gap-2"
            >
              {isCreating ? (
                <>
                  <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                  </svg>
                  Starting…
                </>
              ) : (
                <>
                  Start Chat
                  <Send className="w-4 h-4" />
                </>
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
