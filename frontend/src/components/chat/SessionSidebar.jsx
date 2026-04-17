/**
 * SessionSidebar Component - Redesigned
 *
 * ChatGPT-inspired session list with search and better density
 *
 * Input:
 *   - sessions: Array<{id, title, message_count, documents}>
 *   - currentSession: { id, title, documents, ... } | null
 *   - sessionsLoading: boolean
 *   - onNewChat: () => void
 *   - onSelectSession: (sessionId: string) => void
 *   - onDeleteSession: (sessionId: string) => void
 *   - onOpenDocumentManager: () => void
 *   - onOpenDocument: (documentId: string) => void
 *   - onRemoveDocument: (documentId: string) => void
 */

import { useState, useMemo, useEffect } from "react";
import { Plus, MessageSquare, FileText, Trash2, Search, ChevronLeft, ChevronDown, ChevronRight, Pencil, Check, X } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import Spinner from "../common/Spinner";
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
} from "../ui/alert-dialog";

export default function SessionSidebar({
  sessions = [],
  currentSession = null,
  sessionsLoading = false,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onUpdateSessionTitle,
  onOpenDocumentManager,
  onOpenDocument,
  onRemoveDocument,
  isCollapsed = false,
  onToggleCollapse,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editedTitle, setEditedTitle] = useState(currentSession?.title || "");
  const [docSearchQuery, setDocSearchQuery] = useState("");
  const [documentsCollapsed, setDocumentsCollapsed] = useState(false);

  useEffect(() => {
    setEditedTitle(currentSession?.title || "");
    setIsEditingTitle(false);
    setDocSearchQuery("");
    setDocumentsCollapsed((currentSession?.documents?.length || 0) > 4);
  }, [currentSession?.id]);

  // Filter sessions by search query
  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const query = searchQuery.toLowerCase();
    return sessions.filter((session) =>
      session.title?.toLowerCase().includes(query)
    );
  }, [sessions, searchQuery]);

  const sessionDocuments = currentSession?.documents || [];
  const filteredDocuments = useMemo(() => {
    if (!docSearchQuery.trim()) return sessionDocuments;
    const query = docSearchQuery.toLowerCase();
    return sessionDocuments.filter((doc) =>
      (doc.name || doc.filename || "").toLowerCase().includes(query)
    );
  }, [sessionDocuments, docSearchQuery]);

  // If collapsed, return null (sidebar width is 0 in parent)
  if (isCollapsed) {
    return null;
  }

  return (
    <div className="h-full flex min-h-0 flex-col px-4 py-4">
      <div className="shrink-0 space-y-3 border-b border-border/70 pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground">Sessions</h2>
            <p className="text-[11px] text-muted-foreground">
              {sessions.length} total
            </p>
          </div>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            className="h-8 w-8 rounded-lg shrink-0"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        </div>

        <Button onClick={onNewChat} className="h-9 w-full justify-start rounded-xl gap-2 px-3" size="default">
          <Plus className="w-4 h-4" />
          New Chat
        </Button>

        <div>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search sessions"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 rounded-xl border-border/70 bg-background/70 pl-8 text-xs"
            />
          </div>
          {searchQuery && (
            <p className="mt-2 text-xs text-muted-foreground">
              {filteredSessions.length} match{filteredSessions.length === 1 ? "" : "es"}
            </p>
          )}
        </div>

        {currentSession && (
          <div className="chat-section px-3 py-2.5">
            {isEditingTitle ? (
              <div className="flex items-center gap-1.5">
                <Input
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const next = editedTitle.trim();
                      if (next && onUpdateSessionTitle) {
                        onUpdateSessionTitle(next);
                      }
                      setIsEditingTitle(false);
                    } else if (e.key === "Escape") {
                      setEditedTitle(currentSession?.title || "");
                      setIsEditingTitle(false);
                    }
                  }}
                  autoFocus
                  className="h-8 rounded-xl border-border/70 bg-background/70 text-xs"
                  placeholder="Session title"
                />
                <button
                  onClick={() => {
                    const next = editedTitle.trim();
                    if (next && onUpdateSessionTitle) {
                      onUpdateSessionTitle(next);
                    }
                    setIsEditingTitle(false);
                  }}
                  className="rounded-full p-1 hover:bg-success/10"
                  title="Save"
                >
                  <Check className="w-3.5 h-3.5 text-success" />
                </button>
                <button
                  onClick={() => {
                    setEditedTitle(currentSession?.title || "");
                    setIsEditingTitle(false);
                  }}
                  className="rounded-full p-1 hover:bg-destructive/10"
                  title="Cancel"
                >
                  <X className="w-3.5 h-3.5 text-destructive" />
                </button>
              </div>
            ) : (
              <div
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 bg-primary/5 border border-primary/15 group cursor-default"
              >
                <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0" />
                <p className="truncate text-sm font-semibold text-foreground flex-1">
                  {currentSession.title || "Untitled Chat"}
                </p>
                <button
                  onClick={() => setIsEditingTitle(true)}
                  className="rounded-full p-1 opacity-0 group-hover:opacity-100 hover:bg-primary/10 transition-opacity flex-shrink-0"
                  title="Rename session"
                >
                  <Pencil className="w-3 h-3 text-primary" />
                </button>
              </div>
            )}
          </div>
        )}

        {currentSession && (
          <div className="chat-section px-3 py-2.5">
            <div className="mb-2 flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setDocumentsCollapsed((prev) => !prev)}
                className="flex min-w-0 flex-1 items-center gap-2 text-left"
                title={documentsCollapsed ? "Expand documents" : "Collapse documents"}
              >
                {documentsCollapsed ? (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                )}
                <FileText className="w-3.5 h-3.5 text-muted-foreground" />
                <span className="text-[11px] font-medium text-muted-foreground">
                  Documents
                </span>
                <span className="chat-meta-pill">{sessionDocuments.length}</span>
              </button>
              <div className="flex shrink-0 items-center gap-2">
                {onOpenDocumentManager && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onOpenDocumentManager}
                    className="h-7 rounded-lg px-2.5 text-[11px]"
                  >
                    Manage
                  </Button>
                )}
              </div>
            </div>

            {!documentsCollapsed && sessionDocuments.length > 0 && (
              <div className="relative mb-2">
                <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="Search docs"
                  value={docSearchQuery}
                  onChange={(e) => setDocSearchQuery(e.target.value)}
                  className="h-8 rounded-xl border-border/70 bg-background/70 pl-8 text-[11px]"
                />
              </div>
            )}

            {sessionDocuments.length === 0 ? (
              <div className="py-2 text-center text-xs text-muted-foreground">
                No documents in this session.
              </div>
            ) : documentsCollapsed ? (
              <div className="pr-1 py-1 text-xs leading-5 text-muted-foreground break-words">
                {sessionDocuments.length} document{sessionDocuments.length === 1 ? "" : "s"} attached to this session.
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="py-2 text-center text-xs text-muted-foreground">
                No documents match your search.
              </div>
            ) : (
              <div className="library-scrollbar max-h-52 space-y-1 overflow-y-auto pr-1">
                {filteredDocuments.map((doc) => {
                  const docName = doc.name || doc.filename || "Untitled";
                  const rawPageCount = doc.page_count ?? doc.pages ?? doc.num_pages ?? doc.metadata?.pages;
                  const pageCount = Number(rawPageCount);
                  const pageLabel =
                    Number.isFinite(pageCount) && pageCount > 0
                      ? `${pageCount} pages`
                      : "Pages n/a";
                  return (
                    <div
                      key={doc.id}
                      className="group flex items-center justify-between gap-2 rounded-xl border border-border/60 px-2.5 py-2 transition-colors hover:bg-muted/40"
                    >
                      <button
                        type="button"
                        onClick={() => onOpenDocument?.(doc.id)}
                        className="min-w-0 flex-1 text-left"
                        title="Open document"
                      >
                        <p className="truncate text-xs font-medium text-foreground">
                          {docName}
                        </p>
                        <p className="truncate text-[10px] text-muted-foreground">
                          {pageLabel}
                        </p>
                      </button>
                      {onRemoveDocument && (
                        <button
                          onClick={() => onRemoveDocument(doc.id)}
                          className="p-1 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                          title="Remove document"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="library-scrollbar mt-3 flex-1 overflow-y-auto pr-1">
        {sessionsLoading ? (
          <div className="p-4 flex items-center justify-center">
            <Spinner size="sm" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-6 text-center">
            <MessageSquare className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
            <p className="text-sm text-muted-foreground">
              {searchQuery ? "No matches found" : "No chat sessions yet"}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {searchQuery
                ? "Try a different search"
                : 'Click "New Chat" to start'}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {filteredSessions.map((session) => {
              const isActive = currentSession?.id === session.id;
              const documentCount = session.document_count || 0;

              return (
                <div
                  key={session.id}
                  className={`chat-sidebar-item group ${
                    isActive ? "chat-sidebar-item-active" : ""
                  }`}
                >
                  <button
                    onClick={() => onSelectSession(session.id)}
                    className="w-full pr-9 text-left"
                  >
                    <div className="flex items-start gap-2.5">
                      <MessageSquare className={`mt-0.5 h-4 w-4 shrink-0 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                      <div className="flex-1 min-w-0">
                        <div
                          className={`mb-1 truncate text-sm font-medium ${
                            isActive ? "text-foreground" : "text-foreground"
                          }`}
                        >
                          {session.title || "Untitled Chat"}
                        </div>

                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <div className="chat-meta-pill">
                            <MessageSquare className="w-3 h-3" />
                            <span>{session.message_count || 0}</span>
                          </div>
                          <div className="chat-meta-pill">
                            <FileText className="w-3 h-3" />
                            <span>{documentCount}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </button>

                  <div className="absolute right-2 top-2.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
                          title="Delete session"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            Delete Chat Session?
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete "
                            {session.title || "Untitled Chat"}" and all its
                            messages. This action cannot be undone.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => onDeleteSession?.(session.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
}
