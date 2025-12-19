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
export { api, createAuthenticatedApi } from "./client";

// Extraction APIs
export {
  uploadDocument as uploadDocumentForExtraction,
  streamProgress,
  fetchExtractionResult,
  retryExtraction,
  getJobStatus,
  extractTempDocument,
  extractFromDocument,
  deleteExtraction as deleteResultFromExtraction,
  fetchExtractionHistory,
} from "./extraction";

// User APIs
export { getUserInfo, getUserExtractions, deleteExtraction } from "./users";

// Feedback API
export { submitFeedback } from "./feedback";

// Chat APIs
export {
  createCollection,
  listCollections,
  getCollection,
  deleteCollection,
  uploadDocument as uploadDocumentToCollection,
  connectToIndexingProgress,
  sendChatMessage,
  listSessions,
  getChatHistory,
  deleteSession,
  exportSession,
  getSession,
  createSession,
  updateSession,
  addDocumentsToSession,
} from "./chat";

// Workflows
export {
  getRun,
  getRunArtifact,
  exportRun,
  listRuns,
  listTemplates,
  deleteRun,
} from "./workflows";

// Vertical-specific APIs
export * as peWorkflows from './pe-workflows';
export * as peExtraction from './pe-extraction';
export * as reTemplates from './re-templates';
