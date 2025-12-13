/**
 * Workflows API helpers
 */

import { api, createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

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
 * Export workflow run to Word, Excel, or PDF.
 *
 * New endpoint: POST /api/workflows/runs/{runId}/export
 *
 * @param {Function} getToken - Auth token getter
 * @param {string} runId - Run ID to export
 * @param {string} format - Export format ('word', 'excel', 'pdf')
 * @param {string} delivery - Delivery mode ('stream' or 'url')
 * @returns {Promise} Response with file or URL
 */
export async function exportRun(getToken, runId, format, delivery = "url") {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/workflows/runs/${runId}/export?format=${encodeURIComponent(format)}&delivery=${encodeURIComponent(delivery)}`,
    {},
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
 * This is a wrapper around the unified streamJobProgress utility.
 * Uses the same endpoint as extraction.js: GET /api/jobs/{jobId}/stream
 *
 * @param {string} jobId - The job ID to stream progress for
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {Object} callbacks - Event handler callbacks
 * @param {Function} callbacks.onProgress - Called with progress updates
 * @param {Function} callbacks.onComplete - Called when job completes
 * @param {Function} callbacks.onError - Called on error
 * @param {Function} callbacks.onEnd - Called when stream ends
 * @returns {Promise<Function>} Cleanup function to close the connection
 */
export async function streamWorkflowProgress(
  jobId,
  getToken,
  { onProgress, onComplete, onError, onEnd }
) {
  return streamJobProgress(jobId, getToken, {
    onProgress,
    onComplete,
    onError,
    onEnd,
  });
}
