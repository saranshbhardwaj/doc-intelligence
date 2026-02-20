/**
 * Workflow PDF viewer actions
 *
 * Scoped to workflowDraft.pdfViewer state (separate from chat PDF state).
 * Reuses the same getDocumentDownloadUrl API and presigned URL caching pattern.
 */
import { getDocumentDownloadUrl } from "../../api/documents";

export const createWorkflowPdfActions = (set, get) => ({
  workflowHighlightChunk: (bbox, getToken) => {
    const { docId } = bbox;

    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        pdfViewer: {
          ...state.workflowDraft.pdfViewer,
          highlightBbox: bbox,
        },
      },
    }));

    // Only fetch document URL if it's a different document
    if (docId && docId !== get().workflowDraft.pdfViewer.activeDocumentId) {
      get().workflowSetActivePdfDocument(docId, getToken);
    }
  },

  workflowClearHighlight: () => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        pdfViewer: {
          ...state.workflowDraft.pdfViewer,
          highlightBbox: null,
        },
      },
    }));
  },

  workflowSetActivePdfDocument: async (documentId, getToken) => {
    if (!documentId) return;

    const { urlCache } = get().workflowDraft.pdfViewer;
    const cached = urlCache[documentId];
    const now = Date.now();

    if (cached && cached.expiry > now) {
      set((state) => ({
        workflowDraft: {
          ...state.workflowDraft,
          pdfViewer: {
            ...state.workflowDraft.pdfViewer,
            activeDocumentId: documentId,
          },
        },
      }));
      return;
    }

    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        pdfViewer: {
          ...state.workflowDraft.pdfViewer,
          activeDocumentId: documentId,
          isLoadingUrl: true,
        },
      },
    }));

    try {
      const urlData = await getDocumentDownloadUrl(getToken, documentId);

      if (urlData.url) {
        const expiry = now + urlData.expires_in * 1000;

        set((state) => ({
          workflowDraft: {
            ...state.workflowDraft,
            pdfViewer: {
              ...state.workflowDraft.pdfViewer,
              urlCache: {
                ...state.workflowDraft.pdfViewer.urlCache,
                [documentId]: { url: urlData.url, expiry },
              },
              isLoadingUrl: false,
            },
          },
        }));
      } else {
        set((state) => ({
          workflowDraft: {
            ...state.workflowDraft,
            pdfViewer: {
              ...state.workflowDraft.pdfViewer,
              isLoadingUrl: false,
            },
          },
        }));
      }
    } catch (error) {
      console.error(`Failed to load PDF URL for document ${documentId}:`, error);
      set((state) => ({
        workflowDraft: {
          ...state.workflowDraft,
          pdfViewer: {
            ...state.workflowDraft.pdfViewer,
            isLoadingUrl: false,
          },
        },
      }));
    }
  },

  workflowClearPdfViewer: () => {
    set((state) => ({
      workflowDraft: {
        ...state.workflowDraft,
        pdfViewer: {
          activeDocumentId: null,
          urlCache: {},
          highlightBbox: null,
          isLoadingUrl: false,
        },
      },
    }));
  },
});
