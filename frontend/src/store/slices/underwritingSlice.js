/**
 * Underwriting Slice for Zustand Store
 *
 * Manages RE underwriting state including:
 * - List of underwriting runs
 * - Current run being edited
 * - Wizard step progression (0-5)
 * - Document extraction progress via SSE
 */

import { listUnderwritingRuns, getUnderwritingRun } from "../../api/re-underwriting";
import { streamJobProgress } from "../../api/sse-utils";

export const createUnderwritingSlice = (set, get) => ({
  // ========== State ==========
  underwriting: {
    // List of all underwriting runs for the user
    runs: [],

    // Currently selected run for editing
    currentRun: null,

    // Current step in the 6-step wizard (0-5)
    wizardStep: 0,

    // Extraction state during document processing
    extraction: {
      jobId: null,
      isProcessing: false,
      progress: 0,
      stage: null,
      message: null,
      cleanup: null, // SSE cleanup function — not persisted
    },
  },

  // ========== Actions ==========

  /**
   * Load all underwriting runs for the current user
   */
  loadRuns: async (getToken) => {
    try {
      const data = await listUnderwritingRuns(getToken, { limit: 100 });
      set((state) => ({
        underwriting: {
          ...state.underwriting,
          runs: data.runs || [],
        },
      }));
    } catch (err) {
      console.error("Failed to load underwriting runs:", err);
    }
  },

  /**
   * Load a specific underwriting run
   */
  loadRun: async (getToken, runId) => {
    try {
      const data = await getUnderwritingRun(getToken, runId);
      set((state) => ({
        underwriting: {
          ...state.underwriting,
          currentRun: data,
        },
      }));
    } catch (err) {
      console.error("Failed to load underwriting run:", err);
    }
  },

  /**
   * Set the current wizard step
   */
  setWizardStep: (step) => {
    set((state) => ({
      underwriting: {
        ...state.underwriting,
        wizardStep: Math.max(0, Math.min(5, step)),
      },
    }));
  },

  /**
   * Start extraction with SSE progress tracking
   * @param {string} jobId - Job ID for SSE stream
   * @param {Function} cleanup - SSE cleanup function
   */
  startExtraction: (jobId, cleanup) => {
    set((state) => ({
      underwriting: {
        ...state.underwriting,
        extraction: {
          ...state.underwriting.extraction,
          jobId,
          isProcessing: true,
          progress: 0,
          stage: "starting",
          message: "Starting document extraction...",
          cleanup,
        },
      },
    }));
  },

  /**
   * Update extraction progress from SSE events
   */
  updateExtractionProgress: (progressData) => {
    set((state) => ({
      underwriting: {
        ...state.underwriting,
        extraction: {
          ...state.underwriting.extraction,
          progress: progressData.progress || state.underwriting.extraction.progress,
          stage: progressData.stage || state.underwriting.extraction.stage,
          message: progressData.message || state.underwriting.extraction.message,
        },
      },
    }));
  },

  /**
   * Mark extraction as complete
   */
  completeExtraction: () => {
    set((state) => ({
      underwriting: {
        ...state.underwriting,
        extraction: {
          ...state.underwriting.extraction,
          isProcessing: false,
          progress: 100,
          stage: "completed",
          message: "Extraction completed successfully",
        },
      },
    }));
  },

  /**
   * Reset extraction state
   */
  resetExtraction: () => {
    const { cleanup } = get().underwriting.extraction;

    if (cleanup) {
      cleanup();
    }

    set((state) => ({
      underwriting: {
        ...state.underwriting,
        extraction: {
          jobId: null,
          isProcessing: false,
          progress: 0,
          stage: null,
          message: null,
          cleanup: null,
        },
      },
    }));
  },

  /**
   * Set the current run (used immediately after createUnderwritingRun)
   */
  setCurrentRun: (run) => {
    set((state) => ({
      underwriting: {
        ...state.underwriting,
        currentRun: run,
      },
    }));
  },
});
