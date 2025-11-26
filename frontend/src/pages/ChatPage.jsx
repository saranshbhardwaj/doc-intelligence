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

export default function ChatPage() {
  const { getToken, isLoaded } = useAuth();
  const chat = useChat();
  const actions = useChatActions();

  const [selectedDocuments, setSelectedDocuments] = useState([]);

  useEffect(() => {
    // Wait for Clerk to initialize
    if (!isLoaded) return;

    // Fetch initial data
    actions.fetchSessions(getToken);
    actions.fetchCollections(getToken);
  }, [isLoaded, actions, getToken]);

  const handleNewChat = () => {
    // Clear current session and show empty state
    actions.startNewChat();
    setSelectedDocuments([]);
  };

  const handleSelectSession = async (sessionId) => {
    await actions.loadSession(getToken, sessionId);
  };

  const handleDeleteSession = async (sessionId) => {
    try {
      await actions.deleteSession(getToken, sessionId);

      // If deleted session was active, clear it
      if (chat.currentSession?.id === sessionId) {
        actions.startNewChat();
      }
    } catch (error) {
      console.error("Failed to delete session:", error);
    }
  };

  const handleStartChat = async (documentIds) => {
    try {
      // Create new session with selected documents
      await actions.createNewSession(getToken, {
        title: "New Chat",
        documentIds,
      });
      setSelectedDocuments([]);
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

  const handleExportSession = async () => {
    if (!chat.currentSession) return;

    try {
      const exportData = await actions.exportSession(
        getToken,
        chat.currentSession.id
      );

      // Convert to markdown format
      let markdown = `# ${exportData.session.title}\n\n`;
      markdown += `**Date:** ${new Date(
        exportData.session.created_at
      ).toLocaleString()}\n\n`;
      markdown += `---\n\n`;

      exportData.messages.forEach((msg) => {
        const role = msg.role === "user" ? "You" : "Assistant";
        markdown += `### ${role}\n\n${msg.content}\n\n`;

        if (msg.source_chunks && msg.source_chunks.length > 0) {
          markdown += `*Sources: ${msg.num_chunks_retrieved} chunks*\n\n`;
        }
      });

      // Download as markdown file
      const blob = new Blob([markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `chat-${exportData.session.title
        .replace(/[^a-z0-9]/gi, "-")
        .toLowerCase()}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to export session:", error);
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
      <div className="flex flex-1 bg-background overflow-hidden">
        {/* Session Sidebar */}
        <SessionSidebar
          sessions={chat.sessions}
          currentSession={chat.currentSession}
          sessionsLoading={chat.sessionsLoading}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
        />

        {/* Main Chat Area */}
        {!chat.currentSession ? (
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
    </AppLayout>
  );
}
