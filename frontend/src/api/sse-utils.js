/**
 * Unified SSE (Server-Sent Events) Utility
 *
 * Provides a centralized way to stream job progress from backend
 * Used by both workflows and extractions which share the same endpoint:
 * GET /api/jobs/{jobId}/stream
 *
 * Event Types:
 * - progress: Job progress updates (status, percent, message, stage)
 * - complete: Job completed successfully
 * - error: Job failed with error details
 * - end: Stream termination (always sent last)
 */

import { api } from "./client";

// Track active streams to prevent duplicate EventSource instances per job
const _activeStreams = new Map(); // jobId -> { eventSource, callbacks }

/**
 * Stream job progress via Server-Sent Events (SSE)
 *
 * NOTE: EventSource doesn't support custom headers, so auth token is passed as query parameter
 *
 * @param {string} jobId - The job ID to stream progress for
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {Object} options - Configuration options
 * @param {Function} options.onProgress - Called with progress updates
 * @param {Function} options.onComplete - Called when job completes
 * @param {Function} options.onError - Called on error
 * @param {Function} options.onEnd - Called when stream ends
 * @param {boolean} options.autoReconnect - Auto-reconnect on connection loss (default: true)
 * @param {boolean} options.fetchInitialState - Fetch initial job state before SSE (default: false)
 * @param {Function} options.getJobStatus - Function to fetch job status (required if fetchInitialState=true)
 * @returns {Promise<Function>} Cleanup function to close the connection
 *
 * Progress event structure:
 * {
 *   status: "queued" | "running" | "completed" | "failed",
 *   progress_percent: 0-100,
 *   message: "User-friendly status message",
 *   current_stage: "processing",
 *   details: {...}
 * }
 *
 * Complete event structure:
 * {
 *   message: "Job completed successfully",
 *   run_id: "...",
 *   artifact: {...}
 * }
 *
 * Error event structure:
 * {
 *   message: "Error description",
 *   stage: "parsing" | "chunking" | "embedding" | etc,
 *   type: "validation_error" | "timeout" | etc,
 *   isRetryable: boolean
 * }
 */
