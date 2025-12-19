/**
 * Private Equity Workflows API
 * Vertical-specific API calls to /api/v1/pe/workflows/*
 */

import { createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

/**
 * List PE workflow templates (filtered to domain='private_equity')
 */
export async function listPETemplates(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/workflows/templates`);
  return response.data;
}

/**
 * Get PE workflow template details
 */
export async function getPETemplate(getToken, workflowId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/workflows/templates/${workflowId}`);
  return response.data;
}

/**
 * Create a new PE workflow run
 */
export async function createPEWorkflowRun(getToken, params) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/pe/workflows/runs`, params);
  return response.data;
}

/**
 * List user's PE workflow runs
 */
export async function listPERuns(getToken, { limit = 50, offset = 0 } = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/workflows/runs?limit=${limit}&offset=${offset}`);
  return response.data;
}

/**
 * Get PE workflow run details
 */
export async function getPERun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/workflows/runs/${runId}`);
  return response.data;
}

/**
 * Get PE workflow run artifact
 */
export async function getPERunArtifact(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  try {
    const response = await api.get(`/api/v1/pe/workflows/runs/${runId}/artifact`);
    return response.data;
  } catch {
    return null;
  }
}

/**
 * Delete a PE workflow run
 */
export async function deletePERun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/pe/workflows/runs/${runId}`);
  return response.data;
}

/**
 * Export PE workflow run to Word, Excel, or PDF
 */
export async function exportPERun(getToken, runId, format, delivery = "url") {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/v1/pe/workflows/runs/${runId}/export?format=${encodeURIComponent(format)}&delivery=${encodeURIComponent(delivery)}`,
    {},
    { responseType: "json" }
  );
  return response;
}

/**
 * Re-run a PE workflow with modified parameters
 */
export async function rerunPEWorkflow(getToken, runId, params = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/pe/workflows/runs/${runId}/rerun`, params);
  return response.data;
}

/**
 * List documents available for PE workflows
 */
export async function listPEDocuments(getToken, collectionId = null) {
  const api = createAuthenticatedApi(getToken);
  const url = collectionId
    ? `/api/v1/pe/workflows/documents?collection_id=${collectionId}`
    : `/api/v1/pe/workflows/documents`;
  const response = await api.get(url);
  return response.data;
}

/**
 * Stream PE workflow job progress via Server-Sent Events (SSE)
 */
export async function streamPEWorkflowProgress(
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
