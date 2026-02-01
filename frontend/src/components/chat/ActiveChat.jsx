/**
 * ActiveChat Component - Redesigned
 *
 * Production-level active chat interface with session management.
 * Includes inline title editing, proper document selection, and real-time updates.
 *
 * Input:
 *   - currentSession: { id, title, documents: [{id, filename, added_at}, ...] }
 *   - messages: Array<{role: 'user'|'assistant', content: string, created_at: string}>
 *   - isStreaming: boolean
 *   - streamingMessage: string
 *   - chatError: string | null
 *   - collections: Array (for adding documents)
 *   - getToken: () => Promise<string>
 *   - onSendMessage: (message: string) => void
 *   - onAddDocuments: (documentIds: string[]) => void
 *   - onRemoveDocument: (documentId: string) => void
 *   - onUpdateSessionTitle: (title: string) => void
 *   - onExportSession: () => void
 *
 * Output:
 *   - Renders active chat interface
 *   - Handles message sending
 *   - Manages document chips
 *   - Editable session title
 */

import { useState, useRef, useEffect, useMemo } from "react";
import {
  Send,
  Download,
  FileText,
  X,
  Plus,
  Check,
  Pencil,
  CheckCircle,
  Clock,
  XCircle,
  Search,
  Filter,
  FileDown,
  Loader2,
} from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { Input } from "../ui/input";
import { Checkbox } from "../ui/checkbox";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Combobox } from "../ui/combobox";
import Spinner from "../common/Spinner";
import { getCollection } from "../../api/chat";
import { ComparisonMessage, StreamingComparisonContent } from "./comparison";
import { useComparison, usePdfViewer, useChatActions } from "../../store";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ComparisonPanel from "../comparison/ComparisonPanel";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "../ui/resizable";
import PDFViewer from "../pdf/PDFViewer";

