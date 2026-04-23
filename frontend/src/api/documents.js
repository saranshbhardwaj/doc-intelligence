/**
 * Documents API
 * API calls for document management including PDF downloads
 */

import { createAuthenticatedApi } from "./client";

/**
 * Get presigned URL for document download/viewing
 * @param {Function} getToken - Auth token getter
 * @param {string} documentId - Document ID
 * @returns {Promise<{url: string, expires_in: number, storage_backend: string, filename?: string, content_type?: string} | {missing: true}>}
 */
export async function getDocumentDownloadUrl(getToken, documentId) {
  const api = createAuthenticatedApi(getToken);
  // Treat 404 as an expected state (source document deleted after a fill run exists).
  // This avoids noisy console/interceptor errors for a recoverable UI path.
  const response = await api.get(`/api/chat/documents/${documentId}/download`, {
    validateStatus: (status) => status === 200 || status === 404,
  });

  if (response.status === 404) {
    return { missing: true };
  }

  return response.data;
}
