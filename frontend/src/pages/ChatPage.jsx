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
import { useAuth } from "@clerk/clerk-react";
import { useChat, useChatActions } from "../store";
import AppLayout from "../components/layout/AppLayout";
import SessionSidebar from "../components/chat/SessionSidebar";
import EmptyState from "../components/chat/EmptyState";
import ActiveChat from "../components/chat/ActiveChat";
import Spinner from "../components/common/Spinner";
import { exportAsMarkdown, exportAsWord } from "../utils/exportChat";

export default function ChatPage() {
  const { getToken, isLoaded } = useAuth();
  const chat = useChat();
  const actions = useChatActions();

  const [selectedDocuments, setSelectedDocuments] = useState([]);
  const [isInitializing, setIsInitializing] = useState(true);

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

  const handleNewChat = () => {
    // Clear current session and show empty state
    actions.startNewChat();
    setSelectedDocuments([]);
    try {
      localStorage.removeItem("lastActiveChatSessionId");
    } catch {}
  };

  const handleSelectSession = async (sessionId) => {
    await actions.loadSession(getToken, sessionId);
    try {
      localStorage.setItem("lastActiveChatSessionId", sessionId);
    } catch {}
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
        } catch {}
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const handleStartChat = async (documentIds) => {
    try {
      // Create new session with selected documents
      const session = await actions.createNewSession(getToken, {
        title: "New Chat",
        documentIds,
      });
      setSelectedDocuments([]);
      if (session?.id) {
        try {
          localStorage.setItem("lastActiveChatSessionId", session.id);
        } catch {}
      }
    } catch (error) {
      console.error("Failed to create session:", error);
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
        console.log("✅ Exported as Word document");
      } else {
        await exportAsMarkdown(exportData);
        console.log("✅ Exported as Markdown");
      }
    } catch (error) {
      console.error("Failed to export session:", error);
      alert(`Export failed: ${error.message || "Unknown error"}`);
    }
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

  const breadcrumbs = [{ label: "Chat" }];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      {/* Full-height two-pane layout with independent scroll */}
      <div className="h-[calc(100vh-64px)] flex gap-4">
        {/* Left: Session Sidebar (scrollable) */}
        <div className="w-80 flex-shrink-0 overflow-y-auto scrollbar-thin">
          <SessionSidebar
            sessions={chat.sessions}
            currentSession={chat.currentSession}
            sessionsLoading={chat.sessionsLoading}
            onNewChat={handleNewChat}
            onSelectSession={handleSelectSession}
            onDeleteSession={handleDeleteSession}
          />
        </div>

        {/* Right: Main Chat Area (scrollable pane) */}
        <div className="flex-1 min-w-0 overflow-y-auto scrollbar-chat">
          {isInitializing ? (
            <div className="flex items-center justify-center h-full">
              <Spinner />
            </div>
          ) : !chat.currentSession ? (
            /* Empty State - No Active Session */
            <EmptyState
              collections={chat.collections}
              collectionsLoading={chat.collectionsLoading}
              selectedDocumentIds={selectedDocuments}
              onSelectDocuments={setSelectedDocuments}
              onStartChat={handleStartChat}
              getToken={getToken}
            />
          ) : (
            /* Active Chat */
            <ActiveChat
              currentSession={chat.currentSession}
              messages={chat.messages}
              isStreaming={chat.isStreaming}
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
    </AppLayout>
  );
}
