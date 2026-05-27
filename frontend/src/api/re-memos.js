/**
 * Credit memo API client for the RE underwriting vertical.
 * Mirrors the structure of re-templates.js.
 */
import { createAuthenticatedApi } from './client';
import { streamJobProgress } from './sse-utils';

/**
 * Create a memo: posts cover/sponsor/notes, returns { memo_id, job_id, version }.
 */
export async function generateMemo(getToken, runId, payload) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/v1/re/underwriting/runs/${runId}/memos`,
    payload,
  );
  return response.data;
}

/**
 * Pre-flight readiness check for memo generation.
 * Returns { om_indexed, document_count, indexed_chunk_count, warnings }.
 */
export async function getMemoReadiness(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(
    `/api/v1/re/underwriting/runs/${runId}/memo-readiness`,
  );
  return response.data;
}

/**
 * List all memos for a run (newest version first).
 */
export async function listMemos(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(
    `/api/v1/re/underwriting/runs/${runId}/memos`,
  );
  return response.data.memos || [];
}

/**
 * Fetch a presigned download URL for a complete memo.
 */
export async function getMemoDownloadUrl(getToken, memoId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(
    `/api/v1/re/underwriting/memos/${memoId}/download`,
  );
  return response.data.url;
}

/**
 * Delete a terminal memo and its generated file.
 */
export async function deleteMemo(getToken, memoId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/underwriting/memos/${memoId}`);
  return response.data;
}

/**
 * Subscribe to SSE progress for a memo's underlying job_id.
 *
 * Calls handlers.onProgress({ progress, message, stage }) on each event.
 * Calls handlers.onComplete() on terminal event.
 * Calls handlers.onError(msg) on failure.
 *
 * @param {Function} getToken - Auth token getter
 * @param {string} jobId - The job ID returned by generateMemo
 * @param {Object} handlers - { onProgress, onComplete, onError, onEnd }
 * @returns {Promise<Function>} Cleanup / close function
 */
export async function streamMemoProgress(getToken, jobId, handlers) {
  const { onProgress, onComplete, onError, onEnd } = handlers;

  const getJobStatus = async (id, gt) => {
    const api = createAuthenticatedApi(gt);
    const response = await api.get(`/api/jobs/${id}/status`);
    return response.data;
  };

  return streamJobProgress(jobId, getToken, {
    onProgress: (evt) => {
      onProgress?.({
        progress: evt.progress_percent,
        message: evt.message,
        stage: evt.current_stage,
      });
    },
    onComplete,
    onError: (evt) => {
      onError?.(evt?.message || 'Memo generation failed.');
    },
    onEnd,
    fetchInitialState: true,
    getJobStatus,
  });
}
