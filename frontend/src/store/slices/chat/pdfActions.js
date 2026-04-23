/**
 * PDF viewer actions
 */
import { clearDocumentPreviewCache, loadDocumentPreview } from "../../../utils/documentPreview";

export const createChatPdfActions = (set, get) => ({
  highlightChunk: async (bbox, getToken) => {
    const { docId } = bbox;

    set((state) => ({
      chat: {
        ...state.chat,
        pdfViewer: {
          ...state.chat.pdfViewer,
          highlightBbox: bbox,
        },
      },
    }));

    // Only fetch document URL if it's a different document than what's already active
    if (docId && docId !== get().chat.pdfViewer.activeDocumentId) {
      await get().setActivePdfDocument(docId, getToken);
    }
  },

  clearHighlight: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        pdfViewer: {
          ...state.chat.pdfViewer,
          highlightBbox: null,
        },
      },
    }));
  },

  setActivePdfDocument: async (documentId, getToken) => {
    if (!documentId) return;

    const { urlCache } = get().chat.pdfViewer;
    const cached = urlCache[documentId];
    const now = Date.now();

    if (cached && cached.expiry > now) {
      set((state) => ({
        chat: {
          ...state.chat,
          pdfViewer: {
            ...state.chat.pdfViewer,
            activeDocumentId: documentId,
          },
        },
      }));
      return;
    }

    set((state) => ({
      chat: {
        ...state.chat,
        pdfViewer: {
          ...state.chat.pdfViewer,
          activeDocumentId: documentId,
          isLoadingUrl: true,
        },
      },
    }));

    try {
      const preview = await loadDocumentPreview(getToken, documentId);

      if (preview?.url) {
        const expiry = preview.expiry;

        set((state) => ({
          chat: {
            ...state.chat,
            pdfViewer: {
              ...state.chat.pdfViewer,
              urlCache: {
                ...state.chat.pdfViewer.urlCache,
                [documentId]: { url: preview.url, expiry },
              },
              isLoadingUrl: false,
            },
          },
        }));

      } else {
        console.error(`❌ No URL in response for document ${documentId}`);
        set((state) => ({
          chat: {
            ...state.chat,
            pdfViewer: {
              ...state.chat.pdfViewer,
              isLoadingUrl: false,
            },
          },
        }));
      }
    } catch (error) {
      console.error(`❌ Failed to load PDF URL for document ${documentId}:`, error);
      set((state) => ({
        chat: {
          ...state.chat,
          pdfViewer: {
            ...state.chat.pdfViewer,
            isLoadingUrl: false,
          },
        },
      }));
    }
  },

  loadPdfUrlForDocument: async (documentId, getToken) => {
    const { urlCache } = get().chat.pdfViewer;
    const cached = urlCache[documentId];
    const now = Date.now();

    if (cached && cached.expiry > now) {
      return cached.url;
    }

    try {
      const preview = await loadDocumentPreview(getToken, documentId);

      if (preview?.url) {
        const expiry = preview.expiry;

        set((state) => ({
          chat: {
            ...state.chat,
            pdfViewer: {
              ...state.chat.pdfViewer,
              urlCache: {
                ...state.chat.pdfViewer.urlCache,
                [documentId]: { url: preview.url, expiry },
              },
            },
          },
        }));

        return preview.url;
      }
    } catch (error) {
      console.error(`Failed to load PDF URL for ${documentId}:`, error);
    }

    return null;
  },

  clearPdfUrlCache: () => {
    clearDocumentPreviewCache();
    set((state) => ({
      chat: {
        ...state.chat,
        pdfViewer: {
          ...state.chat.pdfViewer,
          activeDocumentId: null,
          urlCache: {},
          highlightBbox: null,
        },
      },
    }));
  },
});
