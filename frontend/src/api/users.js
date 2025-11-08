/**
 * User API
 *
 * All user-related API calls (profile, usage, extractions, etc.)
 */

import { createAuthenticatedApi } from './client';

/**
 * Get current user's info (usage stats, tier, limits)
 *
 * @param {Function} getToken - Clerk's getToken function
 * @returns {Promise<Object>} User info with usage statistics
 */
export const getUserInfo = async (getToken) => {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.get('/api/users/me');
  return response.data;
};

/**
 * Get user's extraction history
 *
 * @param {Function} getToken - Clerk's getToken function
 * @param {Object} params - Query parameters
 * @param {number} params.limit - Number of results (1-100, default 50)
 * @param {number} params.offset - Pagination offset
 * @param {string} params.status - Filter by status (completed, processing, failed)
 * @returns {Promise<Object>} Extraction history with pagination info
 */
export const getUserExtractions = async (getToken, { limit = 50, offset = 0 } = {}) => {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.get(`/api/users/me/extractions?limit=${limit}&offset=${offset}`);
  return response.data;
};

/**
 * Delete an extraction
 *
 * @param {Function} getToken - Clerk's getToken function
 * @param {string} extractionId - ID of extraction to delete
 * @returns {Promise<Object>} Deletion confirmation
 */
export const deleteExtraction = async (getToken, extractionId) => {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.delete(`/api/extractions/${extractionId}`);
  return response.data;
};
