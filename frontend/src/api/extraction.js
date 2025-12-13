/**
 * Extraction API
 *
 * All extraction-related API calls:
 * - Document upload and extraction
 * - Server-Sent Events (SSE) for progress streaming
 * - Job status and retry
 */

import { api, createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

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
  formData.append("file", file);
  if (context && context.trim()) {
    formData.append("context", context.trim());
  }

  const response = await authenticatedApi.post("/api/extract", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return response.data;
}

/**
 * Stream extraction job progress via Server-Sent Events (SSE)
 *
 * This is a wrapper around the unified streamJobProgress utility.
 * Uses the same endpoint as workflows.js: GET /api/jobs/{jobId}/stream
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
 * @returns {Promise<Function>} Cleanup function to close the connection
 */
export async function streamProgress(
  jobId,
  getToken,
  {
    onProgress,
    onComplete,
    onError,
    onEnd,
    autoReconnect = true,
    fetchInitialState = false,
  }
) {
  // Use unified SSE utility with extraction-specific getJobStatus function
  return streamJobProgress(jobId, getToken, {
    onProgress,
    onComplete,
    onError,
    onEnd,
    autoReconnect,
    fetchInitialState,
    getJobStatus: fetchInitialState ? getJobStatus : null,
  });
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
  const response = await authenticatedApi.get(
    `/api/extractions/${extractionId}`
  );
  return response.data;
}

/**
 * Retry a failed extraction from the last successful stage (REQUIRES AUTHENTICATION)
 *
 * @param {string} extractionId - The extraction ID to retry
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
export async function retryExtraction(extractionId, getToken) {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.post(
    `/api/extractions/${extractionId}/retry`
  );
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

/**
 * Extract temp document (no library save)
 * POST /api/extract/temp
 */
export async function extractTempDocument(file, getToken, context = "") {
  const authenticatedApi = createAuthenticatedApi(getToken);

  const formData = new FormData();
  formData.append("file", file);
  if (context && context.trim()) {
    formData.append("context", context.trim());
  }

  const response = await authenticatedApi.post("/api/extract/temp", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  return response.data;
}

/**
 * Extract from existing library document
 * POST /api/extract/documents/{docId}
 */
export async function extractFromDocument(documentId, getToken, context = "") {
  const authenticatedApi = createAuthenticatedApi(getToken);

  // Send JSON body (context is optional)
  const body = {};
  if (context && context.trim()) {
    body.context = context.trim();
  }

  const response = await authenticatedApi.post(
    `/api/extract/documents/${documentId}`,
    body,
    { headers: { "Content-Type": "application/json" } }
  );

  return response.data;
}

/**
 * Delete extraction
 * DELETE /api/extractions/{extractionId}
 */
export async function deleteExtraction(extractionId, getToken) {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.delete(
    `/api/extractions/${extractionId}`
  );
  return response.data;
}

/**
 * Fetch extraction history (paginated, requires authentication)
 *
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @param {Object} options - { limit, offset, status }
 * @returns {Promise<Object>} { items: ExtractionListItem[], total: number }
 *
 * Usage:
 *   const { getToken } = useAuth();
 *   const { items, total } = await fetchExtractionHistory(getToken, { limit: 20, offset: 0 });
 */
export async function fetchExtractionHistory(
  getToken,
  { limit = 50, offset = 0, status = null } = {}
) {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const params = { limit, offset };
  if (status) params.status = status;
  const response = await authenticatedApi.get("/api/extractions", { params });
  return response.data;
}
