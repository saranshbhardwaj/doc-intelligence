/**
 * API Client Configuration
 *
 * Base axios instance and authentication utilities for all API calls.
 */

import axios from "axios";
import { createErrorInterceptor } from "../utils/apiErrorHandler";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Base axios instance (unauthenticated - for public endpoints if needed)
export const api = axios.create({
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

  // Add auth token to all requests.
  // getToken() contacts Clerk's servers — wrap in a timeout so a slow/unreachable
  // Clerk doesn't hang every API request indefinitely.
  authenticatedApi.interceptors.request.use(async (config) => {
    try {
      const token = await Promise.race([
        getToken(),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('getToken timeout')), 10_000)
        ),
      ]);
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      } else {
        console.warn('⚠️ [Auth] No token returned from getToken()');
      }
    } catch (error) {
      // Log quietly — request proceeds without auth and server returns 401
      console.warn('⚠️ [Auth] Token fetch failed:', error.message);
    }
    return config;
  });

  // Handle errors — redirect to /access-pending on 403 "access_pending"
  authenticatedApi.interceptors.response.use(
    (response) => response,
    (error) => {
      if (
        error.response?.status === 403 &&
        error.response?.data?.detail === "access_pending"
      ) {
        window.location.href = "/access-pending";
        return new Promise(() => {}); // Never resolve — page is navigating
      }
      return createErrorInterceptor()(error);
    }
  );

  return authenticatedApi;
}
