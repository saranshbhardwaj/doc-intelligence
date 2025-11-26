/**
 * Chat Slice for Zustand Store
 *
 * Session-centric architecture:
 * - Collections are folders for browsing documents
 * - Sessions are independent and maintain their own document selection
 * - Chat happens within sessions, not directly with collections
 */

import * as chatApi from "../../api/chat";

/**
 * Get safe error message from error object
 * (Normalized errors from apiErrorHandler have .message)
 */
const getErrorMessage = (error) => {
  return error?.message || "An unexpected error occurred";
};

export const createChatSlice = (set, get) => ({
  chat: {
    // Collections (for document browsing only)
    collections: [],
    collectionsLoading: false,
    collectionsError: null,

    // Current collection (for document browsing)
    currentCollection: null,
    collectionLoading: false,
    collectionError: null,

    // Document upload
    uploadProgress: 0,
    uploadStatus: null, // 'uploading', 'indexing', 'completed', 'failed'
    uploadError: null,
    currentJobId: null,

    // Current session (with documents)
    currentSession: null, // { id, title, description, documents: [{id, name, added_at}, ...] }
    messages: [],
    isStreaming: false,
    streamingMessage: "",
    chatError: null,

    // Sessions list
    sessions: [],
    sessionsLoading: false,
  },

  /**
   * Collections Actions
   */

  fetchCollections: async (getToken) => {
    set((state) => ({
      chat: {
        ...state.chat,
        collectionsLoading: true,
        collectionsError: null,
      },
    }));

    try {
      const data = await chatApi.listCollections(getToken);
      set((state) => ({
        chat: {
          ...state.chat,
          collections: data.collections,
          collectionsLoading: false,
        },
      }));
    } catch (error) {
      console.error("Failed to fetch collections:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          collectionsLoading: false,
          collectionsError: getErrorMessage(error),
        },
      }));
    }
  },

  createCollection: async (getToken, { name, description }) => {
    try {
      const collection = await chatApi.createCollection(getToken, {
        name,
        description,
      });

      // Add to collections list
      set((state) => ({
        chat: {
          ...state.chat,
          collections: [collection, ...state.chat.collections],
        },
      }));

      return collection;
    } catch (error) {
      console.error("Failed to create collection:", error);
      throw error;
    }
  },

  selectCollection: async (getToken, collectionId) => {
    set((state) => ({
      chat: {
        ...state.chat,
        collectionLoading: true,
        collectionError: null,
      },
    }));

    try {
      const collection = await chatApi.getCollection(getToken, collectionId);

      set((state) => ({
        chat: {
          ...state.chat,
          currentCollection: collection,
          collectionLoading: false,
        },
      }));
    } catch (error) {
      console.error("Failed to select collection:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          collectionLoading: false,
          collectionError: getErrorMessage(error),
        },
      }));
    }
  },

  deleteCollection: async (getToken, collectionId) => {
    try {
      await chatApi.deleteCollection(getToken, collectionId);

      // Remove from collections list
      set((state) => ({
        chat: {
          ...state.chat,
          collections: state.chat.collections.filter(
            (c) => c.id !== collectionId
          ),
          currentCollection:
            state.chat.currentCollection?.id === collectionId
              ? null
              : state.chat.currentCollection,
        },
      }));
    } catch (error) {
      console.error("Failed to delete collection:", error);
      throw error;
    }
  },

  /**
   * Document Upload Actions
   */

  uploadDocumentToCollection: async (getToken, collectionId, file) => {
    set((state) => ({
      chat: {
        ...state.chat,
        uploadStatus: "uploading",
        uploadProgress: 0,
        uploadError: null,
      },
    }));

    try {
      // Upload file
      const data = await chatApi.uploadDocument(
        getToken,
        collectionId,
        file,
        (percent) => {
          set((state) => ({
            chat: { ...state.chat, uploadProgress: percent },
          }));
        }
      );

      // Start listening to indexing progress
      set((state) => ({
        chat: {
          ...state.chat,
          uploadStatus: "indexing",
          uploadProgress: 0,
          currentJobId: data.job_id,
        },
      }));

      // Connect to SSE for indexing progress
      chatApi.connectToIndexingProgress(
        getToken,
        data.job_id,
        (progressData) => {
          set((state) => ({
            chat: {
              ...state.chat,
              uploadProgress: progressData.progress_percent || 0,
            },
          }));
        },
        () => {
          set((state) => ({
            chat: {
              ...state.chat,
              uploadStatus: "completed",
              uploadProgress: 100,
              currentJobId: null,
            },
          }));

          // Refresh current collection to show new document
          if (get().chat.currentCollection?.id === collectionId) {
            get().selectCollection(getToken, collectionId);
          }
        },
        (error) => {
          console.error("Indexing progress error:", error);
          set((state) => ({
            chat: {
              ...state.chat,
              uploadStatus: "failed",
              uploadError: getErrorMessage(error),
              currentJobId: null,
            },
          }));
        }
      );
    } catch (error) {
      console.error("Failed to upload document:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadStatus: "failed",
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  deleteDocument: async (getToken, documentId) => {
    try {
      await chatApi.deleteDocument(getToken, documentId);

      // Refresh current collection to update document list
      const currentCollection = get().chat.currentCollection;
      if (currentCollection) {
        await get().selectCollection(getToken, currentCollection.id);
      }
    } catch (error) {
      console.error("Failed to delete document:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  removeDocumentFromCollection: async (getToken, collectionId, documentId) => {
    try {
      await chatApi.removeDocumentFromCollection(getToken, collectionId, documentId);

      // Refresh current collection to update document list
      await get().selectCollection(getToken, collectionId);
    } catch (error) {
      console.error("Failed to remove document from collection:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  resetUploadStatus: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        uploadStatus: null,
        uploadProgress: 0,
        uploadError: null,
        currentJobId: null,
      },
    }));
  },

  /**
   * Session Actions (NEW - Session-centric)
   */

  createNewSession: async (getToken, { title, documentIds }) => {
    /**
     * Create new chat session with documents
     *
     * Input:
     *   - title: string (optional)
     *   - documentIds: string[] (optional)
     *
     * Output:
     *   Updates currentSession and messages
     */
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

      // Add to sessions list
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
    /**
     * Load existing session with messages and documents
     *
     * Input:
     *   - sessionId: string
     *
     * Output:
     *   Updates currentSession and messages
     */
    try {
      // Get session with documents
      const session = await chatApi.getSession(getToken, sessionId);

      // Get messages
      const historyData = await chatApi.getChatHistory(getToken, sessionId);

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: session,
          messages: historyData.messages,
          chatError: null,
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
    /**
     * Add documents to current session
     *
     * Input:
     *   - documentIds: string[]
     *
     * Output:
     *   Updates currentSession.documents AND sessions array
     */
    const sessionId = get().chat.currentSession?.id;
    if (!sessionId) {
      console.error("No active session");
      return;
    }

    try {
      await chatApi.addDocumentsToSession(getToken, sessionId, documentIds);

      // Reload session to get updated documents list
      const updatedSession = await chatApi.getSession(getToken, sessionId);

      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: updatedSession,
          // IMPORTANT: Also update the session in the sessions array
          sessions: state.chat.sessions.map((s) =>
            s.id === sessionId
              ? {
                  ...s,
                  documents: updatedSession.documents,
                  document_count: updatedSession.documents.length  // UPDATE COUNT
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
    /**
     * Remove document from current session
     *
     * Input:
     *   - documentId: string
     *
     * Output:
     *   Updates currentSession.documents AND sessions array
     */
    const sessionId = get().chat.currentSession?.id;
    if (!sessionId) {
      console.error("No active session");
      return;
    }

    try {
      await chatApi.removeDocumentFromSession(getToken, sessionId, documentId);

      // Update local state - remove document from both currentSession and sessions array
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
              document_count: updatedDocuments.length  // UPDATE COUNT
            },
            // IMPORTANT: Also update the session in the sessions array
            sessions: state.chat.sessions.map((s) =>
              s.id === sessionId
                ? {
                    ...s,
                    documents: updatedDocuments,
                    document_count: updatedDocuments.length  // UPDATE COUNT
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
    /**
     * Update session title
     *
     * Input:
     *   - sessionId: string
     *   - title: string
     *
     * Output:
     *   Updates currentSession.title AND sessions array
     */
    try {
      await chatApi.updateSession(getToken, sessionId, { title });

      // Update local state - both currentSession and sessions array
      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: {
            ...state.chat.currentSession,
            title,
          },
          // IMPORTANT: Also update the session in the sessions array
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

  /**
   * Chat Actions (UPDATED - Session-centric)
   */

  sendMessage: async (getToken, message, numChunks = 5) => {
    /**
     * Send message in current session
     *
     * Input:
     *   - message: string
     *   - numChunks: number (optional)
     *
     * Uses: currentSession.id from state
     * Output: Streams response via SSE
     */
    const sessionId = get().chat.currentSession?.id;
    if (!sessionId) {
      console.error("No active session");
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: "No active session. Please create a session first.",
        },
      }));
      return;
    }

    // Add user message immediately
    const userMessage = {
      role: "user",
      content: message,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      chat: {
        ...state.chat,
        messages: [...state.chat.messages, userMessage],
        isStreaming: true,
        streamingMessage: "",
        chatError: null,
      },
    }));

    // Send to API with streaming
    chatApi.sendChatMessage(
      getToken,
      sessionId,
      message,
      numChunks,
      {
        onSession: (returnedSessionId) => {
          // Session ID confirmed (should match)
          console.log("Session confirmed:", returnedSessionId);
        },
        onChunk: (chunk) => {
          // Append to streaming message
          set((state) => ({
            chat: {
              ...state.chat,
              streamingMessage: state.chat.streamingMessage + chunk,
            },
          }));
        },
        onComplete: () => {
          // Add complete assistant message
          const streamingMessage = get().chat.streamingMessage;
          const assistantMessage = {
            role: "assistant",
            content: streamingMessage,
            created_at: new Date().toISOString(),
          };

          set((state) => ({
            chat: {
              ...state.chat,
              messages: [...state.chat.messages, assistantMessage],
              isStreaming: false,
              streamingMessage: "",
            },
          }));

          // Refresh sessions list
          get().fetchSessions(getToken);
        },
        onError: (error) => {
          console.error("Chat streaming error:", error);
          set((state) => ({
            chat: {
              ...state.chat,
              isStreaming: false,
              streamingMessage: "",
              chatError: getErrorMessage(error),
            },
          }));
        },
      }
    );
  },

  loadChatHistory: async (getToken, sessionId) => {
    /**
     * Load chat history (DEPRECATED - use loadSession instead)
     *
     * Kept for backwards compatibility
     */
    try {
      const data = await chatApi.getChatHistory(getToken, sessionId);
      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: {
            id: data.session_id,
          },
          messages: data.messages,
        },
      }));
    } catch (error) {
      console.error("Failed to load chat history:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: getErrorMessage(error),
        },
      }));
    }
  },

  startNewChat: () => {
    /**
     * Clear current session and messages
     */
    console.log("Starting new chat - clearing session and messages");
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

  /**
   * Sessions Actions (UPDATED - User-centric)
   */

  fetchSessions: async (getToken, options = {}) => {
    /**
     * Fetch all user sessions (not collection-specific)
     *
     * Input:
     *   - options: { limit: number, offset: number }
     *
     * Output:
     *   Updates sessions list
     */
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

      // Remove from sessions list
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

  /**
   * Export Actions
   */

  exportSession: async (getToken, sessionId) => {
    try {
      const data = await chatApi.exportSession(getToken, sessionId);
      return data;
    } catch (error) {
      console.error("Failed to export session:", error);
      throw error;
    }
  },
});
