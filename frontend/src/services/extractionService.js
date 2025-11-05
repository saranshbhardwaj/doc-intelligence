/**
 * Extraction Service
 *
 * Handles document extraction API calls and Server-Sent Events (SSE) streaming
 * for real-time progress updates.
 *
 * NOTE: All functions require authentication via Clerk.
 * Pass the getToken function from useAuth() hook to authenticated functions.
 */

import api, { createAuthenticatedApi } from '../api';

/**
 * Upload a document for extraction (REQUIRES AUTHENTICATION)
 *
 * @param {File} file - The PDF file to extract
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {string} context - Optional context to guide extraction (max 500 chars)
 * @returns {Promise<Object>} Response with either immediate result (cache hit) or job details
 *
 * Response types:
 * - Cache HIT (200 OK): { success: true, data: {...}, metadata: {...}, from_cache: true }
 * - Cache MISS (202 Accepted): { success: true, job_id, extraction_id, stream_url, result_url, from_cache: false }
 *
 * Usage:
 * ```jsx
 * const { getToken } = useAuth();
 * const result = await uploadDocument(file, getToken, "Focus on SaaS metrics");
 * ```
 */
export async function uploadDocument(file, getToken, context = "") {
    const authenticatedApi = createAuthenticatedApi(getToken);

    const formData = new FormData();
    formData.append('file', file);
    if (context && context.trim()) {
        formData.append('context', context.trim());
    }

    const response = await authenticatedApi.post('/api/extract', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
    });

    return response.data;
}

/**
 * Stream job progress via Server-Sent Events (SSE)
 *
 * NOTE: EventSource doesn't support custom headers, so auth token is passed as query parameter
 *
 * @param {string} jobId - The job ID to stream progress for
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {Object} callbacks - Event handler callbacks
 * @param {Function} callbacks.onProgress - Called with progress updates
 * @param {Function} callbacks.onComplete - Called when job completes
 * @param {Function} callbacks.onError - Called on error
 * @returns {Function} Cleanup function to close the connection
 *
 * Progress event structure:
 * {
 *   status: "parsing" | "chunking" | "summarizing" | "extracting" | "completed",
 *   progress_percent: 0-100,
 *   message: "User-friendly status message",
 *   current_stage: "parsing",
 *   parsing_completed: true,
 *   chunking_completed: false,
 *   ...
 * }
 *
 * Error event structure:
 * {
 *   error_stage: "parsing",
 *   error_message: "Detailed error message",
 *   error_type: "parsing_error" | "llm_error" | "chunking_error" | "unknown_error",
 *   is_retryable: true
 * }
 */
export async function streamProgress(jobId, getToken, { onProgress, onComplete, onError, onEnd }) {
    const baseURL = api.defaults.baseURL || '';

    // Get auth token and pass as query parameter (EventSource doesn't support headers)
    const token = await getToken();
    const url = `${baseURL}/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`;

    const eventSource = new EventSource(url);
    let streamEnded = false;

    eventSource.addEventListener('progress', (event) => {
        try {
            const data = JSON.parse(event.data);
            onProgress?.(data);
        } catch (err) {
            console.error('Failed to parse progress event:', err);
        }
    });

    eventSource.addEventListener('complete', (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log('[SSE Frontend] 🎉 Complete event received:', data);
            onComplete?.(data);
            // Don't close yet; wait for explicit end event so we avoid firing onerror noise
        } catch (err) {
            console.error('Failed to parse complete event:', err);
        }
    });

    eventSource.addEventListener('end', (event) => {
        streamEnded = true;  // Set FIRST before any other operations
        try {
            const data = JSON.parse(event.data);
            console.log('[SSE Frontend] End event data:', data);
            onEnd?.(data);
        } catch (err) {
            console.error('Failed to parse end event:', err);
        } finally {
            console.log('[SSE Frontend] Closing EventSource');
            eventSource.close();
        }
    });

    eventSource.addEventListener('error', (event) => {
        // Only process error events that have data (custom error events from backend)
        if (event.data) {
            try {
                const data = JSON.parse(event.data);
                onError?.(data);
                // Wait for end event following error to close
            } catch (err) {
                console.error('Failed to parse error event:', err);
            }
        }
    });

    eventSource.onerror = (err) => {
        console.log(`[SSE Frontend] onerror fired: streamEnded=${streamEnded}, readyState=${eventSource.readyState}`);

        // Ignore synthetic error fired on normal close after end event
        if (streamEnded && eventSource.readyState === 2) {
            console.log('[SSE Frontend] ✅ Stream ended gracefully (ignoring onerror)');
            return; // already closed
        }

        // Real connection issue (no end yet)
        console.error('[SSE Frontend] ❌ Real connection error detected:', err);
        onError?.({
            error_message: 'Lost connection to server',
            error_type: 'connection_error',
            is_retryable: true
        });
        try { eventSource.close(); } catch (_) {}
    };

    // Return cleanup function
    return () => {
        streamEnded = true;
        try { eventSource.close(); } catch (_) {}
    };
}

/**
 * Fetch the final extraction result (REQUIRES AUTHENTICATION)
 *
 * @param {string} extractionId - The extraction ID
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @returns {Promise<Object>} Extraction result with data and metadata
 *
 * Response structure:
 * {
 *   success: true,
 *   data: { fund_name: "...", investment_structure: {...}, ... },
 *   metadata: { extraction_id, filename, pages, processing_time_ms, cost_usd, ... },
 *   from_cache: false
 * }
 */
export async function fetchExtractionResult(extractionId, getToken) {
    const authenticatedApi = createAuthenticatedApi(getToken);
    const response = await authenticatedApi.get(`/api/extractions/${extractionId}`);
    return response.data;
}

/**
 * Retry a failed job from the last successful stage (REQUIRES AUTHENTICATION)
 *
 * @param {string} jobId - The job ID to retry
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @returns {Promise<Object>} New job details
 *
 * Response structure:
 * {
 *   success: true,
 *   job_id: "new-job-id",
 *   extraction_id: "same-extraction-id",
 *   message: "Job retry initiated from stage: chunking",
 *   resume_from_stage: "chunking"
 * }
 */
export async function retryJob(jobId, getToken) {
    const authenticatedApi = createAuthenticatedApi(getToken);
    const response = await authenticatedApi.post(`/api/jobs/${jobId}/retry`);
    return response.data;
}

/**
 * Get current job status (polling alternative to SSE) - REQUIRES AUTHENTICATION
 *
 * @param {string} jobId - The job ID
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @returns {Promise<Object>} Current job state
 */
export async function getJobStatus(jobId, getToken) {
    const authenticatedApi = createAuthenticatedApi(getToken);
    const response = await authenticatedApi.get(`/api/jobs/${jobId}/status`);
    return response.data;
}
