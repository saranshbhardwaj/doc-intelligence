/**
 * Workflows API helpers
 */

import { api, createAuthenticatedApi } from "./client";

// Track active streams to prevent duplicate EventSource instances per job
const _activeWorkflowStreams = new Map(); // jobId -> { eventSource, callbacks }

export async function getRun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/workflows/runs/${runId}`);
  return response.data;
}

export async function getRunArtifact(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  try {
    const response = await api.get(`/api/workflows/runs/${runId}/artifact`);
    return response.data;
  } catch {
    // Artifact may not exist; return null to match previous behavior
    return null;
  }
}

export async function listTemplates(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/workflows/templates`);
  return response.data;
}

export async function listRuns(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/workflows/runs`);
  return response.data;
}

/**
 * Export generator. Returns the raw axios response so caller can inspect
 * response.data (may be { url } or a binary blob depending on server)
 */
export async function exportRun(getToken, runId, format, delivery = "url") {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/export/generate?delivery=${encodeURIComponent(delivery)}`,
    { run_id: runId, format },
    { responseType: "json" }
  );
  return response;
}

/**
 * Delete a workflow run
 */
export async function deleteRun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/workflows/runs/${runId}`);
  return response.data;
}

/**
 * Re-run a workflow with optionally modified variables and prompt
 * @param {Function} getToken - Auth token getter
 * @param {string} runId - Original run ID to copy from
 * @param {Object} params - Override parameters
 * @param {Array<string>} params.document_ids - Optional document IDs override
 * @param {string} params.collection_id - Optional collection ID override
 * @param {Object} params.variables - Variables to merge with original
 * @param {string} params.strategy - Optional strategy override
 * @param {string} params.custom_prompt - Optional custom prompt
 */
export async function rerunWorkflow(getToken, runId, params = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/workflows/runs/${runId}/rerun`, params);
  return response.data;
}

/**
 * Stream workflow job progress via Server-Sent Events (SSE)
 *
 * NOTE: EventSource doesn't support custom headers, so auth token is passed as query parameter
 *
 * @param {string} jobId - The job ID to stream progress for
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {Object} callbacks - Event handler callbacks
 * @param {Function} callbacks.onProgress - Called with progress updates
 * @param {Function} callbacks.onComplete - Called when job completes
 * @param {Function} callbacks.onError - Called on error
 * @param {Function} callbacks.onEnd - Called when stream ends
 * @returns {Function} Cleanup function to close the connection
 *
 * Progress event structure:
 * {
 *   status: "queued" | "running" | "completed" | "failed",
 *   progress_percent: 0-100,
 *   message: "User-friendly status message",
 *   current_stage: "processing",
 *   ...
 * }
 */
export async function streamWorkflowProgress(jobId, getToken, { onProgress, onComplete, onError, onEnd }) {
  const baseURL = api.defaults.baseURL || '';

  // Get auth token and pass as query parameter (EventSource doesn't support headers)
  const token = await getToken();
  const url = `${baseURL}/api/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`;

  // If stream already exists, reuse and just update callbacks
  if (_activeWorkflowStreams.has(jobId)) {
    const existing = _activeWorkflowStreams.get(jobId);
    existing.callbacks = { onProgress, onComplete, onError, onEnd };
    return () => {
      try { existing.eventSource.close(); } catch (_) {}
      _activeWorkflowStreams.delete(jobId);
    };
  }

  const eventSource = new EventSource(url);
  let streamEnded = false;
  let isCleaningUp = false;

  const cleanup = () => {
    if (isCleaningUp) return;
    isCleaningUp = true;
    streamEnded = true;

    console.log('[Workflow SSE] Cleaning up EventSource');
    try {
      eventSource.close();
    } catch (err) {
      console.error('[Workflow SSE] Error closing EventSource:', err);
    }
    _activeWorkflowStreams.delete(jobId);
  };

  eventSource.addEventListener('progress', (event) => {
    const { callbacks } = _activeWorkflowStreams.get(jobId) || { callbacks: {} };
    try {
      const data = JSON.parse(event.data);
      callbacks.onProgress?.(data);
    } catch (err) {
      console.error('[Workflow SSE] Failed to parse progress event:', err);
    }
  });

  eventSource.addEventListener('complete', (event) => {
    const { callbacks } = _activeWorkflowStreams.get(jobId) || { callbacks: {} };
    try {
      const data = JSON.parse(event.data);
      console.log('[Workflow SSE] 🎉 Complete event received:', data);
      callbacks.onComplete?.(data);
    } catch (err) {
      console.error('[Workflow SSE] Failed to parse complete event:', err);
    }
  });

  eventSource.addEventListener('end', (event) => {
    const { callbacks } = _activeWorkflowStreams.get(jobId) || { callbacks: {} };
    streamEnded = true;
    try {
      const data = JSON.parse(event.data);
      console.log('[Workflow SSE] End event data:', data);
      callbacks.onEnd?.(data);
    } catch (err) {
      console.error('[Workflow SSE] Failed to parse end event:', err);
    } finally {
      cleanup();
    }
  });

  eventSource.addEventListener('error', (event) => {
    // Domain error (backend emitted SSE 'error' event with JSON payload)
    if (event.data) {
      try {
        const raw = JSON.parse(event.data);
        const normalized = {
          message: raw.message,
          stage: raw.stage,
          type: raw.type || raw.error_type,
          isRetryable: raw.retryable ?? raw.is_retryable ?? false,
        };
        const { callbacks } = _activeWorkflowStreams.get(jobId) || { callbacks: {} };
        callbacks.onError?.(normalized);
      } catch (err) {
        console.error('[Workflow SSE] Failed to parse domain error event:', err);
      }
    }
  });

  eventSource.onerror = (err) => {
    if (isCleaningUp || streamEnded) {
      console.log('[Workflow SSE] ✅ Ignoring transport onerror (terminal or ended)');
      return;
    }

    console.error('[Workflow SSE] ❌ Connection error detected:', err);
    const { callbacks } = _activeWorkflowStreams.get(jobId) || { callbacks: {} };
    callbacks.onError?.({
      message: 'Lost connection to server',
      type: 'connection_error',
      isRetryable: true,
    });

    cleanup();
  };

  _activeWorkflowStreams.set(jobId, { eventSource, callbacks: { onProgress, onComplete, onError, onEnd } });

  // Return cleanup function (explicit cancel)
  return cleanup;
}
