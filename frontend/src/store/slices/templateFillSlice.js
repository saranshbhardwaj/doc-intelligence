/**
 * Template Fill Slice for Zustand Store
 *
 * Manages Real Estate template fill state including:
 * - Fill run data and status
 * - PDF URL and auto-refresh
 * - Selected text from PDF viewer
 * - Field updates and mappings
 */

import {
  getFillRunStatus,
  updateExtractedData,
  updateFillMappings,
  continueFillRun,
} from '../../api/re-templates';
import { getDocumentDownloadUrl } from '../../api/documents';

/**
 * Get safe error message from error object
 */
const getErrorMessage = (error) => {
  return error?.message || 'An unexpected error occurred';
};

export const createTemplateFillSlice = (set, get) => ({
  // ========== State ==========
  templateFill: {
    // Fill run data
    fillRun: null,
    fillRunId: null,

    // PDF viewer
    pdfUrl: null,
    pdfUrlExpiry: null,
    pdfRefreshTimer: null,

    // Selected text from PDF
    selectedText: null, // { text, page }

    // Pop-out window references
    pdfPopoutWindow: null,
    excelPopoutWindow: null,

    // Loading and error states
    isLoading: false,
    isSaving: false,
    error: null,
  },

  // ========== Actions ==========

  /**
   * Load fill run data and initialize PDF URL
   */
  loadFillRun: async (fillRunId, getToken, options = {}) => {
    const { silent = false, skipPdf = false } = options;
    console.log('📊 Loading fill run:', fillRunId, silent ? '(silent)' : '', skipPdf ? '(skip PDF)' : '');

    const prevState = get().templateFill;
    const isNewRun = prevState.fillRunId !== fillRunId;

    // If switching runs, clear anything that could be stale (PDF URL, selection, timers, old fillRun)
    if (isNewRun && prevState.pdfRefreshTimer) {
      clearTimeout(prevState.pdfRefreshTimer);
    }

    // Only show loading spinner for initial load, not for silent refreshes
    const shouldShowLoading = isNewRun && !silent;

    set((state) => ({
      templateFill: {
        ...state.templateFill,
        ...(isNewRun
          ? {
              fillRun: null,
              pdfUrl: null,
              pdfUrlExpiry: null,
              pdfRefreshTimer: null,
              selectedText: null,
            }
          : null),
        fillRunId,
        isLoading: shouldShowLoading,
        error: null,
      },
    }));

    try {
      // Fetch fill run data
      const fillRunData = await getFillRunStatus(getToken, fillRunId);
      console.log('✅ Fill run loaded:', fillRunData);

      set((state) => ({
        templateFill: {
          ...state.templateFill,
          fillRun: fillRunData,
          isLoading: false,
        },
      }));

      // Only load PDF URL on initial load or when switching runs
      // Skip PDF reload during silent refreshes to avoid unnecessary API calls
      const shouldLoadPdf = !skipPdf && (isNewRun || !prevState.pdfUrl);

      if (shouldLoadPdf) {
        console.log('📄 Checking document_id:', fillRunData.document_id);
        if (fillRunData.document_id) {
          console.log('📄 Loading PDF for document:', fillRunData.document_id);
          await get().loadPdfUrl(fillRunData.document_id, getToken);
        } else {
          console.warn('⚠️ No document_id found in fill run');

          // Ensure we don't show a stale PDF from a previous run
          set((state) => ({
            templateFill: {
              ...state.templateFill,
              pdfUrl: null,
              pdfUrlExpiry: null,
            },
          }));
        }
      } else {
        console.log('⏭️ Skipping PDF reload (already loaded)');
      }

      return fillRunData;
    } catch (err) {
      console.error('❌ Failed to load fill run:', err);
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          isLoading: false,
          error: getErrorMessage(err),
        },
      }));
      throw err;
    }
  },

  /**
   * Load PDF presigned URL and set up auto-refresh
   */
  loadPdfUrl: async (documentId, getToken) => {
    console.log('📄 Loading PDF URL for document:', documentId);

    try {
      const urlData = await getDocumentDownloadUrl(getToken, documentId);
      console.log('📄 PDF URL response:', urlData);

      if (urlData.url) {
        const expiry = Date.now() + urlData.expires_in * 1000;

        set((state) => ({
          templateFill: {
            ...state.templateFill,
            pdfUrl: urlData.url,
            pdfUrlExpiry: expiry,
          },
        }));

        // Set up auto-refresh timer (10 minutes before expiry)
        get().schedulePdfRefresh(documentId, getToken, urlData.expires_in);

        console.log('✅ PDF URL loaded, expires at:', new Date(expiry));
      } else {
        console.error('❌ No URL in response:', urlData);

        set((state) => ({
          templateFill: {
            ...state.templateFill,
            pdfUrl: null,
            pdfUrlExpiry: null,
            error: 'Failed to load PDF',
          },
        }));
      }
    } catch (err) {
      console.error('❌ Failed to load PDF URL:', err);
      console.error('❌ Error details:', err.response?.data);
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          pdfUrl: null,
          pdfUrlExpiry: null,
          error: 'Failed to load PDF',
        },
      }));
    }
  },

  /**
   * Schedule PDF URL refresh before expiry
   */
  schedulePdfRefresh: (documentId, getToken, expiresIn) => {
    const { pdfRefreshTimer } = get().templateFill;

    // Clear existing timer
    if (pdfRefreshTimer) {
      clearTimeout(pdfRefreshTimer);
    }

    // Refresh 10 minutes before expiry
    const refreshTime = (expiresIn - 600) * 1000; // 600 seconds = 10 minutes

    if (refreshTime > 0) {
      const timer = setTimeout(async () => {
        console.log('🔄 Auto-refreshing PDF URL...');
        await get().loadPdfUrl(documentId, getToken);
      }, refreshTime);

      set((state) => ({
        templateFill: {
          ...state.templateFill,
          pdfRefreshTimer: timer,
        },
      }));
    }
  },

  /**
   * Set selected text from PDF viewer
   */
  setSelectedText: (selectedText) => {
    set((state) => ({
      templateFill: {
        ...state.templateFill,
        selectedText,
      },
    }));
  },

  /**
   * Update extracted data (for manual edits or paste from PDF)
   */
  updateFieldData: async (fillRunId, extractedData, getToken) => {
    console.log('💾 Updating field data for fill run:', fillRunId);

    set((state) => ({
      templateFill: {
        ...state.templateFill,
        isSaving: true,
        error: null,
      },
    }));

    try {
      await updateExtractedData(getToken, fillRunId, extractedData);

      // Update local state
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          fillRun: {
            ...state.templateFill.fillRun,
            extracted_data: extractedData,
          },
          isSaving: false,
        },
      }));

      console.log('✅ Field data updated');
    } catch (err) {
      console.error('❌ Failed to update field data:', err);
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          isSaving: false,
          error: getErrorMessage(err),
        },
      }));
      throw err;
    }
  },

  /**
   * Update field mappings
   */
  updateMappings: async (fillRunId, mappings, getToken) => {
    console.log('🗺️ Updating mappings for fill run:', fillRunId);

    set((state) => ({
      templateFill: {
        ...state.templateFill,
        isSaving: true,
        error: null,
      },
    }));

    try {
      await updateFillMappings(getToken, fillRunId, mappings);

      // Keep local state consistent with UI semantics: 1 mapping per pdf_field_id
      const dedupedByFieldId = new Map();
      for (const mapping of mappings || []) {
        const fieldId = mapping?.pdf_field_id;
        if (!fieldId) continue;
        // Prefer the last mapping provided (mirrors server behavior for user-edited input)
        dedupedByFieldId.set(fieldId, mapping);
      }

      const dedupedMappings = Array.from(dedupedByFieldId.values());

      // Update local state
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          fillRun: {
            ...state.templateFill.fillRun,
            field_mapping: {
              ...state.templateFill.fillRun.field_mapping,
              mappings: dedupedMappings,
            },
            total_fields_mapped: dedupedMappings.length,
          },
          isSaving: false,
        },
      }));

      console.log('✅ Mappings updated');
    } catch (err) {
      console.error('❌ Failed to update mappings:', err);
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          isSaving: false,
          error: getErrorMessage(err),
        },
      }));
      throw err;
    }
  },

  /**
   * Continue fill run after reviewing mappings
   */
  continueProcessing: async (fillRunId, getToken) => {
    console.log('▶️ Continuing fill run:', fillRunId);

    set((state) => ({
      templateFill: {
        ...state.templateFill,
        isLoading: true,
        error: null,
      },
    }));

    try {
      const response = await continueFillRun(getToken, fillRunId);

      // Reload fill run to get updated status
      await get().loadFillRun(fillRunId, getToken);

      console.log('✅ Fill run continued');
      return response;
    } catch (err) {
      console.error('❌ Failed to continue fill run:', err);
      set((state) => ({
        templateFill: {
          ...state.templateFill,
          isLoading: false,
          error: getErrorMessage(err),
        },
      }));
      throw err;
    }
  },

  /**
   * Reset template fill state
   */
  resetTemplateFill: () => {
    const { pdfRefreshTimer } = get().templateFill;

    // Clear refresh timer
    if (pdfRefreshTimer) {
      clearTimeout(pdfRefreshTimer);
    }

    // Cleanup pop-out windows
    get().cleanupPopouts();

    set({
      templateFill: {
        fillRun: null,
        fillRunId: null,
        pdfUrl: null,
        pdfUrlExpiry: null,
        pdfRefreshTimer: null,
        selectedText: null,
        pdfPopoutWindow: null,
        excelPopoutWindow: null,
        isLoading: false,
        isSaving: false,
        error: null,
      },
    });
  },

  /**
   * Clear error
   */
  clearTemplateFillError: () => {
    set((state) => ({
      templateFill: {
        ...state.templateFill,
        error: null,
      },
    }));
  },

  /**
   * Register PDF pop-out window
   */
  registerPdfPopout: (windowRef) => {
    console.log('📺 Registering PDF pop-out window');
    set((state) => ({
      templateFill: {
        ...state.templateFill,
        pdfPopoutWindow: windowRef,
      },
    }));
  },

  /**
   * Register Excel pop-out window
   */
  registerExcelPopout: (windowRef) => {
    console.log('📊 Registering Excel pop-out window');
    set((state) => ({
      templateFill: {
        ...state.templateFill,
        excelPopoutWindow: windowRef,
      },
    }));
  },

  /**
   * Navigate PDF to page in all windows (main + pop-outs)
   */
  navigatePdfToPage: (pageNumber) => {
    console.log('🔄 Navigating PDF to page', pageNumber, 'across all windows');

    const { pdfPopoutWindow } = get().templateFill;

    // Send message to PDF pop-out if open
    if (pdfPopoutWindow && !pdfPopoutWindow.closed) {
      pdfPopoutWindow.postMessage(
        { type: 'NAVIGATE_TO_PAGE', page: pageNumber },
        '*'
      );
    }
  },

  /**
   * Cleanup pop-out windows
   */
  cleanupPopouts: () => {
    const { pdfPopoutWindow, excelPopoutWindow } = get().templateFill;

    // Close windows if still open
    if (pdfPopoutWindow && !pdfPopoutWindow.closed) {
      pdfPopoutWindow.close();
    }
    if (excelPopoutWindow && !excelPopoutWindow.closed) {
      excelPopoutWindow.close();
    }

    // Clear references
    set((state) => ({
      templateFill: {
        ...state.templateFill,
        pdfPopoutWindow: null,
        excelPopoutWindow: null,
      },
    }));
  },
});
