import { getDocumentDownloadUrl } from "@/api/documents";

const documentPreviewCache = new Map();
const pendingDocumentPreviewRequests = new Map();

export function clearDocumentPreviewCache(documentId) {
  if (documentId) {
    documentPreviewCache.delete(documentId);
    pendingDocumentPreviewRequests.delete(documentId);
    return;
  }

  documentPreviewCache.clear();
  pendingDocumentPreviewRequests.clear();
}

export async function loadDocumentPreview(getToken, documentId) {
  if (!documentId) return null;

  const now = Date.now();
  const cached = documentPreviewCache.get(documentId);
  if (cached && cached.expiry > now) {
    return cached;
  }

  const pendingRequest = pendingDocumentPreviewRequests.get(documentId);
  if (pendingRequest) {
    return pendingRequest;
  }

  const request = (async () => {
    try {
      const result = await getDocumentDownloadUrl(getToken, documentId);
      if (result?.missing) {
        return { missing: true };
      }

      if (!result?.url) {
        return null;
      }

      const preview = {
        documentId,
        url: result.url,
        filename: result.filename || "",
        contentType: result.content_type || "",
        expiry: now + ((result.expires_in || 0) * 1000),
      };

      documentPreviewCache.set(documentId, preview);
      return preview;
    } finally {
      pendingDocumentPreviewRequests.delete(documentId);
    }
  })();

  pendingDocumentPreviewRequests.set(documentId, request);
  return request;
}

export function buildDocumentHighlightPayload(citation) {
  if (!citation) return null;

  const bboxPage = Number(citation.bbox?.page);
  if (citation.bbox && Number.isFinite(bboxPage) && bboxPage > 0) {
    return {
      ...citation.bbox,
      page: bboxPage,
      __ts: Date.now(),
    };
  }

  const page = Number(citation.page);
  if (Number.isFinite(page) && page > 0) {
    return {
      page,
      __scrollOnly: true,
      __ts: Date.now(),
    };
  }

  return null;
}