// src/api/dashboard.js
/**
 * Dashboard API client
 *
 * Fetches organization-scoped analytics data from backend dashboard endpoints.
 * All endpoints are authenticated and automatically scoped to user's org_id.
 */

import { createAuthenticatedApi } from "./client";

/**
 * Get high-level dashboard overview statistics
 *
 * @param {Function} getToken - Clerk getToken function
 * @param {number} days - Number of days to include in period stats (default 30)
 * @returns {Promise<Object>} Overview stats (documents, chat, template fills, extractions, workflows, active users)
 */
export async function getDashboardOverview(getToken, days = 30) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/dashboard/overview?days=${days}`);
  return response.data;
}

/**
 * Get daily activity breakdown for charts
 *
 * @param {Function} getToken - Clerk getToken function
 * @param {number} days - Number of days to include (default 30)
 * @returns {Promise<Object>} Daily activity data { daily: [...] }
 */
export async function getDashboardActivity(getToken, days = 30) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/dashboard/activity?days=${days}`);
  return response.data;
}

/**
 * Get template fill insights and statistics
 *
 * @param {Function} getToken - Clerk getToken function
 * @param {number} days - Number of days to include (default 30)
 * @returns {Promise<Object>} Template fill stats (by_status, avg metrics, top_templates)
 */
export async function getTemplateFillStats(getToken, days = 30) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/dashboard/template-fills?days=${days}`);
  return response.data;
}
