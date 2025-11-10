/**
 * Chat Slice for Zustand Store
 *
 * Manages state for Chat Mode:
 * - Collections list
 * - Current collection and its documents
 * - Active chat session and messages
 * - Document upload progress
 */

import * as chatApi from "../../api/chat";

export const createChatSlice = (set, get) => ({
  chat: {
    // Collections
    collections: [],
    collectionsLoading: false,
    collectionsError: null,

    // Current collection
    currentCollection: null,
    collectionLoading: false,
    collectionError: null,

    // Document upload
    uploadProgress: 0,
    uploadStatus: null, // 'uploading', 'indexing', 'completed', 'failed'
    uploadError: null,
    currentJobId: null,

    // Chat session
    currentSession: null,
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
      set((state) => ({
        chat: {
          ...state.chat,
          collectionsLoading: false,
          collectionsError: error.message,
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

      // Also fetch sessions for this collection
      get().fetchSessions(getToken, collectionId);
    } catch (error) {
      set((state) => ({
        chat: {
          ...state.chat,
          collectionLoading: false,
          collectionError: error.message,
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
        (completedData) => {
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
          set((state) => ({
            chat: {
              ...state.chat,
              uploadStatus: "failed",
              uploadError: error.message,
              currentJobId: null,
            },
          }));
        }
      );
    } catch (error) {
      set((state) => ({
        chat: {
          ...state.chat,
          uploadStatus: "failed",
          uploadError: error.message,
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
   * Chat Actions
   */

  sendMessage: async (getToken, collectionId, message, numChunks = 5) => {
    const currentSession = get().chat.currentSession;

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
      collectionId,
      message,
      currentSession?.id,
      numChunks,
      {
        onSession: (sessionId) => {
          // New session created
          if (!currentSession) {
            set((state) => ({
              chat: {
                ...state.chat,
                currentSession: { id: sessionId },
              },
            }));
          }
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
          get().fetchSessions(getToken, collectionId);
        },
        onError: (error) => {
          set((state) => ({
            chat: {
              ...state.chat,
              isStreaming: false,
              streamingMessage: "",
              chatError: error.message,
            },
          }));
        },
      }
    );
  },

  loadChatHistory: async (getToken, sessionId) => {
    try {
      const data = await chatApi.getChatHistory(getToken, sessionId);
      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: {
            id: data.session_id,
            collection_id: data.collection_id,
          },
          messages: data.messages,
        },
      }));
    } catch (error) {
      console.error("Failed to load chat history:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          chatError: error.message,
        },
      }));
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

  /**
   * Sessions Actions
   */

  fetchSessions: async (getToken, collectionId) => {
    set((state) => ({
      chat: {
        ...state.chat,
        sessionsLoading: true,
      },
    }));

    try {
      const data = await chatApi.listSessions(getToken, collectionId);
      set((state) => ({
        chat: {
          ...state.chat,
          sessions: data.sessions,
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
