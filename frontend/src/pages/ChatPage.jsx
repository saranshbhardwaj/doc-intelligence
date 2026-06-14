/**
 * Chat Page (Session-Centric)
 *
 * Main chat interface with session-based architecture.
 * Features:
 * - Session sidebar with list of chats
 * - Empty state for creating new sessions with documents
 * - Active chat interface with document chips
 * - Document management (add/remove from session)
 * - Export chat sessions
 */

import { useEffect, useState } from "react";
import { useAppAuth } from "@/hooks/useAppAuth";
import { ChevronRight, PanelLeft, MessageSquare, Plus } from "lucide-react";
import { useChat, useChatActions } from "../store";
import { Button } from "../components/ui/button";
import AppLayout from "../components/layout/AppLayout";
import SessionSidebar from "../components/chat/SessionSidebar";
import EmptyState from "../components/chat/EmptyState";
import ActiveChat from "../components/chat/ActiveChat";
import DocumentManagerDialog from "../components/chat/DocumentManagerDialog";
import Spinner from "../components/common/Spinner";
import { exportAsMarkdown, exportAsWord } from "../utils/exportChat";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "../components/ui/sheet";
import { ChatPageSkeleton } from "../components/skeletons/PageSkeletons";

export default function ChatPage() {
  const { getToken, isLoaded } = useAppAuth();
  const chat = useChat();
  const actions = useChatActions();

  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [showNewChatDialog, setShowNewChatDialog] = useState(false);
  const [mobileSessionsOpen, setMobileSessionsOpen] = useState(false);
  const [documentManagerOpen, setDocumentManagerOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem("chatSidebarCollapsed") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    // Wait for Clerk to initialize
    if (!isLoaded) return;

    // Fetch initial data
    (async () => {
      await Promise.all([
        actions.fetchSessions(getToken),
        actions.fetchCollections(getToken),
      ]);

      // Auto-reopen last active session if present
      const lastSessionId = localStorage.getItem("lastActiveChatSessionId");
      if (lastSessionId) {
        try {
          await actions.loadSession(getToken, lastSessionId);
        } catch (e) {
          console.warn("Failed to auto-load last session:", e);
          localStorage.removeItem("lastActiveChatSessionId");
        }
      }
      setIsInitializing(false);
    })();
  }, [isLoaded, actions, getToken]);

  // Auto-open dialog when there's no active session after init
  useEffect(() => {
    if (!isInitializing && !chat.currentSession) {
      setShowNewChatDialog(true);
    }
  }, [isInitializing]);

  const handleNewChat = () => {
    setShowNewChatDialog(true);
  };

  const handleSelectSession = async (sessionId) => {
    await actions.loadSession(getToken, sessionId);
    setMobileSessionsOpen(false);
    try {
      localStorage.setItem("lastActiveChatSessionId", sessionId);
    } catch { /* ignore localStorage errors */ }
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await actions.deleteSession(getToken, sessionId);

      // If deleted session was active, clear it
      if (chat.currentSession?.id === sessionId) {
        actions.startNewChat();
        try {
          const saved = localStorage.getItem("lastActiveChatSessionId");
          if (saved === String(sessionId)) {
            localStorage.removeItem("lastActiveChatSessionId");
          }
        } catch { /* ignore localStorage errors */ }
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const handleStartChat = async (documentIds, title) => {
    if (isCreatingSession) return;
    setIsCreatingSession(true);
    try {
      // Create new session with selected documents
      const session = await actions.createNewSession(getToken, {
        title: title || "New Chat",
        documentIds,
      });
      setShowNewChatDialog(false);
      setSelectedDocuments([]);
      if (session?.id) {
        try {
          localStorage.setItem("lastActiveChatSessionId", session.id);
        } catch { /* ignore localStorage errors */ }
      }
    } catch (error) {
      console.error("Failed to create session:", error);
    } finally {
      setIsCreatingSession(false);
    }
  };

  const handleSendMessage = async (message) => {
    await actions.sendMessage(getToken, message);
  };

  const handleAddDocuments = async (documentIds) => {
    await actions.addDocumentsToCurrentSession(getToken, documentIds);
    // State is already updated in the slice action - no need to fetch
  };

  const handleRemoveDocument = async (documentId) => {
    await actions.removeDocumentFromCurrentSession(getToken, documentId);
    // State is already updated in the slice action - no need to fetch
  };

  const handleOpenDocument = (documentId) => {
    actions.setActivePdfDocument(documentId, getToken);
  };

  const handleUpdateSessionTitle = async (title) => {
    if (!chat.currentSession) return;
    await actions.updateSessionTitle(getToken, chat.currentSession.id, title);
    // State is already updated in the slice action - no need to fetch
  };

  const handleExportSession = async (format = "markdown") => {
    if (!chat.currentSession) return;

    try {
      // Fetch export data from API
      const exportData = await actions.exportSession(
        getToken,
        chat.currentSession.id
      );

      // Export based on selected format
      if (format === "word") {
        await exportAsWord(exportData);
      } else {
        await exportAsMarkdown(exportData);
      }
    } catch (error) {
      console.error("Failed to export session:", error);
      alert(`Export failed: ${error.message || "Unknown error"}`);
    }
  };

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const newValue = !prev;
      try {
        localStorage.setItem("chatSidebarCollapsed", String(newValue));
      } catch { /* ignore localStorage errors */ }
      return newValue;
    });
  };

  // Loading state
  if (!isLoaded) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-screen">
          <Spinner />
        </div>
      </AppLayout>
    );
  }

  if (isInitializing) {
    return (
      <AppLayout lockViewport suppressPageHeader>
        <ChatPageSkeleton />
      </AppLayout>
    );
  }

  return (
    <AppLayout lockViewport suppressPageHeader>
      <div className="relative flex h-full min-h-0 gap-3 px-3 pb-3 pt-2 md:px-4 md:pb-4 md:pt-3">
        {/* Mobile sessions drawer trigger */}
        <div className="absolute left-3 top-3 z-40 md:hidden">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setMobileSessionsOpen(true)}
            className="h-8 px-2.5 bg-card/95 backdrop-blur"
            title="Open sessions"
          >
            <PanelLeft className="h-4 w-4 mr-1.5" />
            Sessions
          </Button>
        </div>

        {/* Mobile sessions drawer */}
        <Sheet open={mobileSessionsOpen} onOpenChange={setMobileSessionsOpen}>
          <SheetContent side="left" className="w-[88vw] max-w-sm p-0">
            <SheetTitle className="sr-only">Chat Sessions</SheetTitle>
            <SheetDescription className="sr-only">
              Browse, search, create, and delete chat sessions.
            </SheetDescription>
            <div className="chat-shell h-full pt-6">
              <SessionSidebar
                sessions={chat.sessions}
                currentSession={chat.currentSession}
                sessionsLoading={chat.sessionsLoading}
                onNewChat={handleNewChat}
                onSelectSession={handleSelectSession}
                onDeleteSession={handleDeleteSession}
                onUpdateSessionTitle={handleUpdateSessionTitle}
                onOpenDocumentManager={() => setDocumentManagerOpen(true)}
                onOpenDocument={handleOpenDocument}
                onRemoveDocument={handleRemoveDocument}
                isCollapsed={false}
                onToggleCollapse={() => setMobileSessionsOpen(false)}
              />
            </div>
          </SheetContent>
        </Sheet>

        {/* Left: Session Sidebar (scrollable, collapsible) */}
        <div
          className={`hidden md:flex h-full flex-shrink-0 overflow-hidden transition-all duration-300 ${
            sidebarCollapsed ? "w-0" : "w-[18rem]"
          }`}
        >
          <div className="chat-shell panel-shell h-full w-full">
            <SessionSidebar
              sessions={chat.sessions}
              currentSession={chat.currentSession}
              sessionsLoading={chat.sessionsLoading}
              onNewChat={handleNewChat}
              onSelectSession={handleSelectSession}
              onDeleteSession={handleDeleteSession}
              onUpdateSessionTitle={handleUpdateSessionTitle}
              onOpenDocumentManager={() => setDocumentManagerOpen(true)}
              onOpenDocument={handleOpenDocument}
              onRemoveDocument={handleRemoveDocument}
              isCollapsed={sidebarCollapsed}
              onToggleCollapse={toggleSidebar}
            />
          </div>
        </div>

        {/* Expand Button (shown when sidebar is collapsed) */}
        {sidebarCollapsed && (
          <div className="absolute left-0 top-0 z-50 hidden md:block">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="h-9 w-9 rounded-r-xl rounded-l-none border border-l-0 bg-card shadow-md hover:bg-muted hover:shadow-lg"
              title="Expand sidebar"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Right: Main Chat Area */}
        <div className="min-h-0 min-w-0 flex-1 overflow-hidden pt-11 md:pt-0">
          {isInitializing ? (
            <div className="flex items-center justify-center h-full">
              <Spinner />
            </div>
          ) : !chat.currentSession ? (
            /* No active session placeholder — dialog opens automatically */
            <div className="flex flex-col items-center justify-center h-full gap-4 text-center px-4">
              <div className="w-16 h-16 glass-card rounded-2xl flex items-center justify-center">
                <MessageSquare className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h3 className="font-display text-lg font-semibold text-foreground">No active session</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Select a session from the sidebar or start a new chat
                </p>
              </div>
              <Button onClick={() => setShowNewChatDialog(true)} className="gap-2">
                <Plus className="w-4 h-4" />
                New Chat
              </Button>
            </div>
          ) : (
            /* Active Chat */
            <ActiveChat
              currentSession={chat.currentSession}
              messages={chat.messages}
              isStreaming={chat.isStreaming}
              isThinking={chat.isThinking}
              thinkingMessage={chat.thinkingMessage}
              streamingMessage={chat.streamingMessage}
              chatError={chat.chatError}
              collections={chat.collections}
              getToken={getToken}
              onSendMessage={handleSendMessage}
              onAddDocuments={handleAddDocuments}
              onRemoveDocument={handleRemoveDocument}
              onUpdateSessionTitle={handleUpdateSessionTitle}
              onExportSession={handleExportSession}
            />
          )}
        </div>
      </div>

      {/* New Chat Dialog — always mounted, dialog controls visibility */}
      <EmptyState
        open={showNewChatDialog}
        onOpenChange={setShowNewChatDialog}
        collections={chat.collections}
        collectionsLoading={chat.collectionsLoading}
        selectedDocumentIds={selectedDocuments}
        onSelectDocuments={setSelectedDocuments}
        onStartChat={handleStartChat}
        isCreating={isCreatingSession}
        getToken={getToken}
      />

      <DocumentManagerDialog
        open={documentManagerOpen}
        onOpenChange={setDocumentManagerOpen}
        collections={chat.collections}
        currentSessionDocuments={chat.currentSession?.documents || []}
        getToken={getToken}
        onAddDocuments={handleAddDocuments}
        onRemoveDocument={handleRemoveDocument}
      />
    </AppLayout>
  );
}
