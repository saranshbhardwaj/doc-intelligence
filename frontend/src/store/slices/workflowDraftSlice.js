/**
 * Workflow Draft Slice for Zustand Store
 *
 * Manages workflow draft state including:
 * - Selected documents (full objects, not just IDs)
 * - Selected workflow template
 * - Workflow variables
 * - Workflow execution state (jobId, runId, progress tracking)
 * - Persists across page refresh via localStorage
 */

import { streamProgress } from '../../api';

export const createWorkflowDraftSlice = (set, get) => ({
  // ========== State ==========
  workflowDraft: {
    // Array of full document objects (solves Problem 1: newly uploaded docs are available)
    selectedDocuments: [],

    // Selected workflow template
    selectedWorkflow: null,

    // Workflow configuration variables
    variables: {},

    // Execution state (for running workflows)
    execution: {
      jobId: null,
      runId: null,
      isProcessing: false,
      progress: 0,
      stage: null,
      message: null,
      cleanup: null, // SSE cleanup function
    },
  },

  // ========== Actions ==========

  /**
   * Add a document to the workflow draft
   * @param {Object} doc - Full document object with all metadata
   */
  addDocumentToDraft: (doc) => {
    set((state) => {
      // Prevent duplicates
      const exists = state.workflowDraft.selectedDocuments.some(d => d.id === doc.id);
      if (exists) {
        return state;
      }

      return {
        workflowDraft: {
          ...state.workflowDraft,
          selectedDocuments: [...state.workflowDraft.selectedDocuments, doc],
        },
      };
    });
  },

  /**
   * Add multiple documents to the workflow draft
   * @param {Array} docs - Array of full document objects
   */
  addDocumentsToDraft: (docs) => {
    set((state) => {
      // Filter out duplicates
      const currentIds = new Set(state.workflowDraft.selectedDocuments.map(d => d.id));
      const newDocs = docs.filter(doc => !currentIds.has(doc.id));

      if (newDocs.length === 0) {
        return state;
      }

      return {
        workflowDraft: {
          ...state.workflowDraft,
          selectedDocuments: [...state.workflowDraft.selectedDocuments, ...newDocs],
        },
      };
    });
  },

  /**
   * Remove a document from the workflow draft
   * @param {string} docId - Document ID to remove
   */
  removeDocumentFromDraft: (docId) => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        selectedDocuments: state.workflowDraft.selectedDocuments.filter(d => d.id !== docId),
      },
    }));
  },

  /**
   * Set all selected documents (replaces existing selection)
   * @param {Array} docs - Array of full document objects
   */
  setSelectedDocuments: (docs) => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        selectedDocuments: docs,
      },
    }));
  },

  /**
   * Set the selected workflow template
   * @param {Object} workflow - Workflow template object
   */
  setSelectedWorkflow: (workflow) => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        selectedWorkflow: workflow,
        // Reset variables when workflow changes
        variables: workflow ? {} : state.workflowDraft.variables,
      },
    }));
  },

  /**
   * Update workflow variables
   * @param {Object} variables - Workflow configuration variables
   */
  setWorkflowVariables: (variables) => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        variables,
      },
    }));
  },

  /**
   * Clear the entire workflow draft (reset to empty state)
   */
  clearWorkflowDraft: () => {
    set({
      workflowDraft: {
        selectedDocuments: [],
        selectedWorkflow: null,
        variables: {},
      },
    });
  },

  /**
   * Get selected document IDs (for API calls)
   * @returns {Array<string>} Array of document IDs
   */
  getSelectedDocumentIds: () => {
    return get().workflowDraft.selectedDocuments.map(doc => doc.id);
  },

  // ========== Workflow Execution Actions ==========

  /**
   * Start workflow execution tracking
   * @param {string} jobId - Job ID for progress tracking
   * @param {string} runId - Workflow run ID
   */
  startWorkflowExecution: (jobId, runId) => {
    console.log('🚀 Starting workflow execution tracking:', { jobId, runId });
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          ...state.workflowDraft.execution,
          jobId,
          runId,
          isProcessing: true,
          progress: 0,
          stage: 'queued',
          message: 'Workflow queued...',
        },
      },
    }));
  },

  /**
   * Update workflow execution progress
   * @param {Object} progressData - Progress data from SSE
   */
  updateWorkflowProgress: (progressData) => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          ...state.workflowDraft.execution,
          progress: progressData.progress_percent || 0,
          stage: progressData.current_stage || state.workflowDraft.execution.stage,
          message: progressData.message || state.workflowDraft.execution.message,
        },
      },
    }));
  },

  /**
   * Complete workflow execution
   */
  completeWorkflowExecution: () => {
    console.log('✅ Workflow execution completed');
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          ...state.workflowDraft.execution,
          isProcessing: false,
          progress: 100,
          stage: 'completed',
          message: 'Workflow completed successfully',
        },
      },
    }));
  },

  /**
   * Fail workflow execution
   * @param {string} errorMessage - Error message
   */
  failWorkflowExecution: (errorMessage) => {
    console.error('❌ Workflow execution failed:', errorMessage);
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          ...state.workflowDraft.execution,
          isProcessing: false,
          stage: 'failed',
          message: errorMessage || 'Workflow failed',
        },
      },
    }));
  },

  /**
   * Reconnect to active workflow execution after navigation
   * @param {Function} getToken - Clerk getToken function
   */
  reconnectWorkflowExecution: async (getToken) => {
    const { jobId, runId } = get().workflowDraft.execution;

    if (!jobId || !runId) {
      console.log('❌ No active workflow to reconnect');
      return;
    }

    console.log('🔄 Reconnecting to workflow execution:', { jobId, runId });

    try {
      const cleanup = await streamProgress(jobId, getToken, {
        onProgress: (data) => {
          get().updateWorkflowProgress(data);
        },
        onComplete: (data) => {
          get().completeWorkflowExecution();
        },
        onError: (errorData) => {
          const errorMsg = typeof errorData === 'string'
            ? errorData
            : (errorData?.message || 'Workflow failed');
          get().failWorkflowExecution(errorMsg);
        },
        onEnd: async (data) => {
          console.log('🏁 Workflow SSE stream ended:', data?.reason);
          // Don't reset jobId/runId here - keep them for result page navigation
        },
      });

      set((state) => ({
        workflowDraft: {
          ...state.workflowDraft,
          execution: {
            ...state.workflowDraft.execution,
            cleanup,
            isProcessing: true,
          },
        },
      }));
    } catch (err) {
      console.error('Reconnection failed:', err);
      get().failWorkflowExecution('Failed to reconnect to workflow');
    }
  },

  /**
   * Cancel ongoing workflow execution
   */
  cancelWorkflowExecution: () => {
    const { cleanup } = get().workflowDraft.execution;

    if (cleanup) {
      cleanup();
    }

    console.log('🛑 Workflow execution canceled');
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          ...state.workflowDraft.execution,
          isProcessing: false,
          cleanup: null,
        },
      },
    }));
  },

  /**
   * Reset workflow execution state (after completion or navigation away)
   */
  resetWorkflowExecution: () => {
    const { cleanup } = get().workflowDraft.execution;

    if (cleanup) {
      cleanup();
    }

    console.log('🔄 Resetting workflow execution state');
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        execution: {
          jobId: null,
          runId: null,
          isProcessing: false,
          progress: 0,
          stage: null,
          message: null,
          cleanup: null,
        },
      },
    }));
  },
});
