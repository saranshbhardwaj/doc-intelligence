/**
 * Comparison actions
 */
import * as chatApi from "../../../api/chat";
import { getErrorMessage } from "./utils";

export const createChatComparisonActions = (set, get) => ({
  setComparisonContext: (context) => {
    set((state) => ({
      chat: {
        ...state.chat,
        comparison: {
          ...state.chat.comparison,
          isActive: !!context,
          context: context,
        },
      },
    }));
  },

  clearComparison: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        comparison: {
          isActive: false,
          context: null,
          selectedPairIndex: null,
          viewMode: "cards",
          expandedTopics: [],
        },
      },
    }));
  },

  setComparisonViewMode: (viewMode) => {
    set((state) => ({
      chat: {
        ...state.chat,
        comparison: {
          ...state.chat.comparison,
          viewMode: viewMode,
        },
      },
    }));
  },

  toggleComparisonTopic: (topic) => {
    set((state) => {
      const currentTopics = state.chat.comparison.expandedTopics;
      const newTopics = currentTopics.includes(topic)
        ? currentTopics.filter((t) => t !== topic)
        : [...currentTopics, topic];

      return {
        chat: {
          ...state.chat,
          comparison: {
            ...state.chat.comparison,
            expandedTopics: newTopics,
          },
        },
      };
    });
  },

  // Document selection actions

  setComparisonSelectionNeeded: (data) => {
    set((state) => ({
      chat: {
        ...state.chat,
        comparison: {
          ...state.chat.comparison,
          selectionNeeded: true,
          selectionDocuments: data.documents || [],
          selectionPreSelected: data.pre_selected || [],
          selectionQuery: data.original_query || "",
          selectionMessage: data.message || "Select 2-3 documents to compare:",
        },
        isStreaming: false,
        isThinking: false,
      },
    }));
  },

  clearComparisonSelection: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        comparison: {
          ...state.chat.comparison,
          selectionNeeded: false,
          selectionDocuments: [],
          selectionPreSelected: [],
          selectionQuery: "",
          selectionMessage: "",
        },
      },
    }));
  },

  confirmComparisonSelection: async (getToken, sessionId, documentIds, originalQuery, skipComparison) => {
    // Clear selection state
    get().clearComparisonSelection();

    // Add user message to chat
    const userMessage = {
      role: "user",
      content: originalQuery,
      created_at: new Date().toISOString(),
    };

    set((state) => ({
      chat: {
        ...state.chat,
        messages: [...state.chat.messages, userMessage],
        isStreaming: true,
        streamingMessage: "",
        chatError: null,
        comparison: {
          isActive: false,
          context: null,
          viewMode: state.chat.comparison?.viewMode || "cards",
          selectedPairIndex: null,
          expandedTopics: [],
          selectionNeeded: false,
          selectionDocuments: [],
          selectionPreSelected: [],
          selectionQuery: "",
          selectionMessage: "",
        },
      },
    }));

    // Call confirmComparison API
    chatApi.confirmComparison(
      getToken,
      sessionId,
      documentIds,
      originalQuery,
      skipComparison,
      {
        onSession: (returnedSessionId) => {
          console.log("Session confirmed:", returnedSessionId);
        },
        onThinking: (data) => {
          console.log("Backend is thinking:", data);
          set((state) => ({
            chat: { ...state.chat, isThinking: true },
          }));
        },
        onComparisonContext: (context) => {
          console.log("Received comparison context:", context);
          set((state) => ({
            chat: {
              ...state.chat,
              comparison: {
                isActive: true,
                context: context,
                selectedPairIndex: null,
                viewMode: "cards",
                expandedTopics: [],
                selectionNeeded: false,
                selectionDocuments: [],
                selectionPreSelected: [],
                selectionQuery: "",
                selectionMessage: "",
              },
            },
          }));
        },
        onChunk: (chunk) => {
          set((state) => ({
            chat: {
              ...state.chat,
              isThinking: false,
              streamingMessage: state.chat.streamingMessage + chunk,
            },
          }));
        },
        onComplete: () => {
          const streamingMessage = get().chat.streamingMessage;
          const comparisonState = get().chat.comparison;
          const assistantMessage = {
            role: "assistant",
            content: streamingMessage,
            created_at: new Date().toISOString(),
            ...(comparisonState?.isActive && comparisonState?.context
              ? { comparison_metadata: comparisonState.context }
              : {}),
          };

          set((state) => ({
            chat: {
              ...state.chat,
              messages: [...state.chat.messages, assistantMessage],
              isStreaming: false,
              streamingMessage: "",
            },
          }));

          get().fetchSessions(getToken);
        },
        onError: (error) => {
          console.error("Comparison confirmation error:", error);
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
});
