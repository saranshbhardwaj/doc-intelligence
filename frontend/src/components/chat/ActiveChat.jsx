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

export default function ActiveChat({
  currentSession,
  messages = [],
  isStreaming = false,
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

  return (
    <div className="flex-1 flex flex-col h-full">
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
                  className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-muted rounded transition-all"
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
              {currentSession?.documents?.map((doc, index) => (
                <div
                  key={doc.id}
                  className="group flex items-center gap-1.5 px-2.5 py-1 bg-primary/10 text-primary rounded-full text-xs font-medium transition-all hover:bg-primary/20 animate-chip-fade-in"
                  style={{ animationDelay: `${index * 30}ms` }}
                >
                  <FileText className="w-3 h-3" />
                  <span className="max-w-[120px] truncate">{doc.name}</span>
                  <button
                    onClick={() => onRemoveDocument?.(doc.id)}
                    className="opacity-0 group-hover:opacity-100 transition-opacity hover:text-destructive ml-0.5"
                    title="Remove document"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
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
          <div className="mt-4 p-4 bg-muted/50 rounded-lg border border-border animate-fade-in">
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

      {/* Messages Area - ChatGPT-inspired centered layout (scrollable) */}
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
            {messages.map((msg, index) => (
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
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </div>
                  {msg.source_chunks && msg.source_chunks.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-border/30 opacity-70">
                      <p className="text-xs">
                        📚 Sources: {msg.num_chunks_retrieved} chunks used
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {isStreaming && streamingMessage && (
              <div className="flex justify-start animate-fade-in">
                <div className="max-w-[80%] rounded-2xl px-5 py-3 bg-card border border-border">
                  <div className="text-sm leading-relaxed whitespace-pre-wrap">
                    {streamingMessage}
                  </div>
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
                  <Spinner size="sm" className="mr-2" />
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
    </div>
  );
}
