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

function enrichTemplateStats(template) {
  if (!template) return template;

  const schemaMetadata = template.schema_metadata || {};
  const sheets = Array.isArray(schemaMetadata.sheets) ? schemaMetadata.sheets : [];
  const yamlTotalRaw =
    schemaMetadata?.schema_summary?.total_yaml_fields ??
    schemaMetadata?.total_yaml_fields;
  const isMissingYamlTotal =
    yamlTotalRaw == null ||
    (typeof yamlTotalRaw === "string" && yamlTotalRaw.trim() === "");
  const yamlTotal = isMissingYamlTotal ? Number.NaN : Number(yamlTotalRaw);

  const tableCells = sheets.reduce((sum, sheet) => {
    const tables = Array.isArray(sheet?.tables) ? sheet.tables : [];
    return sum + tables.reduce((tableSum, table) => tableSum + (table?.total_fillable_cells || 0), 0);
  }, 0);

  const fallbackTotalFields = (schemaMetadata.total_key_value_fields || 0) + tableCells;
  const totalFields = Number.isFinite(yamlTotal) ? yamlTotal : fallbackTotalFields;
  const totalSheets = sheets.length;

  return {
    ...template,
    total_fields: totalFields,
    total_sheets: totalSheets,
  };
}

/**
 * Poll template until schema_metadata is populated (template analysis complete).
 *
 * Uses exponential backoff: 1s → 2s → 4s → 8s (capped), so we check quickly
 * at first and back off if analysis is slow. Appropriate for background use
 * where nothing is blocking the UI.
 *
 * Returns the populated template or throws on timeout.
 */
export async function waitForTemplateAnalysis(getToken, templateId, maxWaitMs = 30_000) {
  const startTime = Date.now();
  let delay = 1_000; // Start at 1s
  const maxDelay = 8_000; // Cap at 8s

  while (Date.now() - startTime < maxWaitMs) {
    const template = await getRETemplate(getToken, templateId);

    if (template.schema_metadata && Object.keys(template.schema_metadata).length > 0) {
      return enrichTemplateStats(template);
    }

    await new Promise(resolve => setTimeout(resolve, delay));
    delay = Math.min(delay * 2, maxDelay); // Exponential backoff
  }

  // Timeout — return whatever state the template is in now
  console.warn('Template analysis timeout — returning current state');
  const latest = await getRETemplate(getToken, templateId);
  return enrichTemplateStats(latest);
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
 * Rename an Excel template
 */
export async function renameRETemplate(getToken, templateId, name) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.patch(`/api/v1/re/templates/${templateId}`, { name });
  return response.data;
}

/**
 * Rename a template fill run
 */
export async function renameFillRun(getToken, fillRunId, name) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.patch(`/api/v1/re/templates/fills/${fillRunId}`, { name });
  return response.data;
}

/**
 * Download Excel template file. Returns ArrayBuffer for XLSX parsing.
 *
 * R2 storage: backend returns { url } JSON — we fetch directly from the presigned
 * URL to avoid the Origin: null CORS error that occurs when browsers follow
 * cross-origin 307 redirects.
 * Local dev: backend streams binary directly.
 */
export async function downloadRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/${templateId}/download`, {
    responseType: 'blob',
  });

  const contentType = response.headers['content-type'] || '';
  if (contentType.includes('application/json')) {
    // R2: parse the presigned URL from the JSON blob, then fetch directly
    const text = await response.data.text();
    const { url } = JSON.parse(text);
    const fileResponse = await fetch(url);
    if (!fileResponse.ok) throw new Error(`Template fetch failed: ${fileResponse.status}`);
    return await fileResponse.arrayBuffer();
  }

  // Local dev: blob is the binary file
  return await response.data.arrayBuffer();
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
 * Get total fill run count for the current user (lightweight — no row data)
 */
export async function getFillRunCount(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/fills/count`);
  return response.data.count;
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
