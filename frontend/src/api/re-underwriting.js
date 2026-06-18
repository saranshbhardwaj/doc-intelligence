/**
 * Real Estate Underwriting API
 * Vertical-specific API calls to /api/v1/re/underwriting/*
 */

import { createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

export async function createUnderwritingRun(getToken, payload) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/underwriting/runs`, payload);
  return response.data;
}

export async function listUnderwritingRuns(getToken, { limit = 20, offset = 0 } = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/underwriting/runs`, {
    params: { limit, offset },
  });
  return response.data;
}

export async function getUnderwritingRun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/underwriting/runs/${runId}`);
  return response.data;
}

export async function updateUnderwritingInputs(getToken, runId, inputs, fieldCitations) {
  const api = createAuthenticatedApi(getToken);
  const payload = { inputs };
  if (fieldCitations !== undefined) payload.field_citations = fieldCitations;
  const response = await api.patch(`/api/v1/re/underwriting/runs/${runId}/inputs`, payload);
  return response.data;
}

export async function updateUnderwritingRunMetadata(getToken, runId, metadata) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.patch(`/api/v1/re/underwriting/runs/${runId}`, metadata);
  return response.data;
}

export async function runSensitivityAnalysis(getToken, runId, purchasePrices) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/v1/re/underwriting/runs/${runId}/sensitivity`,
    { purchase_prices: purchasePrices }
  );
  return response.data;
}

/**
 * Stateless what-if recalculation. Only provided override fields are applied.
 * @param {object} overrides - { exit_cap_rate?, vacancy_credit_loss_pct?, rent_growth_pct?, interest_rate_pct?, purchase_price? }
 */
export async function recalculateScenario(getToken, runId, overrides) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/v1/re/underwriting/runs/${runId}/recalculate`,
    overrides
  );
  return response.data;
}

/**
 * Stateless max-loan sizing. All constraints optional; backend falls back to criteria, then to defaults.
 * @param {object} constraints - { dscr_floor?, max_ltv?, debt_yield_floor? }
 * @returns {Promise<object>} MaxLoanResult shape (see backend schemas/self_storage.py)
 */
export async function calculateMaxLoan(getToken, runId, constraints = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(
    `/api/v1/re/underwriting/runs/${runId}/max-loan`,
    constraints
  );
  return response.data;
}

export async function deleteUnderwritingRun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/underwriting/runs/${runId}`);
  return response.data;
}

/**
 * Stream underwriting extraction job progress via Server-Sent Events (SSE).
 * Fetches current job state first so UI can recover after refresh/navigation.
 */
export async function streamUnderwritingExtractionProgress(
  jobId,
  getToken,
  { onProgress, onComplete, onError, onEnd }
) {
  const getJobStatus = async (activeJobId, activeGetToken) => {
    const api = createAuthenticatedApi(activeGetToken);
    const response = await api.get(`/api/jobs/${activeJobId}/status`);
    return response.data;
  };

  return streamJobProgress(jobId, getToken, {
    onProgress,
    onComplete,
    onError,
    onEnd,
    fetchInitialState: true,
    getJobStatus,
  });
}
