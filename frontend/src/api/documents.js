/**
 * Documents API
 * API calls for document management including PDF downloads
 */

import { createAuthenticatedApi } from "./client";

/**
 * Get presigned URL for document download/viewing
 * @param {Function} getToken - Auth token getter
 * @param {string} documentId - Document ID
 * @returns {Promise<{url: string, expires_in: number, storage_backend: string}>}
 */
export async function getDocumentDownloadUrl(getToken, documentId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/documents/${documentId}/download`);
  return response.data;
}
