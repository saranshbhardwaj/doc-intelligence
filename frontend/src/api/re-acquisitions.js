import { createAuthenticatedApi } from './client';

function normalizeDocument(doc) {
  return {
    ...doc,
    type: doc.type || doc.doc_type,
    name: doc.name || doc.filename || doc.document_id || 'Library document',
    processingStatus: doc.processingStatus || doc.processing_status || doc.status,
    hasEmbeddings: doc.hasEmbeddings ?? doc.has_embeddings,
    chunkCount: doc.chunkCount ?? doc.chunk_count,
  };
}

export function normalizeCandidate(candidate) {
  if (!candidate) return null;
  return {
    ...candidate,
    assetClass: candidate.assetClass || candidate.asset_class,
    assetClassConfidence: candidate.assetClassConfidence ?? Math.round((candidate.asset_class_confidence || 0) * 100),
    sourceType: candidate.sourceType || candidate.source_type,
    sourceName: candidate.sourceName || candidate.source_name,
    sourceStatus: candidate.sourceStatus || candidate.source_status,
    readinessScore: candidate.readinessScore ?? candidate.readiness_score,
    missingItems: candidate.missingItems || candidate.missing_items || [],
    underwritingRunId: candidate.underwritingRunId || candidate.underwriting_run_id,
    documents: (candidate.documents || []).map(normalizeDocument),
  };
}

export async function listAcquisitionCandidates(getToken, { limit = 100, offset = 0 } = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get('/api/v1/re/acquisitions/candidates', { params: { limit, offset } });
  return {
    ...response.data,
    candidates: (response.data.candidates || []).map(normalizeCandidate),
  };
}

export async function getAcquisitionCandidate(getToken, candidateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/v1/re/acquisitions/candidates/${candidateId}`);
  return normalizeCandidate(response.data);
}

export async function createAcquisitionCandidate(getToken, payload) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post('/api/v1/re/acquisitions/candidates', {
    name: payload.name,
    address: payload.address || null,
    market: payload.market || null,
    asset_class: payload.assetClass || payload.asset_class || 'self_storage',
    asset_class_confidence: payload.assetClassConfidence != null
      ? Number(payload.assetClassConfidence) / 100
      : payload.asset_class_confidence,
    source_type: payload.sourceType || payload.source_type || 'manual',
    source_name: payload.sourceName || payload.source_name || null,
    source_status: payload.sourceStatus || payload.source_status || 'manual',
    status: payload.status || 'needs_docs',
    priority: payload.priority || 'medium',
    readiness_score: payload.readinessScore ?? payload.readiness_score ?? null,
    facts: payload.facts || {},
    evidence: payload.evidence || [],
    missing_items: payload.missingItems || payload.missing_items || ['om'],
  });
  return normalizeCandidate(response.data);
}

export async function attachCandidateDocument(getToken, candidateId, payload) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/acquisitions/candidates/${candidateId}/documents`, payload);
  return normalizeCandidate(response.data);
}

export async function detachCandidateDocument(getToken, candidateId, documentId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/v1/re/acquisitions/candidates/${candidateId}/documents/${documentId}`);
  return normalizeCandidate(response.data);
}

export async function createUnderwritingRunFromCandidate(getToken, candidateId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/v1/re/acquisitions/candidates/${candidateId}/create-underwriting-run`, { confirmed: true });
  return response.data;
}