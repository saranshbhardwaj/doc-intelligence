/**
 * Real Estate Underwriting API
 * Vertical-specific API calls to /api/v1/re/underwriting/*
 */

import { createAuthenticatedApi } from "./client";

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

export async function updateUnderwritingInputs(getToken, runId, inputs) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.patch(`/api/v1/re/underwriting/runs/${runId}/inputs`, {
    inputs,
  });
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

export async function deleteUnderwritingRun(getToken, runId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/underwriting/runs/${runId}`);
  return response.data;
}
