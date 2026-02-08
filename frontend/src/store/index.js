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
import { createChatSlice } from "./slices/chat/chatSlice";
import { createWorkflowDraftSlice } from "./slices/workflowDraftSlice";
import { createTemplateFillSlice } from "./slices/templateFillSlice";
import { createFeedbackSlice } from "./slices/feedbackSlice";

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
      ...createTemplateFillSlice(...args),
      ...createFeedbackSlice(...args),
    }),
    {
      name: "sand-cloud-storage", // localStorage key
      storage: createJSONStorage(() => localStorage), // Use localStorage for workflow draft persistence
      partialize: (state) => ({
        // Only persist extraction state (jobId, extractionId) for reconnection
        // Don't persist isProcessing or progress - they will be restored via reconnection
        // Don't persist user data (should be fetched fresh)
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
        // Persist document indexing jobs for reconnection
        chat: {
          indexingJobs: Object.fromEntries(
            Object.entries(state.chat?.indexingJobs || {}).map(([docId, job]) => [
              docId,
              {
                jobId: job.jobId,
                documentId: job.documentId,
                collectionId: job.collectionId,
                // Don't persist: isProcessing, progress, cleanup, message, error
              },
            ])
          ),
          // Persist comparison UI preferences (NOT context - too large!)
          comparisonUI: {
            viewMode: state.chat?.comparison?.viewMode || 'cards',
          },
        },
        // Persist template fill state for reconnection
        templateFill: {
          fillRunId: state.templateFill?.fillRunId ?? null,
          // Don't persist: fillRun, pdfUrl, pdfUrlExpiry, selectedText, isLoading, isSaving, error, pdfRefreshTimer
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
          chat: {
            ...current.chat,
            indexingJobs: {
              ...current.chat.indexingJobs,
              ...(persisted.chat?.indexingJobs || {}),
            },
            // Restore comparison UI preferences
            comparison: {
              ...current.chat.comparison,
              viewMode: persisted.chat?.comparisonUI?.viewMode || current.chat.comparison.viewMode,
            },
          },
          templateFill: {
            ...current.templateFill,
            ...persisted.templateFill,
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
      // Collections
      fetchCollections: state.fetchCollections,
      createCollection: state.createCollection,
      selectCollection: state.selectCollection,
      deleteCollection: state.deleteCollection,
      // Documents
      uploadDocumentToCollection: state.uploadDocumentToCollection,
      deleteDocument: state.deleteDocument,
      resetUploadStatus: state.resetUploadStatus,
      removeDocumentFromCollection: state.removeDocumentFromCollection,
      // Sessions (NEW)
      createNewSession: state.createNewSession,
      loadSession: state.loadSession,
      fetchSessions: state.fetchSessions,
      deleteSession: state.deleteSession,
      exportSession: state.exportSession,
      updateSessionTitle: state.updateSessionTitle,
      // Session Documents (NEW)
      addDocumentsToCurrentSession: state.addDocumentsToCurrentSession,
      removeDocumentFromCurrentSession: state.removeDocumentFromCurrentSession,
      // Messages
      sendMessage: state.sendMessage,
      loadChatHistory: state.loadChatHistory,
      startNewChat: state.startNewChat,
      // Indexing actions
      startDocumentIndexing: state.startDocumentIndexing,
      updateIndexingProgress: state.updateIndexingProgress,
      completeIndexing: state.completeIndexing,
      failIndexing: state.failIndexing,
      reconnectAllIndexingJobs: state.reconnectAllIndexingJobs,
      clearIndexingJob: state.clearIndexingJob,
      clearAllIndexingJobs: state.clearAllIndexingJobs,
      // Comparison mode actions
      setComparisonContext: state.setComparisonContext,
      clearComparison: state.clearComparison,
      setComparisonViewMode: state.setComparisonViewMode,
      toggleComparisonTopic: state.toggleComparisonTopic,
      // PDF viewer actions
      highlightChunk: state.highlightChunk,
      clearHighlight: state.clearHighlight,
      setActivePdfDocument: state.setActivePdfDocument,
      loadPdfUrlForDocument: state.loadPdfUrlForDocument,
      clearPdfUrlCache: state.clearPdfUrlCache,
      // Legacy (deprecated)
      toggleDocumentSelection: state.toggleDocumentSelection,
      toggleSelectAll: state.toggleSelectAll,
      setSelectedDocuments: state.setSelectedDocuments,
    }))
  );

// Comparison selectors
export const useComparison = () =>
  useStore((state) => state.chat.comparison);

export const usePdfViewer = () =>
  useStore((state) => state.chat.pdfViewer);

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

// Template Fill selectors
export const useTemplateFill = () => useStore((state) => state.templateFill);
export const useTemplateFillActions = () =>
  useStore(
    useShallow((state) => ({
      loadFillRun: state.loadFillRun,
      loadPdfUrl: state.loadPdfUrl,
      setSelectedText: state.setSelectedText,
      updateFieldData: state.updateFieldData,
      updateMappings: state.updateMappings,
      continueProcessing: state.continueProcessing,
      resetTemplateFill: state.resetTemplateFill,
      clearTemplateFillError: state.clearTemplateFillError,
      registerPdfPopout: state.registerPdfPopout,
      registerExcelPopout: state.registerExcelPopout,
      navigatePdfToPage: state.navigatePdfToPage,
      cleanupPopouts: state.cleanupPopouts,
      cacheExcelWorkbook: state.cacheExcelWorkbook,
      getCachedExcelWorkbook: state.getCachedExcelWorkbook,
      clearCachedExcelWorkbook: state.clearCachedExcelWorkbook,
    }))
  );

// Feedback selectors
export const useFeedback = () => useStore((state) => state.feedback);
export const useFeedbackActions = () =>
  useStore(
    useShallow((state) => ({
      openFeedbackModal: state.openFeedbackModal,
      closeFeedbackModal: state.closeFeedbackModal,
      isFeedbackModalOpen: state.isFeedbackModalOpen,
      submitFeedback: state.submitFeedback,
      hasFeedbackBeenSubmitted: state.hasFeedbackBeenSubmitted,
      setFeedbackSubmitting: state.setFeedbackSubmitting,
      isFeedbackSubmitting: state.isFeedbackSubmitting,
    }))
  );

export default useStore;
