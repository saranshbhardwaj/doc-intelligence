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
// Track active streams to prevent duplicate EventSource instances per job
const _activeStreams = new Map(); // jobId -> { eventSource, callbacks }

export async function streamProgress(jobId, getToken, { onProgress, onComplete, onError, onEnd, autoReconnect = true }) {
    const baseURL = api.defaults.baseURL || '';

    // Get auth token and pass as query parameter (EventSource doesn't support headers)
    const token = await getToken();
    const url = `${baseURL}/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`;

    // If stream already exists, reuse and just update callbacks
    if (_activeStreams.has(jobId)) {
        const existing = _activeStreams.get(jobId);
        existing.callbacks = { onProgress, onComplete, onError, onEnd };
        return () => {
            try { existing.eventSource.close(); } catch (_) {}
            _activeStreams.delete(jobId);
        };
    }

    const eventSource = new EventSource(url);
    let streamEnded = false;
    let isCleaningUp = false;  // Prevent duplicate cleanup
    let receivedDomainError = false; // True if backend emitted an application error event
    let terminalFailed = false; // True if error is non-retryable (retryable === false)
    let lastProgressTime = Date.now();

    const cleanup = () => {
        if (isCleaningUp) return;
        isCleaningUp = true;
        streamEnded = true;

        console.log('[SSE Frontend] Cleaning up EventSource');
        try {
            eventSource.close();
        } catch (err) {
            console.error('[SSE Frontend] Error closing EventSource:', err);
        }
        _activeStreams.delete(jobId);
    };

    eventSource.addEventListener('progress', (event) => {
        const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
        try {
            const data = JSON.parse(event.data);
            lastProgressTime = Date.now();
            callbacks.onProgress?.(data);
        } catch (err) {
            console.error('Failed to parse progress event:', err);
        }
    });

    eventSource.addEventListener('complete', (event) => {
        const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
        try {
            const data = JSON.parse(event.data);
            console.log('[SSE Frontend] 🎉 Complete event received:', data);
            callbacks.onComplete?.(data);
        } catch (err) {
            console.error('Failed to parse complete event:', err);
        }
    });

    eventSource.addEventListener('end', (event) => {
        const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
        streamEnded = true;  // Set FIRST before any other operations
        try {
            const data = JSON.parse(event.data);
            console.log('[SSE Frontend] End event data:', data);
            callbacks.onEnd?.(data);
        } catch (err) {
            console.error('Failed to parse end event:', err);
        } finally {
            // Cleanup AFTER callback
            cleanup();
        }
    });

    eventSource.addEventListener('error', (event) => {
        // Domain error (backend emitted SSE 'error' event with JSON payload)
        if (event.data) {
            try {
                const raw = JSON.parse(event.data);
                receivedDomainError = true;
                const normalized = {
                    message: raw.message,
                    stage: raw.stage,
                    type: raw.type || raw.error_type,
                    isRetryable: raw.retryable ?? raw.is_retryable ?? false,
                };
                if (!normalized.isRetryable) {
                    terminalFailed = true;
                }
                const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
                callbacks.onError?.(normalized);
                // We allow the dedicated 'end' event to perform cleanup.
            } catch (err) {
                console.error('Failed to parse domain error event:', err);
            }
        }
    });

    let reconnectAttempts = 0;
    const maxReconnect = 5;
    const baseDelay = 1000;

    eventSource.onerror = (err) => {
        console.log(`[SSE Frontend] onerror fired: streamEnded=${streamEnded}, readyState=${eventSource.readyState}`);

        // If domain error already received (application failure) or graceful end, skip transport reconnect
        if (isCleaningUp || streamEnded || receivedDomainError || terminalFailed) {
            console.log('[SSE Frontend] ✅ Ignoring transport onerror (terminal or ended)');
            return;
        }

        // Treat as connection issue only if no domain error yet
        console.error('[SSE Frontend] ❌ Connection error detected (no domain error yet):', err);
        const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
        callbacks.onError?.({
            message: 'Lost connection to server',
            type: 'connection_error',
            isRetryable: true,
        });

        cleanup();

        // Simple heuristic: if we've never seen progress (still at initial stage) limit reconnect attempts to 2
        const strictLimit = (Date.now() - lastProgressTime) < 5000; // no progress within 5s window
        const allowedReconnects = strictLimit ? 2 : maxReconnect;

        if (autoReconnect && reconnectAttempts < allowedReconnects) {
            reconnectAttempts += 1;
            const delay = baseDelay * Math.pow(2, reconnectAttempts - 1); // exponential backoff
            console.log(`[SSE Frontend] Attempting reconnect #${reconnectAttempts} (limit ${allowedReconnects}) in ${delay}ms`);
            setTimeout(() => {
                streamProgress(jobId, getToken, { onProgress, onComplete, onError, onEnd, autoReconnect });
            }, delay);
        } else if (reconnectAttempts >= allowedReconnects) {
            console.error('[SSE Frontend] Max reconnection attempts reached');
            callbacks.onError?.({
                message: 'Failed to reconnect after multiple attempts',
                type: 'connection_error',
                isRetryable: false,
            });
        }
    };

    _activeStreams.set(jobId, { eventSource, callbacks: { onProgress, onComplete, onError, onEnd } });

    // Return cleanup function (explicit cancel)
    return cleanup;
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
