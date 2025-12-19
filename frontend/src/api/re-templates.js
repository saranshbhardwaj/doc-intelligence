/**
 * Real Estate Templates API
 * Vertical-specific API calls to /api/v1/re/templates/*
 */

import { createAuthenticatedApi } from "./client";

/**
 * List Excel templates for RE vertical
 */
export async function listRETemplates(getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates`);
  return response.data;
}

/**
 * Upload a new Excel template
 */
export async function uploadRETemplate(getToken, file, name = null, description = null) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("file", file);
  if (name) formData.append("name", name);
  if (description) formData.append("description", description);

  const response = await api.post(`/api/v1/re/templates`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

/**
 * Get Excel template details
 */
export async function getRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/templates/${templateId}`);
  return response.data;
}

/**
 * Fill Excel template with data from document
 */
export async function fillRETemplate(getToken, templateId, documentId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/templates/${templateId}/fill`, {
    document_id: documentId,
  });
  return response.data;
}

/**
 * Delete an Excel template
 */
export async function deleteRETemplate(getToken, templateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/templates/${templateId}`);
  return response.data;
}
