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
        thinkingMessage: "",
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

    // The user message is already in the chat from the initial send — don't re-add it.
    set((state) => ({
      chat: {
        ...state.chat,
        isStreaming: true,
        isThinking: true,
        thinkingMessage: "Thinking...",
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
        onSession: () => {},
        onThinking: (data) => {
          set((state) => ({
            chat: { ...state.chat, isThinking: true, thinkingMessage: data?.message || "Thinking..." },
          }));
        },
        onComparisonContext: (context) => {
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
        onCitationContext: (context) => {
          set((state) => ({
            chat: {
              ...state.chat,
              citationContext: context,
            },
          }));
        },
        onChunk: (chunk) => {
          set((state) => ({
            chat: {
              ...state.chat,
              isThinking: false,
              thinkingMessage: "",
              streamingMessage: state.chat.streamingMessage + chunk,
            },
          }));
        },
        onComplete: (doneData = {}) => {
          const streamingMessage = get().chat.streamingMessage;
          const comparisonState = get().chat.comparison;
          const citationContext = get().chat.citationContext;
          const assistantMessage = {
            role: "assistant",
            content: streamingMessage,
            created_at: new Date().toISOString(),
            ...(doneData.assistant_message_id ? { id: doneData.assistant_message_id } : {}),
            ...(comparisonState?.isActive && comparisonState?.context
              ? { comparison_metadata: comparisonState.context }
              : {}),
            ...(citationContext?.citations?.length > 0
              ? { citation_context: citationContext }
              : {}),
          };

          set((state) => {
            const messages = [...state.chat.messages];
            if (doneData.user_message_id && messages.length > 0) {
              const lastIdx = messages.length - 1;
              messages[lastIdx] = { ...messages[lastIdx], id: doneData.user_message_id };
            }
            return {
              chat: {
                ...state.chat,
                messages: [...messages, assistantMessage],
                isStreaming: false,
                streamingMessage: "",
              },
            };
          });

          get().fetchSessions(getToken);
        },
        onError: (error) => {
          console.error("Comparison confirmation error:", error);
          set((state) => ({
            chat: {
              ...state.chat,
              isStreaming: false,
              isThinking: false,
              thinkingMessage: "",
              streamingMessage: "",
              chatError: getErrorMessage(error),
            },
          }));
        },
      }
    );
  },
});
