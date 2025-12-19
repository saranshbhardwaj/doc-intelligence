/**
 * Private Equity Extraction API
 * Vertical-specific API calls to /api/v1/pe/extraction/*
 */

import { createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

/**
 * List PE extractions (user's extraction history)
 */
export async function listPEExtractions(getToken, { limit = 50, offset = 0, status = null } = {}) {
  const api = createAuthenticatedApi(getToken);
  const params = new URLSearchParams({ limit, offset });
  if (status) params.append("status", status);
  const response = await api.get(`/api/v1/pe/extraction?${params}`);
  return response.data;
}

/**
 * Extract CIM data from uploaded document (PE vertical)
 */
export async function extractPEDocument(getToken, file, context = null) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("file", file);
  if (context) {
    formData.append("context", context);
  }

  const response = await api.post(`/api/v1/pe/extraction`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/**
 * Upload temporary file for extraction (no library save)
 */
export async function extractPETempDocument(getToken, file, context = null) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("file", file);
  if (context) {
    formData.append("context", context);
  }

  const response = await api.post(`/api/v1/pe/extraction/temp`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/**
 * Run extraction on existing library document
 */
export async function extractFromPELibraryDocument(getToken, documentId, context = null) {
  const api = createAuthenticatedApi(getToken);
  const payload = context ? { context } : {};
  const response = await api.post(`/api/v1/pe/extraction/documents/${documentId}`, payload);
  return response.data;
}

/**
 * Get PE extraction result by ID
 */
export async function getPEExtraction(getToken, extractionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/extraction/${extractionId}`);
  return response.data;
}

/**
 * Delete a PE extraction and its artifacts
 */
export async function deletePEExtraction(getToken, extractionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/pe/extraction/${extractionId}`);
  return response.data;
}

/**
 * Retry a failed PE extraction
 */
export async function retryPEExtraction(getToken, extractionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/pe/extraction/${extractionId}/retry`);
  return response.data;
}

/**
 * Export PE extraction result to Word or Excel
 */
export async function exportPEExtraction(getToken, extractionId, format = "word") {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/pe/extraction/${extractionId}/export?format=${encodeURIComponent(format)}`, {
    responseType: "blob",
  });
  return response;
}

/**
 * Stream PE extraction job progress via Server-Sent Events (SSE)
 */
export async function streamPEExtractionProgress(
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
