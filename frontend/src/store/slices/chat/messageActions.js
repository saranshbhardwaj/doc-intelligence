/**
 * Message actions
 */
import * as chatApi from "../../../api/chat";
import { getErrorMessage } from "./utils";
import { toast } from "sonner";

export const createChatMessageActions = (set, get) => ({
  sendMessage: async (getToken, message, numChunks = 5) => {
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
        },
      },
    }));

    chatApi.sendChatMessage(
      getToken,
      sessionId,
      message,
      numChunks,
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
        onSessionWarning: (data) => {
          // Display toast notification for long conversation
          toast.warning("Long conversation detected", {
            description: data.recommendation || "Consider starting a new session for best results",
            duration: 8000,
            action: {
              label: "New Session",
              onClick: () => {
                // Clear current session and show empty state
                get().startNewChat();
                try {
                  localStorage.removeItem("lastActiveChatSessionId");
                } catch (e) {
                  console.error("Failed to clear last session:", e);
                }
              },
            },
          });
        },
        onComparisonSelection: (data) => {
          get().setComparisonSelectionNeeded(data);
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
        onComplete: () => {
          const streamingMessage = get().chat.streamingMessage;
          const comparisonState = get().chat.comparison;
          const citationContext = get().chat.citationContext;
          const assistantMessage = {
            role: "assistant",
            content: streamingMessage,
            created_at: new Date().toISOString(),
            ...(comparisonState?.isActive && comparisonState?.context
              ? { comparison_metadata: comparisonState.context }
              : {}),
            ...(citationContext?.citations?.length > 0
              ? { citation_context: citationContext }
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

          // Refresh messages from API to get database IDs (needed for feedback buttons)
          chatApi.getChatHistory(getToken, sessionId).then((data) => {
            set((state) => ({
              chat: {
                ...state.chat,
                messages: data.messages,
              },
            }));
          }).catch((err) => {
            console.error("Failed to refresh message IDs:", err);
          });

          get().fetchSessions(getToken);
        },
        onError: (error) => {
          console.error("Chat streaming error:", error);
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

  loadChatHistory: async (getToken, sessionId) => {
    try {
      const data = await chatApi.getChatHistory(getToken, sessionId);
      set((state) => ({
        chat: {
          ...state.chat,
          currentSession: {
            ...state.chat.currentSession,
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
});
