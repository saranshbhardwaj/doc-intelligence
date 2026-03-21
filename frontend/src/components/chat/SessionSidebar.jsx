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
import { Plus, MessageSquare, FileText, Trash2, Search, ChevronLeft, Pencil, Check, X } from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
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

  useEffect(() => {
    setEditedTitle(currentSession?.title || "");
    setIsEditingTitle(false);
    setDocSearchQuery("");
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
    <Card className="p-3 h-full flex flex-col">
      {/* Header with Collapse Button and New Chat Button */}
      <div className="mb-2 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Sessions</h2>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleCollapse}
            className="h-7 w-7"
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
        </div>
        <Button onClick={onNewChat} className="w-full h-9 rounded-xl gap-2" size="default">
          <Plus className="w-4 h-4" />
          New Chat
        </Button>
      </div>

      {currentSession && (
        <div className="mb-2 rounded-xl border border-border/60 bg-muted/30 px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">
            Active Session
          </div>
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
                className="h-7 text-xs"
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
                className="p-1 rounded hover:bg-success/10"
                title="Save"
              >
                <Check className="w-3.5 h-3.5 text-success" />
              </button>
              <button
                onClick={() => {
                  setEditedTitle(currentSession?.title || "");
                  setIsEditingTitle(false);
                }}
                className="p-1 rounded hover:bg-destructive/10"
                title="Cancel"
              >
                <X className="w-3.5 h-3.5 text-destructive" />
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold text-foreground truncate">
                {currentSession.title || "Untitled Chat"}
              </p>
              <button
                onClick={() => setIsEditingTitle(true)}
                className="p-1 rounded hover:bg-muted"
                title="Edit title"
              >
                <Pencil className="w-3.5 h-3.5 text-muted-foreground" />
              </button>
            </div>
          )}
        </div>
      )}

      {currentSession && (
        <div className="mb-3 rounded-xl border border-border/60 bg-primary/5 px-2.5 py-2">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <FileText className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
                Documents
              </span>
              <span className="text-[11px] text-muted-foreground">
                {sessionDocuments.length}
              </span>
            </div>
            {onOpenDocumentManager && (
              <Button
                variant="outline"
                size="sm"
                onClick={onOpenDocumentManager}
                className="h-6 px-2 text-[11px]"
              >
                Manage
              </Button>
            )}
          </div>

          {sessionDocuments.length > 0 && (
            <div className="relative mb-2">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search docs..."
                value={docSearchQuery}
                onChange={(e) => setDocSearchQuery(e.target.value)}
                className="pl-8 h-7 text-[11px]"
              />
            </div>
          )}

          {sessionDocuments.length === 0 ? (
            <div className="text-xs text-muted-foreground py-2 text-center">
              No documents in this session.
            </div>
          ) : filteredDocuments.length === 0 ? (
            <div className="text-xs text-muted-foreground py-2 text-center">
              No documents match your search.
            </div>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto library-scrollbar pr-1">
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
                    className="group flex items-center justify-between gap-2 rounded-lg border border-border/60 px-2.5 py-2 hover:bg-muted/40 transition-colors"
                  >
                    <button
                      type="button"
                      onClick={() => onOpenDocument?.(doc.id)}
                      className="flex-1 min-w-0 text-left"
                      title="Open document"
                    >
                      <p className="text-xs font-medium text-foreground truncate">
                        {docName}
                      </p>
                      <p className="text-[10px] text-muted-foreground truncate">
                        {pageLabel}
                      </p>
                    </button>
                    {onRemoveDocument && (
                      <button
                        onClick={() => onRemoveDocument(doc.id)}
                        className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive p-1"
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

      {/* Search */}
      <div className="mb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search sessions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-xs"
          />
        </div>
        {searchQuery && (
          <p className="text-xs text-muted-foreground mt-2">
            {filteredSessions.length} of {sessions.length} sessions
          </p>
        )}
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto library-scrollbar">
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
          <div className="p-1 space-y-1">
            {filteredSessions.map((session) => {
              const isActive = currentSession?.id === session.id;
              const documentCount = session.document_count || 0;

              return (
                <div
                  key={session.id}
                  className={`group relative rounded-xl transition-all ${
                    isActive
                      ? "bg-primary/10"
                      : "hover:bg-muted/50"
                  }`}
                >
                  <button
                    onClick={() => onSelectSession(session.id)}
                    className="w-full text-left px-3 py-2.5 pr-9 rounded-xl"
                  >
                    <div className="flex items-start gap-2.5">
                      <MessageSquare className={`w-4 h-4 shrink-0 mt-0.5 ${isActive ? "text-primary" : "text-muted-foreground"}`} />
                      <div className="flex-1 min-w-0">
                        {/* Session Title */}
                        <div
                          className={`font-medium text-sm truncate mb-1 ${
                            isActive ? "text-primary" : "text-foreground"
                          }`}
                        >
                          {session.title || "Untitled Chat"}
                        </div>

                        {/* Session Metadata */}
                        <div className="flex items-center gap-2.5 text-xs text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <MessageSquare className="w-3 h-3" />
                            <span>{session.message_count || 0}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <FileText className="w-3 h-3" />
                            <span>{documentCount}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </button>

                  {/* Delete Button */}
                  <div className="absolute right-2 top-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="p-1.5 rounded hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
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

      {/* Footer */}
      <div className="border-t border-border pt-3 mt-3">
        <div className="text-xs text-muted-foreground text-center">
          {sessions.length} {sessions.length === 1 ? "session" : "sessions"}
        </div>
      </div>
    </Card>
  );
}
