/**
 * Extraction Slice for Zustand Store
 *
 * Manages document extraction state including:
 * - Upload and processing
 * - Progress tracking via SSE
 * - Results and errors
 * - Connection persistence across navigation
 */

import { uploadDocument, retryExtraction, streamProgress, fetchExtractionResult } from '../../api';

/**
 * Get safe error message from error object
 * (Normalized errors from apiErrorHandler have .message)
 */
const getErrorMessage = (error) => {
  return error?.message || "An unexpected error occurred";
};

export const createExtractionSlice = (set, get) => ({
  // ========== State ==========
  extraction: {
    // Processing state
    isProcessing: false,

    // Job identifiers
    jobId: null,
    extractionId: null,

    // Progress tracking
    progress: {
      status: 'idle',
      percent: 0,
      message: '',
      stage: 'idle',
      stages: {
        parsing: false,
        chunking: false,
        summarizing: false,
        extracting: false,
      },
    },

    // Results
    result: null,
    error: null,

    // SSE cleanup function
    cleanup: null,
  },

  // ========== Actions ==========

  /**
   * Upload document and start extraction
   */
  uploadDocument: async (file, getToken, context = '') => {
    const { resetExtraction, setProgress, setResult, setError, setProcessing } = get();

    resetExtraction();
    setProcessing(true);

    try {
      const response = await uploadDocument(file, getToken, context);
      console.log('📤 Upload response:', response);

      // Handle cache hit or duplicate document (no async processing needed)
      if (response.from_cache || response.from_history) {
        setResult(response);
        const message = response.from_history
          ? 'Retrieved from your extraction history'
          : 'Retrieved from cache';
        setProgress({
          status: 'completed',
          percent: 100,
          message: message,
          stage: 'completed',
          stages: { parsing: true, chunking: true, summarizing: true, extracting: true }
        });
        setProcessing(false);
        return response;
      }

      // Start async processing with SSE
      const jobId = response.job_id;
      const extractionId = response.extraction_id;

      set((state) => ({
        extraction: {
          ...state.extraction,
          jobId,
          extractionId,
        },
      }));

      console.log('🚀 Starting SSE stream for job:', jobId);

      // Start SSE stream
      const cleanup = await streamProgress(jobId, getToken, {
        onProgress: (data) => {
          console.log('📊 Progress update:', data);
          setProgress({
            status: data.status,
            percent: data.progress_percent,
            message: data.message,
            stage: data.current_stage,
            stages: {
              parsing: data.parsing_completed || false,
              chunking: data.chunking_completed || false,
              summarizing: data.summarizing_completed || false,
              extracting: data.extracting_completed || false,
            },
          });
        },
        onComplete: async (data) => {
          console.log('✅ Extraction completed:', data);
          setProgress({
            status: 'completed',
            percent: 100,
            message: 'Extraction completed successfully',
            stage: 'completed',
            stages: { parsing: true, chunking: true, summarizing: true, extracting: true },
          });
        },
        onError: (errorData) => {
          console.error('❌ Extraction error:', errorData);
          const errorMsg = typeof errorData === 'string'
            ? errorData
            : (errorData?.message || 'Extraction failed');
          setError(errorMsg);
          setProcessing(false);
        },
        onEnd: async (data) => {
          console.log('🏁 SSE stream ended:', data);
          if (data?.reason === 'completed') {
            const extractionResult = await fetchExtractionResult(extractionId, getToken);
            setResult(extractionResult);
          }
          setProcessing(false);
        },
      });

      // Store cleanup function
      set((state) => ({
        extraction: {
          ...state.extraction,
          cleanup,
        },
      }));

      return response;
    } catch (err) {
      console.error('Upload failed:', err);
      setError(getErrorMessage(err));
      setProcessing(false);
      throw err;
    }
  },

  /**
   * Retry failed extraction
   */
  retryExtraction: async (extractionId, getToken) => {
    const { resetExtraction, setProgress, setResult, setError, setProcessing } = get();

    resetExtraction();
    setProcessing(true);

    try {
      const response = await retryExtraction(extractionId, getToken);
      const jobId = response.job_id;

      set((state) => ({
        extraction: {
          ...state.extraction,
          jobId,
          extractionId,
        },
      }));

      console.log('🔄 Starting retry with job:', jobId);

      // Start SSE stream for retry
      const cleanup = await streamProgress(jobId, getToken, {
        onProgress: (data) => {
          setProgress({
            status: data.status,
            percent: data.progress_percent,
            message: data.message,
            stage: data.current_stage,
            stages: {
              parsing: data.parsing_completed || false,
              chunking: data.chunking_completed || false,
              summarizing: data.summarizing_completed || false,
              extracting: data.extracting_completed || false,
            },
          });
        },
        onComplete: async (data) => {
          setProgress({
            status: 'completed',
            percent: 100,
            message: 'Retry completed successfully',
            stage: 'completed',
            stages: { parsing: true, chunking: true, summarizing: true, extracting: true },
          });
        },
        onError: (errorData) => {
          const errorMsg = typeof errorData === 'string'
            ? errorData
            : (errorData?.message || 'Extraction failed');
          setError(errorMsg);
          setProcessing(false);
        },
        onEnd: async (data) => {
          if (data?.reason === 'completed') {
            const extractionResult = await fetchExtractionResult(extractionId, getToken);
            setResult(extractionResult);
          }
          setProcessing(false);
        },
      });

      set((state) => ({
        extraction: {
          ...state.extraction,
          cleanup,
        },
      }));

      return response;
    } catch (err) {
      console.error('Retry failed:', err);
      setError(getErrorMessage(err));
      setProcessing(false);
      throw err;
    }
  },

  /**
   * Reconnect to active extraction after navigation
   */
  reconnectExtraction: async (getToken) => {
    const { setProgress, setResult, setError, setProcessing } = get();
    const { jobId, extractionId } = get().extraction;

    if (!jobId || !extractionId) {
      console.log('❌ No active extraction to reconnect');
      return;
    }

    console.log('🔄 Reconnecting to extraction:', jobId);
    setProcessing(true);

    try {
      const cleanup = await streamProgress(jobId, getToken, {
        onProgress: (data) => {
          setProgress({
            status: data.status,
            percent: data.progress_percent,
            message: data.message,
            stage: data.current_stage,
            stages: {
              parsing: data.parsing_completed || false,
              chunking: data.chunking_completed || false,
              summarizing: data.summarizing_completed || false,
              extracting: data.extracting_completed || false,
            },
          });
        },
        onComplete: async (data) => {
          setProgress({
            status: 'completed',
            percent: 100,
            message: 'Extraction completed successfully',
            stage: 'completed',
            stages: { parsing: true, chunking: true, summarizing: true, extracting: true },
          });
        },
        onError: (errorData) => {
          const errorMsg = typeof errorData === 'string'
            ? errorData
            : (errorData?.message || 'Extraction failed');
          setError(errorMsg);
          setProcessing(false);
        },
        onEnd: async (data) => {
          if (data?.reason === 'completed') {
            const extractionResult = await fetchExtractionResult(extractionId, getToken);
            setResult(extractionResult);
          }
          setProcessing(false);
        },
      });

      set((state) => ({
        extraction: {
          ...state.extraction,
          cleanup,
        },
      }));
    } catch (err) {
      console.error('Reconnection failed:', err);
      setError(getErrorMessage(err));
      setProcessing(false);
    }
  },

  /**
   * Cancel ongoing extraction
   */
  cancelExtraction: () => {
    const { cleanup } = get().extraction;

    if (cleanup) {
      cleanup();
    }

    set((state) => ({
      extraction: {
        ...state.extraction,
        isProcessing: false,
        cleanup: null,
      },
    }));
  },

  /**
   * Reset extraction state
   */
  resetExtraction: () => {
    const { cleanup } = get().extraction;

    if (cleanup) {
      cleanup();
    }

    set({
      extraction: {
        isProcessing: false,
        jobId: null,
        extractionId: null,
        progress: {
          status: 'idle',
          percent: 0,
          message: '',
          stage: 'idle',
          stages: {
            parsing: false,
            chunking: false,
            summarizing: false,
            extracting: false,
          },
        },
        result: null,
        error: null,
        cleanup: null,
      },
    });
  },

  // ========== Utility Setters ==========

  setProgress: (progress) => {
    set((state) => ({
      extraction: {
        ...state.extraction,
        progress: {
          ...state.extraction.progress,
          ...progress,
        },
      },
    }));
  },

  setResult: (result) => {
    set((state) => ({
      extraction: {
        ...state.extraction,
        result,
      },
    }));
  },

  setError: (error) => {
    set((state) => ({
      extraction: {
        ...state.extraction,
        error,
      },
    }));
  },

  setProcessing: (isProcessing) => {
    set((state) => ({
      extraction: {
        ...state.extraction,
        isProcessing,
      },
    }));
  },
});
