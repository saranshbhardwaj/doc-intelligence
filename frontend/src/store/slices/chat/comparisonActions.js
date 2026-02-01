/**
 * Comparison actions
 */

export const createChatComparisonActions = (set) => ({
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
});