export default function ActiveChat({
  currentSession,
  messages = [],
  isStreaming = false,
  isThinking = false,
  streamingMessage = "",
  chatError = null,
  collections = [],
  getToken,
  onSendMessage,
  onAddDocuments,
  onRemoveDocument,
  onUpdateSessionTitle,
  onExportSession,
}) {
  const [message, setMessage] = useState("");
  const [showDocumentManager, setShowDocumentManager] = useState(false);
  const [selectedCollectionId, setSelectedCollectionId] = useState(null);
  const [collectionDocuments, setCollectionDocuments] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(false);
  const [docsToAdd, setDocsToAdd] = useState([]);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState(currentSession?.title || "");
  const [showComparisonPanel, setShowComparisonPanel] = useState(false);
  const [showPdfPanel, setShowPdfPanel] = useState(false);
  const messagesEndRef = useRef(null);
  const titleInputRef = useRef(null);

  // Search and filter state
  const [documentSearchQuery, setDocumentSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingMessage]);

  // Auto-select first collection
  useEffect(() => {
    if (!selectedCollectionId && collections.length > 0) {
      setSelectedCollectionId(collections[0].id);
    }
  }, [collections, selectedCollectionId]);

  // Fetch collection documents when collection changes
  useEffect(() => {
    if (selectedCollectionId && showDocumentManager) {
      fetchCollectionDocuments(selectedCollectionId);
    }
  }, [selectedCollectionId, showDocumentManager]);

  // Focus title input when editing
  useEffect(() => {
    if (isEditingTitle && titleInputRef.current) {
      titleInputRef.current.focus();
      titleInputRef.current.select();
    }
  }, [isEditingTitle]);

  // Sync title with current session
  useEffect(() => {
    setEditedTitle(currentSession?.title || "");
  }, [currentSession?.title]);

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

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!message.trim() || isStreaming) return;

    onSendMessage?.(message.trim());
    setMessage("");
  };

  const handleAddDocuments = () => {
    if (docsToAdd.length > 0) {
      onAddDocuments?.(docsToAdd);
      setDocsToAdd([]);
      setShowDocumentManager(false);
    }
  };

  const handleToggleDoc = (docId) => {
    setDocsToAdd((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
  };

  const handleSaveTitle = () => {
    if (editedTitle.trim() && editedTitle !== currentSession?.title) {
      onUpdateSessionTitle?.(editedTitle.trim());
    }
    setIsEditingTitle(false);
  };

  const handleCancelTitleEdit = () => {
    setEditedTitle(currentSession?.title || "");
    setIsEditingTitle(false);
  };

  const handleTitleKeyDown = (e) => {
    if (e.key === "Enter") {
      handleSaveTitle();
    } else if (e.key === "Escape") {
      handleCancelTitleEdit();
    }
  };

  const sessionDocIds = currentSession?.documents?.map((d) => d.id) || [];

  // Filter and process documents
  const filteredDocuments = useMemo(() => {
    let filtered = [...collectionDocuments];

    // Search filter
    if (documentSearchQuery.trim()) {
      const query = documentSearchQuery.toLowerCase();
      filtered = filtered.filter((doc) =>
        doc.filename.toLowerCase().includes(query)
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter((doc) => doc.status === statusFilter);
    }

    return filtered;
  }, [collectionDocuments, documentSearchQuery, statusFilter]);

  // Filter documents: exclude already-in-session AND only show completed
  const availableDocuments = filteredDocuments.filter(
    (doc) => !sessionDocIds.includes(doc.id) && doc.status === "completed"
  );

  // Get comparison context for rendering
  const comparison = useComparison();
  const pdfViewer = usePdfViewer();
  const { clearHighlight, setActivePdfDocument, clearPdfUrlCache } = useChatActions();

  // Handler for opening full comparison panel
  const handleOpenComparisonPanel = () => {
    setShowComparisonPanel(true);
  };

  // Handler for clicking document chip (switch active PDF)
  const handleDocumentChipClick = (docId) => {
    setActivePdfDocument(docId, getToken);
    setShowPdfPanel(true);
  };

  // Clear PDF cache and reset panel state when session changes
  useEffect(() => {
    clearPdfUrlCache();
    setShowPdfPanel(false); // Reset local panel state
  }, [currentSession?.id, clearPdfUrlCache]);

  // Auto-show PDF panel when active document is set AND URL is available
  useEffect(() => {
    if (pdfViewer.activeDocumentId && pdfViewer.urlCache[pdfViewer.activeDocumentId]?.url) {
      setShowPdfPanel(true);
    }
  }, [pdfViewer.activeDocumentId, pdfViewer.urlCache]);

  // Auto-show PDF panel when highlight changes (for citation clicks)
  useEffect(() => {
    if (pdfViewer.highlightBbox) {
      setShowPdfPanel(true);
    }
  }, [pdfViewer.highlightBbox]);

  // Get active PDF URL from cache
  const activePdfUrl = pdfViewer.activeDocumentId
    ? pdfViewer.urlCache[pdfViewer.activeDocumentId]?.url
    : null;

  return (
    <ResizablePanelGroup
      direction="horizontal"
      className="flex-1 overflow-hidden"
    >
      {/* Left Panel: Chat Interface */}
      <ResizablePanel
        defaultSize={showPdfPanel ? 55 : 100}
        minSize={showPdfPanel ? 35 : 100}
        maxSize={showPdfPanel ? 70 : 100}
      >
        <div className="w-full flex flex-col h-full overflow-hidden">
          {/* Sticky Header with Editable Title and Document Chips */}
          <div className="sticky top-0 z-10 bg-card/80 backdrop-blur border-b border-border px-6 py-3">
        <div className="flex items-center justify-between mb-3">
          {/* Editable Title */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            {isEditingTitle ? (
              <div className="flex items-center gap-2 flex-1 max-w-md">
                <Input
                  ref={titleInputRef}
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  onKeyDown={handleTitleKeyDown}
                  onBlur={handleSaveTitle}
                  className="h-8 text-base font-semibold"
                  placeholder="Session title..."
                />
                <button
                  onClick={handleSaveTitle}
                  className="p-1.5 hover:bg-success/10 rounded transition-colors"
                  title="Save"
                >
                  <Check className="w-4 h-4 text-success" />
                </button>
                <button
                  onClick={handleCancelTitleEdit}
                  className="p-1.5 hover:bg-destructive/10 rounded transition-colors"
                  title="Cancel"
                >
                  <X className="w-4 h-4 text-destructive" />
                </button>
              </div>
            ) : (
              <div className="group flex items-center gap-2 flex-1 min-w-0">
                <h2 className="text-lg font-semibold text-foreground truncate">
                  {currentSession?.title || "Chat Session"}
                </h2>
                <button
                  onClick={() => setIsEditingTitle(true)}
                  className="opacity-50 hover:opacity-100 p-1.5 hover:bg-muted rounded transition-all"
                  title="Edit title"
                >
                  <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
              </div>
            )}
          </div>

          {/* Export Dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                Export
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem onClick={() => onExportSession?.("markdown")}>
                <FileText className="w-4 h-4 mr-2" />
                <div className="flex flex-col">
                  <span className="font-medium">Markdown</span>
                  <span className="text-xs text-muted-foreground">
                    Simple .md file
                  </span>
                </div>
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onExportSession?.("word")}>
                <FileDown className="w-4 h-4 mr-2" />
                <div className="flex flex-col">
                  <span className="font-medium">Word Document</span>
                  <span className="text-xs text-muted-foreground">
                    Professional .docx
                  </span>
                </div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Document Chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-muted-foreground font-medium">
            Documents ({sessionDocIds.length}):
          </span>

          {sessionDocIds.length === 0 ? (
            <span className="text-xs text-muted-foreground italic">
              No documents selected
            </span>
          ) : (
            <>
              {currentSession?.documents?.map((doc, index) => {
                const isActive = pdfViewer.activeDocumentId === doc.id;
                return (
                  <div
                    key={doc.id}
                    onClick={() => handleDocumentChipClick(doc.id)}
                    className={`group flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-all cursor-pointer animate-chip-fade-in ${
                      isActive
                        ? 'bg-primary text-primary-foreground ring-2 ring-primary/50'
                        : 'bg-primary/10 text-primary hover:bg-primary/20'
                    }`}
                    style={{ animationDelay: `${index * 30}ms` }}
                    title="Click to view PDF"
                  >
                    <FileText className="w-3 h-3" />
                    <span className="max-w-[120px] truncate">{doc.name}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onRemoveDocument?.(doc.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-destructive ml-0.5"
                      title="Remove document"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                );
              })}
            </>
          )}

          {/* Add Documents Button */}
          <button
            onClick={() => setShowDocumentManager(!showDocumentManager)}
            className="flex items-center gap-1 px-2.5 py-1 bg-muted hover:bg-muted/80 text-foreground rounded-full text-xs font-medium transition-all"
          >
            <Plus className="w-3 h-3" />
            Add
          </button>
        </div>

        {/* Document Manager (Expandable) */}
        {showDocumentManager && (
          <div className="mt-3 p-3 bg-muted/50 rounded-lg border border-border animate-fade-in">
            <div className="space-y-3">
              {/* Collection Selector */}
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

              {/* Documents List */}
              {selectedCollectionId && (
                <div>
                  <label className="text-xs font-medium text-foreground mb-1.5 block">
                    Select Documents to Add ({docsToAdd.length} selected)
                  </label>

                  {/* Document Search and Filter */}
                  <div className="space-y-2 mb-3">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input
                        placeholder="Search documents..."
                        value={documentSearchQuery}
                        onChange={(e) => setDocumentSearchQuery(e.target.value)}
                        className="pl-8 h-8 text-xs"
                      />
                    </div>

                    <div className="flex items-center gap-2">
                      <Filter className="w-3.5 h-3.5 text-muted-foreground" />
                      <Select
                        value={statusFilter}
                        onValueChange={setStatusFilter}
                      >
                        <SelectTrigger className="h-8 text-xs bg-background">
                          <SelectValue placeholder="Filter status..." />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">All Status</SelectItem>
                          <SelectItem value="completed">Completed</SelectItem>
                          <SelectItem value="processing">Processing</SelectItem>
                          <SelectItem value="failed">Failed</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Results count */}
                    {(documentSearchQuery || statusFilter !== "all") && (
                      <p className="text-xs text-muted-foreground">
                        {filteredDocuments.length} of{" "}
                        {collectionDocuments.length} documents
                      </p>
                    )}
                  </div>

                  {loadingDocuments ? (
                    <div className="flex items-center justify-center py-8">
                      <Spinner size="sm" />
                    </div>
                  ) : availableDocuments.length === 0 ? (
                    <div className="text-center py-6 bg-muted/30 rounded-lg border border-dashed">
                      <FileText className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
                      <p className="text-xs text-muted-foreground">
                        {documentSearchQuery || statusFilter !== "all"
                          ? "No documents match your filters"
                          : collectionDocuments.length === 0
                          ? "No documents in this collection"
                          : "All documents are already added"}
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-1.5 max-h-48 overflow-y-auto scrollbar-thin">
                      {filteredDocuments.map((doc) => {
                        const isInSession = sessionDocIds.includes(doc.id);
                        const isSelected = docsToAdd.includes(doc.id);
                        const isCompleted = doc.status === "completed";

                        return (
                          <div
                            key={doc.id}
                            className={`p-3 rounded-lg border transition-all ${
                              isInSession
                                ? "bg-success/5 border-success/30 cursor-not-allowed"
                                : isSelected
                                ? "bg-primary/5 border-primary"
                                : isCompleted
                                ? "border-border hover:border-muted-foreground/30 hover:bg-muted/30 cursor-pointer"
                                : "border-border bg-muted/20 opacity-60 cursor-not-allowed"
                            }`}
                            onClick={() =>
                              !isInSession &&
                              isCompleted &&
                              handleToggleDoc(doc.id)
                            }
                          >
                            <div className="flex items-center gap-2">
                              {isInSession ? (
                                <div className="flex items-center justify-center w-4 h-4 bg-success rounded">
                                  <Check className="w-3 h-3 text-success-foreground" />
                                </div>
                              ) : isCompleted ? (
                                <Checkbox
                                  id={`add-doc-${doc.id}`}
                                  checked={isSelected}
                                  onCheckedChange={() =>
                                    handleToggleDoc(doc.id)
                                  }
                                  onClick={(e) => e.stopPropagation()}
                                />
                              ) : (
                                <div className="w-4 h-4" />
                              )}

                              <div className="flex-1 min-w-0">
                                <label
                                  htmlFor={`add-doc-${doc.id}`}
                                  className={`text-xs truncate block ${
                                    isInSession
                                      ? "text-success font-medium"
                                      : isCompleted
                                      ? "text-foreground cursor-pointer"
                                      : "text-muted-foreground"
                                  }`}
                                >
                                  {doc.filename}
                                  {isInSession && " (Already added)"}
                                </label>
                                <div className="flex items-center gap-2 mt-0.5">
                                  <span className="text-xs text-muted-foreground">
                                    {doc.chunk_count || 0} chunks
                                  </span>
                                  {doc.status === "completed" ? (
                                    <CheckCircle className="w-3 h-3 text-success" />
                                  ) : doc.status === "processing" ? (
                                    <Clock className="w-3 h-3 text-warning" />
                                  ) : (
                                    <XCircle className="w-3 h-3 text-destructive" />
                                  )}
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

              {/* Actions */}
              <div className="flex gap-2 pt-2">
                <Button
                  size="sm"
                  onClick={handleAddDocuments}
                  disabled={docsToAdd.length === 0}
                  className="flex-1"
                >
                  Add {docsToAdd.length} Document
                  {docsToAdd.length !== 1 ? "s" : ""}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setShowDocumentManager(false);
                    setDocsToAdd([]);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
      {/* End: Sticky Header */}

      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto bg-background">
        {messages.length === 0 && !streamingMessage ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md">
              <div className="w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <FileText className="w-8 h-8 text-primary" />
              </div>
              <h3 className="text-lg font-medium text-foreground mb-2">
                Ready to chat!
              </h3>
              <p className="text-sm text-muted-foreground">
                {sessionDocIds.length > 0
                  ? `Ask questions about your ${
                      sessionDocIds.length
                    } selected document${sessionDocIds.length !== 1 ? "s" : ""}`
                  : "Add documents to start asking questions"}
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto py-6 px-4 space-y-6">
            {messages.map((msg, index) => {
              const isLastMessage = index === messages.length - 1;
              const isComparisonResponse =
                msg.role === "assistant" &&
                ((isLastMessage && comparison.isActive && comparison.context) ||
                  Boolean(msg.comparison_metadata));

              if (isComparisonResponse) {
                return (
                  <div
                    key={index}
                    className="flex justify-start animate-message-slide-left w-full"
                  >
                    <div className="w-full">
                      <ComparisonMessage
                        message={msg}
                        onOpenComparisonPanel={handleOpenComparisonPanel}
                      />
                    </div>
                  </div>
                );
              }

              return (
                <div
                  key={index}
                  className={`flex ${
                    msg.role === "user" ? "justify-end" : "justify-start"
                  } animate-message-slide-left`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-5 py-3 ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground"
                        : "bg-card border border-border"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm max-w-none dark:prose-invert
                        prose-table:border-collapse prose-table:w-full
                        prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                        prose-td:border prose-td:border-border prose-td:p-2
                        prose-tr:even:bg-muted/30
                        prose-p:text-muted-foreground prose-p:leading-relaxed
                        prose-strong:text-foreground prose-strong:font-semibold
                        prose-ul:text-muted-foreground prose-ul:my-3
                        prose-ol:text-muted-foreground prose-ol:my-3
                        prose-li:my-1
                        prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                        prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                        prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                        prose-pre:bg-muted prose-pre:border prose-pre:border-border
                        prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                        prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                        prose-headings:font-bold prose-headings:text-foreground
                      ">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="text-sm leading-relaxed whitespace-pre-wrap">
                        {msg.content}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Thinking indicator - shown during processing before streaming */}
            {isThinking && (
              <div className="flex justify-start animate-fade-in">
                <div className="max-w-[80%] rounded-2xl px-5 py-3 bg-card border border-border">
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm">Analyzing documents...</span>
                  </div>
                </div>
              </div>
            )}

            {isStreaming && streamingMessage && (
              <div className="flex justify-start animate-fade-in">
                <div className="max-w-[80%] rounded-2xl px-5 py-3 bg-card border border-border">
                  {comparison.isActive && comparison.context ? (
                    // Render streaming comparison message with markdown + styled citations
                    <div className="prose prose-sm max-w-none dark:prose-invert
                      prose-table:border-collapse prose-table:w-full
                      prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                      prose-td:border prose-td:border-border prose-td:p-2
                      prose-tr:even:bg-muted/30
                      prose-p:text-muted-foreground prose-p:leading-relaxed
                      prose-strong:text-foreground prose-strong:font-semibold
                      prose-ul:text-muted-foreground prose-ul:my-3
                      prose-ol:text-muted-foreground prose-ol:my-3
                      prose-li:my-1
                      prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                      prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                      prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                      prose-pre:bg-muted prose-pre:border prose-pre:border-border
                      prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                      prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                      prose-headings:font-bold prose-headings:text-foreground
                    ">
                      <StreamingComparisonContent content={streamingMessage} />
                    </div>
                  ) : (
                    // Regular streaming message (markdown)
                    <div className="prose prose-sm max-w-none dark:prose-invert
                      prose-table:border-collapse prose-table:w-full
                      prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2
                      prose-td:border prose-td:border-border prose-td:p-2
                      prose-tr:even:bg-muted/30
                      prose-p:text-muted-foreground prose-p:leading-relaxed
                      prose-strong:text-foreground prose-strong:font-semibold
                      prose-ul:text-muted-foreground prose-ul:my-3
                      prose-ol:text-muted-foreground prose-ol:my-3
                      prose-li:my-1
                      prose-a:text-primary prose-a:no-underline hover:prose-a:underline
                      prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
                      prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
                      prose-pre:bg-muted prose-pre:border prose-pre:border-border
                      prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
                      prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
                      prose-headings:font-bold prose-headings:text-foreground
                    ">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {streamingMessage}
                      </ReactMarkdown>
                    </div>
                  )}
                  {/* Typing indicator */}
                  <div className="flex items-center gap-1 mt-2">
                    <div className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot" />
                    <div
                      className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot"
                      style={{ animationDelay: "0.2s" }}
                    />
                    <div
                      className="w-1.5 h-1.5 bg-primary rounded-full animate-typing-dot"
                      style={{ animationDelay: "0.4s" }}
                    />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer - sticky at bottom of scroll pane */}
      <div className="sticky bottom-0 bg-card/90 backdrop-blur border-t border-border p-4">
        <div className="max-w-4xl mx-auto px-4">
          {chatError && (
            <div className="mb-3 p-3 bg-destructive/10 text-destructive rounded-lg text-sm border border-destructive/20">
              ⚠️ {chatError}
            </div>
          )}

          <form onSubmit={handleSendMessage} className="flex gap-3">
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={
                sessionDocIds.length === 0
                  ? "Add documents to start chatting..."
                  : "Ask a question about your documents..."
              }
              disabled={isStreaming || sessionDocIds.length === 0}
              className="flex-1 px-4 py-3 border border-input rounded-lg bg-background text-foreground placeholder:text-muted-foreground disabled:bg-muted disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-ring transition-all"
            />
            <Button
              type="submit"
              disabled={
                !message.trim() || isStreaming || sessionDocIds.length === 0
              }
              size="lg"
              className="min-w-[100px]"
            >
              {isStreaming ? (
                <>
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 mr-2" />
                  Send
                </>
              )}
            </Button>
          </form>

          {sessionDocIds.length === 0 && (
            <p className="text-xs text-muted-foreground mt-2 text-center">
              💡 Click "+ Add" above to select documents from your collections
            </p>
          )}
        </div>
      </div>
      {/* End: Outer flex container from line 254 */}
      </div>
      </ResizablePanel>

      {/* Resizable Handle - only show if PDF panel is visible */}
      {showPdfPanel && sessionDocIds.length > 0 && <ResizableHandle withHandle />}

      {/* Right Panel: PDF Viewer */}
      {showPdfPanel && sessionDocIds.length > 0 && (
        <ResizablePanel defaultSize={45} minSize={30} maxSize={65}>
          <div className="w-full h-full flex flex-col bg-background overflow-hidden">
            <div className="bg-card px-4 py-2 border-b flex-shrink-0">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <h2 className="font-medium text-sm text-foreground">
                    {activePdfUrl && pdfViewer.activeDocumentId
                      ? currentSession?.documents?.find(d => d.id === pdfViewer.activeDocumentId)?.name || "Document"
                      : "Document"}
                  </h2>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowPdfPanel(false)}
                  className="h-7 w-7"
                  title="Close PDF viewer"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-hidden">
              {pdfViewer.isLoadingUrl ? (
                <div className="flex flex-col items-center justify-center h-full gap-2">
                  <Spinner size="md" />
                  <p className="text-sm text-muted-foreground">Loading PDF...</p>
                </div>
              ) : activePdfUrl ? (
                <PDFViewer
                  pdfUrl={activePdfUrl}
                  highlightBbox={pdfViewer.highlightBbox}
                  onHighlightClick={clearHighlight}
                />
              ) : pdfViewer.activeDocumentId ? (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                  <FileText className="w-12 h-12 opacity-20" />
                  <p className="text-sm">Click a document chip to view PDF</p>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
                  <FileText className="w-12 h-12 opacity-20" />
                  <p className="text-sm">No document selected</p>
                </div>
              )}
            </div>
          </div>
        </ResizablePanel>
      )}

      {/* Comparison Panel Sheet */}
      <ComparisonPanel
        isOpen={showComparisonPanel}
        onClose={() => setShowComparisonPanel(false)}
      />
    </ResizablePanelGroup>
  );
}
