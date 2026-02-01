/**
 * Session actions
 */
import * as chatApi from "../../../api/chat";
import { getErrorMessage } from "./utils";

export const createChatSessionActions = (set, get) => ({
  createNewSession: async (getToken, { title, documentIds }) => {
    try {
      const session = await chatApi.createSession(getToken, {
        title: title || "New Chat",
        description: null,
        documentIds: documentIds || [],
      });

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: session,
          messages: [],
          chatError: null,
        },
      }));

      set((state) => ({
        chat: {
          ...state.chat,
          sessions: [session, ...state.chat.sessions],
        },
      }));

      return session;
    } catch (error) {
      console.error("Failed to create session:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
      throw error;
    }
  },

  loadSession: async (getToken, sessionId) => {
    try {
      const session = await chatApi.getSession(getToken, sessionId);
      const historyData = await chatApi.getChatHistory(getToken, sessionId);

      const lastAssistant = historyData.messages
        .filter((m) => m.role === "assistant")
        .pop();

      const comparisonContext = lastAssistant?.comparison_metadata || null;

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: session,
          messages: historyData.messages,
          chatError: null,
          comparison: comparisonContext
            ? {
                isActive: true,
                context: comparisonContext,
                viewMode: state.chat.comparison?.viewMode || "cards",
                selectedPairIndex: null,
                expandedTopics: [],
              }
            : {
                isActive: false,
                context: null,
                viewMode: state.chat.comparison?.viewMode || "cards",
                selectedPairIndex: null,
                expandedTopics: [],
              },
        },
      }));
    } catch (error) {
      console.error("Failed to load session:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
    }
  },

  addDocumentsToCurrentSession: async (getToken, documentIds) => {
    const sessionId = get().chat.currentSession?.id;
    if (!sessionId) {
      console.error("No active session");
      return;
    }

    try {
      await chatApi.addDocumentsToSession(getToken, sessionId, documentIds);
      const updatedSession = await chatApi.getSession(getToken, sessionId);

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: updatedSession,
          sessions: state.chat.sessions.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  documents: updatedSession.documents,
                  document_count: updatedSession.documents.length,
                }
              : s
          ),
        },
      }));
    } catch (error) {
      console.error("Failed to add documents to session:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
    }
  },

  removeDocumentFromCurrentSession: async (getToken, documentId) => {
    const sessionId = get().chat.currentSession?.id;
    if (!sessionId) {
      console.error("No active session");
      return;
    }

    try {
      await chatApi.removeDocumentFromSession(getToken, sessionId, documentId);

      set((state) => {
        const updatedDocuments = state.chat.currentSession.documents.filter(
          (doc) => doc.id !== documentId
        );

        return {
          chat: {
            ...state.chat,
            currentSession: {
              ...state.chat.currentSession,
              documents: updatedDocuments,
              document_count: updatedDocuments.length,
            },
            sessions: state.chat.sessions.map((s) =>
              s.id === sessionId
                ? {
                    ...s,
                    documents: updatedDocuments,
                    document_count: updatedDocuments.length,
                  }
                : s
            ),
          },
        };
      });
    } catch (error) {
      console.error("Failed to remove document from session:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
    }
  },

  updateSessionTitle: async (getToken, sessionId, title) => {
    try {
      await chatApi.updateSession(getToken, sessionId, { title });

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: {
            ...state.chat.currentSession,
            title,
          },
          sessions: state.chat.sessions.map((s) =>
            s.id === sessionId ? { ...s, title } : s
          ),
        },
      }));
    } catch (error) {
      console.error("Failed to update session title:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
    }
  },

  fetchSessions: async (getToken, options = {}) => {
    set((state) => ({
      chat: {
        ...state.chat,
        sessionsLoading: true,
      },
    }));

    try {
      const data = await chatApi.listSessions(getToken, options);
      set((state) => ({
        chat: {
          ...state.chat,
          sessions: data,
          sessionsLoading: false,
        },
      }));
    } catch (error) {
      console.error("Failed to fetch sessions:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          sessionsLoading: false,
        },
      }));
    }
  },

  deleteSession: async (getToken, sessionId) => {
    try {
      await chatApi.deleteSession(getToken, sessionId);

      set((state) => ({
        chat: {
          ...state.chat,
          sessions: state.chat.sessions.filter((s) => s.id !== sessionId),
          currentSession:
            state.chat.currentSession?.id === sessionId
              ? null
              : state.chat.currentSession,
          messages:
            state.chat.currentSession?.id === sessionId
              ? []
              : state.chat.messages,
        },
      }));
    } catch (error) {
      console.error("Failed to delete session:", error);
      throw error;
    }
  },

  exportSession: async (getToken, sessionId) => {
    try {
      const data = await chatApi.exportSession(getToken, sessionId);
      return data;
    } catch (error) {
      console.error("Failed to export session:", error);
      throw error;
    }
  },

  startNewChat: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        currentSession: null,
        messages: [],
        isStreaming: false,
        streamingMessage: "",
        chatError: null,
      },
    }));
  },
});
