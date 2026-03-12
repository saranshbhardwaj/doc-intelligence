/**
 * PE Diligence API Client
 * Covers: Deal Rooms, Documents, Analysis, Investigations, Claims
 */

import { createAuthenticatedApi } from "./client";

const BASE = "/api/v1/pe/diligence";

// --- Rooms ---

export async function listRooms(getToken) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms`);
  return res.data;
}

export async function createRoom(getToken, payload) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms`, payload);
  return res.data;
}

export async function getRoom(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}`);
  return res.data;
}

// --- Documents ---

export async function listRoomDocuments(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/documents`);
  return res.data;
}

export async function uploadRoomDocument(getToken, roomId, formData) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms/${roomId}/documents/upload`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

export async function removeRoomDocument(getToken, roomId, roomDocumentId) {
  const api = createAuthenticatedApi(getToken);
  await api.delete(`${BASE}/rooms/${roomId}/documents/${roomDocumentId}`);
}

// --- Analysis ---

export async function startAnalysis(getToken, roomId, forceReanalyze = false) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms/${roomId}/analyze`, { force_reanalyze: forceReanalyze });
  return res.data;
}

export async function getAnalysisRun(getToken, roomId, runId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/analysis-runs/${runId}`);
  return res.data;
}

export async function getRoomChecklist(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/checklist`);
  return res.data;
}

export async function getRoomFindings(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/findings`);
  return res.data;
}

export async function getRoomSummary(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/summary`);
  return res.data;
}

// --- Investigations ---

export async function listInvestigations(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/investigations`);
  return res.data;
}

export async function createInvestigation(getToken, roomId, payload) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms/${roomId}/investigations`, payload);
  return res.data;
}

export async function getInvestigation(getToken, roomId, investigationId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/investigations/${investigationId}`);
  return res.data;
}

export async function rerunInvestigation(getToken, roomId, investigationId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms/${roomId}/investigations/${investigationId}/rerun`);
  return res.data;
}

// --- Findings ---

export async function updateFinding(getToken, roomId, findingId, payload) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.patch(`${BASE}/rooms/${roomId}/findings/${findingId}`, payload);
  return res.data;
}

// --- Amendment Links ---

export async function updateAmendmentLink(getToken, roomId, roomDocumentId, payload) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.patch(`${BASE}/rooms/${roomId}/documents/${roomDocumentId}/amendment-link`, payload);
  return res.data;
}

// --- Folder Management ---

export async function updateRoomDocumentFolder(getToken, roomId, roomDocumentId, folder) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.patch(`${BASE}/rooms/${roomId}/documents/${roomDocumentId}/folder`, {
    folder,
  });
  return res.data;
}

// --- Clauses ---

export async function listRoomClauses(getToken, roomId, { documentId, clauseType, limit = 200, offset = 0 } = {}) {
  const api = createAuthenticatedApi(getToken);
  const params = {};
  if (documentId) params.document_id = documentId;
  if (clauseType) params.clause_type = clauseType;
  if (limit !== 200) params.limit = limit;
  if (offset) params.offset = offset;
  const res = await api.get(`${BASE}/rooms/${roomId}/clauses`, { params });
  return res.data;
}

// --- Contract Families ---

export async function listContractFamilies(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/rooms/${roomId}/contract-families`);
  return res.data;
}

// --- Playbooks ---

export async function listPlaybooks(getToken) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.get(`${BASE}/playbooks`);
  return res.data;
}

// --- IC Memo Generation ---

export async function generateICMemo(getToken, roomId) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.post(`${BASE}/rooms/${roomId}/generate-ic-memo`);
  return res.data;
}

// --- Claims ---

export async function overrideClaim(getToken, roomId, investigationId, claimId, payload) {
  const api = createAuthenticatedApi(getToken);
  const res = await api.patch(
    `${BASE}/rooms/${roomId}/investigations/${investigationId}/claims/${claimId}/verification`,
    payload,
  );
  return res.data;
}