export async function streamJobProgress(
  jobId,
  getToken,
  {
    onProgress,
    onComplete,
    onError,
    onEnd,
    autoReconnect = true,
    fetchInitialState = false,
    getJobStatus = null,
  }
) {
  const baseURL = api.defaults.baseURL || "";

  // Get auth token and pass as query parameter (EventSource doesn't support headers)
  const token = await getToken();
  const url = `${baseURL}/api/jobs/${jobId}/stream?token=${encodeURIComponent(
    token
  )}`;

  // If stream already exists for this job, reuse and just update callbacks
  if (_activeStreams.has(jobId)) {
    console.log(`[SSE Utils] Reusing existing stream for job ${jobId}`);
    const existing = _activeStreams.get(jobId);
    existing.callbacks = { onProgress, onComplete, onError, onEnd };
    return () => {
      try {
        existing.eventSource.close();
      } catch (_) {}
      _activeStreams.delete(jobId);
    };
  }

  // Fetch initial state before starting SSE if requested (useful for reconnection)
  if (fetchInitialState && getJobStatus) {
    try {
      const initialState = await getJobStatus(jobId, getToken);
      console.log("[SSE Utils] Fetched initial job state:", initialState);

      // Emit initial state to populate UI immediately
      if (initialState.status === "completed") {
        onComplete?.({
          message: initialState.message || "Job completed successfully",
          run_id: initialState.run_id,
          extraction_id: initialState.extraction_id,
        });
        onEnd?.({ reason: "completed", job_id: jobId });
        return () => {}; // No cleanup needed, job already done
      } else if (initialState.status === "failed") {
        onError?.({
          message: initialState.error_message || "Job failed",
          stage: initialState.error_stage,
          type: initialState.error_type,
          isRetryable: initialState.is_retryable ?? false,
        });
        onEnd?.({ reason: "failed", job_id: jobId });
        return () => {};
      } else {
        // In progress - send initial progress event
        onProgress?.({
          status: initialState.status,
          current_stage: initialState.current_stage,
          progress_percent: initialState.progress_percent,
          message: initialState.message,
          details: initialState.details || {},
        });
      }
    } catch (err) {
      console.error("[SSE Utils] Failed to fetch initial state:", err);
      // Continue to SSE connection anyway
    }
  }

  console.log(`[SSE Utils] Creating new EventSource for job ${jobId}`);
  const eventSource = new EventSource(url);
  let streamEnded = false;
  let isCleaningUp = false;
  let receivedDomainError = false;
  let terminalFailed = false;
  let lastProgressTime = Date.now();

  const cleanup = () => {
    if (isCleaningUp) return;
    isCleaningUp = true;
    streamEnded = true;

    console.log(`[SSE Utils] Cleaning up EventSource for job ${jobId}`);
    try {
      eventSource.close();
    } catch (err) {
      console.error("[SSE Utils] Error closing EventSource:", err);
    }
    _activeStreams.delete(jobId);
  };

  // Progress event handler
  eventSource.addEventListener("progress", (event) => {
    const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
    try {
      const data = JSON.parse(event.data);
      lastProgressTime = Date.now(); // Track last progress for reconnect heuristics
      callbacks.onProgress?.(data);
    } catch (err) {
      console.error("[SSE Utils] Failed to parse progress event:", err);
    }
  });

  // Complete event handler
  eventSource.addEventListener("complete", (event) => {
    const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
    try {
      const data = JSON.parse(event.data);
      console.log("[SSE Utils] 🎉 Complete event received:", data);
      callbacks.onComplete?.(data);
    } catch (err) {
      console.error("[SSE Utils] Failed to parse complete event:", err);
    }
  });

  // End event handler (stream termination)
  eventSource.addEventListener("end", (event) => {
    const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
    streamEnded = true;
    try {
      const data = JSON.parse(event.data);
      console.log("[SSE Utils] End event data:", data);
      callbacks.onEnd?.(data);
    } catch (err) {
      console.error("[SSE Utils] Failed to parse end event:", err);
    } finally {
      cleanup();
    }
  });

  // Domain error event handler (backend-emitted error event with JSON payload)
  eventSource.addEventListener("error", (event) => {
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
        // We allow the dedicated 'end' event to perform cleanup
      } catch (err) {
        console.error("[SSE Utils] Failed to parse domain error event:", err);
      }
    }
  });

  // Transport error handler with auto-reconnect support
  let reconnectAttempts = 0;
  const maxReconnect = 5;
  const baseDelay = 1000; // 1 second base delay

  eventSource.onerror = (err) => {
    console.log(
      `[SSE Utils] onerror fired: streamEnded=${streamEnded}, readyState=${eventSource.readyState}`
    );

    // If domain error already received (application failure) or graceful end, skip transport reconnect
    if (isCleaningUp || streamEnded || receivedDomainError || terminalFailed) {
      console.log(
        "[SSE Utils] ✅ Ignoring transport onerror (terminal or ended)"
      );
      return;
    }

    // Treat as connection issue only if no domain error yet
    console.error(
      "[SSE Utils] ❌ Connection error detected (no domain error yet):",
      err
    );
    const { callbacks } = _activeStreams.get(jobId) || { callbacks: {} };
    callbacks.onError?.({
      message: "Lost connection to server",
      type: "connection_error",
      isRetryable: true,
    });

    cleanup();

    // Auto-reconnect with exponential backoff
    if (autoReconnect) {
      // Simple heuristic: if we've never seen progress (still at initial stage) limit reconnect attempts
      const strictLimit = Date.now() - lastProgressTime < 5000; // no progress within 5s
      const allowedReconnects = strictLimit ? 2 : maxReconnect;

      if (reconnectAttempts < allowedReconnects) {
        reconnectAttempts += 1;
        const delay = baseDelay * Math.pow(2, reconnectAttempts - 1); // exponential backoff
        console.log(
          `[SSE Utils] Attempting reconnect #${reconnectAttempts}/${allowedReconnects} in ${delay}ms`
        );
        setTimeout(() => {
          streamJobProgress(jobId, getToken, {
            onProgress,
            onComplete,
            onError,
            onEnd,
            autoReconnect,
            fetchInitialState: false, // Don't fetch again on reconnect
            getJobStatus,
          });
        }, delay);
      } else {
        console.error("[SSE Utils] Max reconnection attempts reached");
        callbacks.onError?.({
          message: "Failed to reconnect after multiple attempts",
          type: "connection_error",
          isRetryable: false,
        });
      }
    }
  };

  // Store stream reference
  _activeStreams.set(jobId, {
    eventSource,
    callbacks: { onProgress, onComplete, onError, onEnd },
  });

  // Return cleanup function (for explicit cancel)
  return cleanup;
}

/**
 * Get count of active SSE streams (for debugging)
 */
export function getActiveStreamCount() {
  return _activeStreams.size;
}

/**
 * Close all active streams (useful for cleanup on logout)
 */
export function closeAllStreams() {
  console.log(`[SSE Utils] Closing all ${_activeStreams.size} active streams`);
  _activeStreams.forEach((stream) => {
    try {
      stream.eventSource.close();
    } catch (err) {
      console.error("[SSE Utils] Error closing stream:", err);
    }
  });
  _activeStreams.clear();
}
