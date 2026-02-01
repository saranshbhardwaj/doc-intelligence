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
 */

import { useState, useMemo } from "react";
import { Plus, MessageSquare, FileText, Trash2, Search, ChevronLeft, ChevronRight } from "lucide-react";
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
  isCollapsed = false,
  onToggleCollapse,
}) {
  const [searchQuery, setSearchQuery] = useState("");

  // Filter sessions by search query
  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const query = searchQuery.toLowerCase();
    return sessions.filter((session) =>
      session.title?.toLowerCase().includes(query)
    );
  }, [sessions, searchQuery]);

  // If collapsed, return null (sidebar width is 0 in parent)
  if (isCollapsed) {
    return null;
  }

  return (
    <Card className="p-3 h-full flex flex-col">
      {/* Header with Collapse Button and New Chat Button */}
      <div className="mb-2 space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm text-foreground">Sessions</h2>
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
        <Button onClick={onNewChat} className="w-full h-9" size="default">
          <Plus className="w-4 h-4 mr-2" />
          New Chat
        </Button>
      </div>

      {/* Search */}
      <div className="mb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search sessions..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-sm"
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
                  className={`group relative rounded-lg transition-all ${
                    isActive
                      ? "bg-primary/10 border border-primary/30"
                      : "hover:bg-muted/70"
                  }`}
                >
                  <button
                    onClick={() => onSelectSession(session.id)}
                    className="w-full text-left p-2 pr-9 rounded-lg"
                  >
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
                      {/* Message Count */}
                      <div className="flex items-center gap-1">
                        <MessageSquare className="w-3 h-3" />
                        <span>{session.message_count || 0}</span>
                      </div>

                      {/* Document Count */}
                      <div className="flex items-center gap-1">
                        <FileText className="w-3 h-3" />
                        <span>{documentCount}</span>
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
