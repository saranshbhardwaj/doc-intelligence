/**
 * API Exports
 *
 * Central export point for all API functions.
 * Import from here instead of individual files.
 *
 * Usage:
 * ```jsx
 * import { uploadDocument, getUserInfo } from '../api';
 * ```
 */

// Client
export { api, createAuthenticatedApi } from './client';

// Extraction APIs
export {
  uploadDocument,
  streamProgress,
  fetchExtractionResult,
  retryExtraction,
  getJobStatus,
} from './extraction';

// User APIs
export {
  getUserInfo,
  getUserExtractions,
  deleteExtraction,
} from './users';

// Feedback API
export { submitFeedback } from './feedback';
