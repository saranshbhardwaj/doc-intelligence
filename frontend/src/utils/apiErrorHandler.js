/**
 * Centralized API Error Handler
 *
 * Provides consistent error handling across all API calls with:
 * - User-friendly error messages
 * - Proper HTTP error response parsing
 * - Network failure detection
 * - Timeout and CORS error handling
 * - Consistent error object structure
 */

/**
 * Error types for categorization
 */
export const ErrorTypes = {
  NETWORK: 'network_error',
  HTTP: 'http_error',
  TIMEOUT: 'timeout_error',
  AUTH: 'auth_error',
  VALIDATION: 'validation_error',
  SERVER: 'server_error',
  UNKNOWN: 'unknown_error',
};

/**
 * Extract error message from various error formats
 *
 * Handles:
 * - FastAPI error responses: { detail: "..." }
 * - Generic error responses: { message: "...", error: "..." }
 * - Array of errors: { detail: [{ msg: "..." }] }
 * - Plain text responses
 */
function extractErrorMessage(error) {
  // If error.response exists, try to extract from response data
  if (error.response?.data) {
    const data = error.response.data;

    // FastAPI validation error (422): { detail: [{ msg: "...", type: "..." }] }
    if (Array.isArray(data.detail) && data.detail.length > 0) {
      return data.detail.map(e => e.msg || e.message).join(', ');
    }

    // FastAPI error: { detail: "..." }
    if (typeof data.detail === 'string') {
      return data.detail;
    }

    // Generic error formats
    if (data.message) return data.message;
    if (data.error) return data.error;

    // If response data is a string
    if (typeof data === 'string') return data;
  }

  // Check error.message (could be from Error object or axios)
  if (error.message) {
    // Don't return generic axios messages
    if (error.message === 'Network Error') return null;
    if (error.message.startsWith('timeout of')) return null;
    return error.message;
  }

  return null;
}

/**
 * Determine error type from axios error
 */
function determineErrorType(error) {
  // Network failure (no response received)
  if (!error.response) {
    if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
      return ErrorTypes.TIMEOUT;
    }
    return ErrorTypes.NETWORK;
  }

  // HTTP status-based classification
  const status = error.response.status;

  if (status === 401 || status === 403) {
    return ErrorTypes.AUTH;
  }

  if (status === 422 || status === 400) {
    return ErrorTypes.VALIDATION;
  }

  if (status >= 500) {
    return ErrorTypes.SERVER;
  }

  return ErrorTypes.HTTP;
}

/**
 * Determine if error is retryable
 */
function isRetryable(error, errorType) {
  // Network errors and timeouts are usually retryable
  if (errorType === ErrorTypes.NETWORK || errorType === ErrorTypes.TIMEOUT) {
    return true;
  }

  // Server errors (5xx) are potentially retryable
  if (errorType === ErrorTypes.SERVER) {
    return true;
  }

  // Auth errors are not retryable (need re-login)
  if (errorType === ErrorTypes.AUTH) {
    return false;
  }

  // Validation errors are not retryable (need different input)
  if (errorType === ErrorTypes.VALIDATION) {
    return false;
  }

  // Check if backend explicitly marked as retryable
  if (error.response?.data?.is_retryable !== undefined) {
    return error.response.data.is_retryable;
  }

  if (error.response?.data?.retryable !== undefined) {
    return error.response.data.retryable;
  }

  return false;
}

/**
 * Get user-friendly error message based on error type
 */
function getUserFriendlyMessage(error, errorType, extractedMessage) {
  // If we extracted a good message from backend, use it
  if (extractedMessage && extractedMessage.length > 10) {
    return extractedMessage;
  }

  // Provide user-friendly defaults based on error type
  switch (errorType) {
    case ErrorTypes.NETWORK:
      return 'Unable to connect to server. Please check your internet connection and try again.';

    case ErrorTypes.TIMEOUT:
      return 'Request timed out. The server is taking too long to respond. Please try again.';

    case ErrorTypes.AUTH:
      if (error.response?.status === 401) {
        return 'Your session has expired. Please sign in again.';
      }
      return 'You don\'t have permission to perform this action.';

    case ErrorTypes.VALIDATION:
      return extractedMessage || 'Invalid input. Please check your data and try again.';

    case ErrorTypes.SERVER:
      return 'Server error occurred. Please try again later.';

    default:
      // Use extracted message or generic fallback
      return extractedMessage || 'An unexpected error occurred. Please try again.';
  }
}

/**
 * Main error handler function
 *
 * Converts any error into a consistent error object with:
 * - message: User-friendly error message
 * - type: Error type for categorization
 * - isRetryable: Whether the error can be retried
 * - status: HTTP status code (if applicable)
 * - originalError: Original error object for debugging
 *
 * @param {Error} error - Error from axios or other source
 * @returns {Object} Normalized error object
 */
export function handleApiError(error) {
  console.error('[API Error Handler]', error);

  // Determine error type
  const errorType = determineErrorType(error);

  // Extract error message from response
  const extractedMessage = extractErrorMessage(error);

  // Get user-friendly message
  const message = getUserFriendlyMessage(error, errorType, extractedMessage);

  // Determine if retryable
  const retryable = isRetryable(error, errorType);

  // Build normalized error object
  const normalizedError = {
    message,
    type: errorType,
    isRetryable: retryable,
    status: error.response?.status,
    originalError: error,
  };

  // Add additional context for specific error types
  if (errorType === ErrorTypes.VALIDATION && error.response?.data?.detail) {
    normalizedError.validationErrors = Array.isArray(error.response.data.detail)
      ? error.response.data.detail
      : null;
  }

  if (errorType === ErrorTypes.AUTH) {
    normalizedError.authError = true;
  }

  return normalizedError;
}

/**
 * Axios response interceptor error handler
 *
 * Use this in axios interceptors to automatically normalize all errors:
 *
 * ```javascript
 * api.interceptors.response.use(
 *   response => response,
 *   error => {
 *     const normalizedError = handleApiError(error);
 *     return Promise.reject(normalizedError);
 *   }
 * );
 * ```
 */
export function createErrorInterceptor() {
  return (error) => {
    const normalizedError = handleApiError(error);
    // Enhance the error object with normalized data
    error.normalized = normalizedError;
    // Also update error.message for backward compatibility
    error.message = normalizedError.message;
    return Promise.reject(error);
  };
}

/**
 * Wrap async function with error handling
 *
 * Usage:
 * ```javascript
 * const safeApiCall = withErrorHandling(async () => {
 *   return await api.get('/endpoint');
 * });
 *
 * try {
 *   const result = await safeApiCall();
 * } catch (error) {
 *   // error is already normalized
 *   console.error(error.message);
 * }
 * ```
 */
export function withErrorHandling(asyncFn) {
  return async (...args) => {
    try {
      return await asyncFn(...args);
    } catch (error) {
      throw handleApiError(error);
    }
  };
}
