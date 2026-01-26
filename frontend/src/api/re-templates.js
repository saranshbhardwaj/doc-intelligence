/**
 * Real Estate Templates API
 * Vertical-specific API calls to /api/v1/re/templates/*
 */

import { createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

/**
 * List Excel templates for RE vertical
 */
export async function listRETemplates(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates`);
  return response.data;
}

/**
 * Upload a new Excel template
 */
export async function uploadRETemplate(getToken, file, options = {}) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("file", file);

  const { name, description, category } = options;
  if (name) formData.append("name", name);
  if (description) formData.append("description", description);
  if (category) formData.append("category", category);

  const response = await api.post(`/api/v1/re/templates`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/**
 * Get Excel template details
 */
export async function getRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/${templateId}`);
  return response.data;
}

/**
 * Poll template until schema_metadata is populated (template analysis complete)
 * Returns the populated template or throws timeout error
 */
export async function waitForTemplateAnalysis(getToken, templateId, maxWaitMs = 10000) {
  const startTime = Date.now();
  const pollInterval = 500; // Check every 500ms

  while (Date.now() - startTime < maxWaitMs) {
    const template = await getRETemplate(getToken, templateId);

    // Check if schema_metadata exists and has data
    if (template.schema_metadata && Object.keys(template.schema_metadata).length > 0) {
      return template;
    }

    // Wait before next poll
    await new Promise(resolve => setTimeout(resolve, pollInterval));
  }

  // Timeout - return what we have
  console.warn('⚠️ Template analysis timeout, returning current state');
  return await getRETemplate(getToken, templateId);
}

/**
 * Fill Excel template with data from document (alias for startTemplateFill)
 */
export async function fillRETemplate(getToken, templateId, documentId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/templates/${templateId}/fill`, {
    document_id: documentId,
  });
  return response.data;
}

/**
 * Start a template fill run (same as fillRETemplate)
 */
export async function startTemplateFill(getToken, templateId, documentId) {
  return fillRETemplate(getToken, templateId, documentId);
}

/**
 * Get template usage statistics (for deletion warning)
 */
export async function getTemplateUsage(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/${templateId}/usage`);
  return response.data;
}

/**
 * Delete an Excel template
 */
export async function deleteRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/templates/${templateId}`);
  return response.data;
}

/**
 * Download Excel template file (streams through backend to avoid CORS)
 * Returns ArrayBuffer for XLSX parsing
 */
export async function downloadRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/${templateId}/download`, {
    responseType: 'arraybuffer',
  });
  return response.data; // ArrayBuffer
}

/**
 * Get fill run status
 */
export async function getFillRunStatus(getToken, fillRunId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/fills/${fillRunId}`);
  return response.data;
}

/**
 * Update field mappings for a fill run
 */
export async function updateFillMappings(getToken, fillRunId, mappings) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.put(`/api/v1/re/templates/fills/${fillRunId}/mappings`, {
    mappings,
  });
  return response.data;
}

/**
 * Update extracted data for a fill run (manual editing)
 */
export async function updateExtractedData(getToken, fillRunId, extractedData) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.put(
    `/api/v1/re/templates/fills/${fillRunId}/extracted-data`,
    extractedData
  );
  return response.data;
}

/**
 * Continue fill run after reviewing mappings
 */
export async function continueFillRun(getToken, fillRunId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/templates/fills/${fillRunId}/continue`, {});
  return response.data;
}

/**
 * Download filled Excel file
 */
export async function downloadFilledExcel(getToken, fillRunId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/fills/${fillRunId}/download`, {
    responseType: 'blob',
  });
  return response.data;
}

/**
 * List all fill runs for the current user with pagination
 */
export async function listFillRuns(getToken, limit = 20, offset = 0) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/fills`, {
    params: { limit, offset },
  });
  return response.data;
}

/**
 * Delete a fill run
 */
export async function deleteFillRun(getToken, fillRunId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/templates/fills/${fillRunId}`);
  return response.data;
}

/**
 * Stream template fill job progress via Server-Sent Events (SSE)
 *
 * @param {string} jobId - The job ID (usually same as fill_run_id)
 * @param {function} getToken - Function to get auth token
 * @param {object} callbacks - { onProgress, onComplete, onError, onEnd }
 * @returns {function} Cleanup function to close SSE connection
 */
export async function streamTemplateFillProgress(
  jobId,
  getToken,
  { onProgress, onComplete, onError, onEnd }
) {
  // Helper to fetch job status for initial state
  const getJobStatus = async (jobId, getToken) => {
    const api = createAuthenticatedApi(getToken);
    const response = await api.get(`/api/jobs/${jobId}/status`);
    return response.data;
  };

  return streamJobProgress(jobId, getToken, {
    onProgress,
    onComplete,
    onError,
    onEnd,
    fetchInitialState: true, // Fetch current job state before SSE connection
    getJobStatus,
  });
}
