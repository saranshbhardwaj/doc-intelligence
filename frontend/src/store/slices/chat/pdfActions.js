/**
 * PDF viewer actions
 */
import { getDocumentDownloadUrl } from "../../../api/documents";

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

    if (docId) {
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
      const urlData = await getDocumentDownloadUrl(getToken, documentId);

      if (urlData.url) {
        const expiry = now + urlData.expires_in * 1000;

        set((state) => ({
          chat: {
            ...state.chat,
            pdfViewer: {
              ...state.chat.pdfViewer,
              urlCache: {
                ...state.chat.pdfViewer.urlCache,
                [documentId]: { url: urlData.url, expiry },
              },
              isLoadingUrl: false,
            },
          },
        }));

        console.log(`✅ Loaded PDF URL for document ${documentId}`);
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
      const urlData = await getDocumentDownloadUrl(getToken, documentId);

      if (urlData.url) {
        const expiry = now + urlData.expires_in * 1000;

        set((state) => ({
          chat: {
            ...state.chat,
            pdfViewer: {
              ...state.chat.pdfViewer,
              urlCache: {
                ...state.chat.pdfViewer.urlCache,
                [documentId]: { url: urlData.url, expiry },
              },
            },
          },
        }));

        return urlData.url;
      }
    } catch (error) {
      console.error(`Failed to load PDF URL for ${documentId}:`, error);
    }

    return null;
  },

  clearPdfUrlCache: () => {
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
