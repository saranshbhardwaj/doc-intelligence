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
      console.log('🔑 [Auth] Calling getToken()...');
      const token = await getToken();
      console.log('🔑 [Auth] Token received:', token ? `${token.substring(0, 20)}...` : 'null');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
        console.log('✅ [Auth] Authorization header set');
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
export const getUserInfo = async (getToken) => {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.get('/api/users/me');
  return response.data;
};

export default api;
