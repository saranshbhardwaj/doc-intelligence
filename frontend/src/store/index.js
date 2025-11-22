/**
 * Main Zustand Store
 *
 * Combines all slices and provides centralized state management
 * with persistence for extraction state across navigation.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { useShallow } from "zustand/react/shallow";
import { createExtractionSlice } from "./slices/extractionSlice";
import { createUserSlice } from "./slices/userSlice";
import { createChatSlice } from "./slices/chatSlice";
import { createWorkflowDraftSlice } from "./slices/workflowDraftSlice";

/**
 * Main store combining all slices
 */
export const useStore = create(
  persist(
    (...args) => ({
      ...createExtractionSlice(...args),
      ...createUserSlice(...args),
      ...createChatSlice(...args),
      ...createWorkflowDraftSlice(...args),
    }),
    {
      name: "sand-cloud-storage", // localStorage key
      storage: createJSONStorage(() => localStorage), // Use localStorage for workflow draft persistence
      partialize: (state) => ({
        // Only persist extraction state (jobId, extractionId) for reconnection
        // Don't persist isProcessing or progress - they will be restored via reconnection
        // Don't persist user data (should be fetched fresh)
        // Don't persist chat state (should be fetched fresh from selected collection/session)
        extraction: {
          jobId: state.extraction?.jobId ?? null,
          extractionId: state.extraction?.extractionId ?? null,
        },
        // Persist workflow draft state (documents, workflow, variables)
        // This survives page refresh and solves the "lost state" problem
        workflowDraft: {
          ...state.workflowDraft,
          // Persist execution state (jobId, runId) for reconnection
          // Don't persist isProcessing, progress, cleanup - they will be restored via reconnection
          execution: {
            jobId: state.workflowDraft.execution.jobId ?? null,
            runId: state.workflowDraft.execution.runId ?? null,
          },
        },
      }),
      // Merge persisted slice keys into current state instead of overwriting
      // so that non-persisted defaults (e.g. progress structure) remain intact.
      merge: (persisted, current) => {
        return {
          ...current,
          extraction: {
            ...current.extraction,
            ...persisted.extraction,
          },
          workflowDraft: {
            ...current.workflowDraft,
            ...persisted.workflowDraft,
            execution: {
              ...current.workflowDraft.execution,
              ...(persisted.workflowDraft?.execution || {}),
            },
          },
        };
      },
    }
  )
);

/**
 * Selector hooks for easy access to specific slices
 */

// Extraction selectors
export const useExtraction = () => useStore((state) => state.extraction);

export const useExtractionHistory = () =>
  useStore((state) => state.extractionHistory);

export const useExtractionActions = () =>
  useStore(
    useShallow((state) => ({
      uploadDocument: state.uploadDocument,
      extractLibraryDocument: state.extractLibraryDocument,
      extractTempDocument: state.extractTempDocument,
      retryExtraction: state.retryExtraction,
      reconnectExtraction: state.reconnectExtraction,
      cancelExtraction: state.cancelExtraction,
      resetExtraction: state.resetExtraction,
      setResult: state.setResult,
      setError: state.setError,
      setProgress: state.setProgress,
      setProcessing: state.setProcessing,
      fetchExtractionHistory: state.fetchExtractionHistory,
    }))
  );

// User selectors
export const useUser = () => useStore((state) => state.user);
export const useUserActions = () =>
  useStore(
    useShallow((state) => ({
      fetchUserInfo: state.fetchUserInfo,
      fetchExtractions: state.fetchExtractions,
      loadMoreExtractions: state.loadMoreExtractions,
      refreshDashboard: state.refreshDashboard,
      clearUserData: state.clearUserData,
    }))
  );

// Chat selectors
export const useChat = () => useStore((state) => state.chat);
export const useChatActions = () =>
  useStore(
    useShallow((state) => ({
      fetchCollections: state.fetchCollections,
      createCollection: state.createCollection,
      selectCollection: state.selectCollection,
      deleteCollection: state.deleteCollection,
      uploadDocumentToCollection: state.uploadDocumentToCollection,
      deleteDocument: state.deleteDocument,
      resetUploadStatus: state.resetUploadStatus,
      sendMessage: state.sendMessage,
      loadChatHistory: state.loadChatHistory,
      startNewChat: state.startNewChat,
      fetchSessions: state.fetchSessions,
      deleteSession: state.deleteSession,
      exportSession: state.exportSession,
    }))
  );

// Workflow Draft selectors
export const useWorkflowDraft = () => useStore((state) => state.workflowDraft);
export const useWorkflowDraftActions = () =>
  useStore(
    useShallow((state) => ({
      addDocumentToDraft: state.addDocumentToDraft,
      addDocumentsToDraft: state.addDocumentsToDraft,
      removeDocumentFromDraft: state.removeDocumentFromDraft,
      setSelectedDocuments: state.setSelectedDocuments,
      setSelectedWorkflow: state.setSelectedWorkflow,
      setWorkflowVariables: state.setWorkflowVariables,
      clearWorkflowDraft: state.clearWorkflowDraft,
      getSelectedDocumentIds: state.getSelectedDocumentIds,
      // Execution actions
      startWorkflowExecution: state.startWorkflowExecution,
      updateWorkflowProgress: state.updateWorkflowProgress,
      completeWorkflowExecution: state.completeWorkflowExecution,
      failWorkflowExecution: state.failWorkflowExecution,
      reconnectWorkflowExecution: state.reconnectWorkflowExecution,
      cancelWorkflowExecution: state.cancelWorkflowExecution,
      resetWorkflowExecution: state.resetWorkflowExecution,
    }))
  );

export default useStore;
