// src/api.js
/**
 * Core API client configuration
 *
 * This file exports the base axios instance used by all API services.
 * Individual services (e.g., extractionService.js) import this for their requests.
 */
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Base axios instance (unauthenticated - for public endpoints if needed)
const api = axios.create({
  baseURL: API_URL,
  timeout: 500_000, // 5 minutes for long-running extractions
  headers: {
    "Content-Type": "application/json",
  },
});

/**
 * Create an authenticated axios instance with Clerk token
 *
 * Usage in React components:
 * ```jsx
 * const { getToken } = useAuth();
 * const authenticatedApi = createAuthenticatedApi(getToken);
 * await authenticatedApi.post('/api/extract', formData);
 * ```
 *
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 * @returns {Object} Axios instance with auth interceptor
 */
export function createAuthenticatedApi(getToken) {
  const authenticatedApi = axios.create({
    baseURL: API_URL,
    timeout: 500_000,
  });

  // Add auth token to all requests
  authenticatedApi.interceptors.request.use(async (config) => {
    try {
      const token = await getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      } else {
        console.warn('⚠️ [Auth] No token returned from getToken()');
      }
    } catch (error) {
      console.error('❌ [Auth] Failed to get auth token:', error);
    }
    return config;
  });

  return authenticatedApi;
}

// User API
export const getUserInfo = async (token) => {
  const authenticatedApi = createAuthenticatedApi(() => token);
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
export const getUserExtractions = async (token, { limit, offset } = {}) => {
  const authenticatedApi = createAuthenticatedApi(() => token);
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

export default api;
