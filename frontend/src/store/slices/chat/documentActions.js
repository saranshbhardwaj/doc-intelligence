/**
 * Document upload actions
 */
import * as chatApi from "../../../api/chat";
import { getErrorMessage } from "./utils";

export const createChatDocumentActions = (set, get) => ({
  uploadDocumentToCollection: async (getToken, collectionId, file) => {
    set((state) => ({
      chat: {
        ...state.chat,
        uploadStatus: "uploading",
        uploadProgress: 0,
        uploadError: null,
      },
    }));

    try {
      const data = await chatApi.uploadDocument(
        getToken,
        collectionId,
        file,
        (percent) => {
          set((state) => ({
            chat: { ...state.chat, uploadProgress: percent },
          }));
        }
      );

      set((state) => ({
        chat: {
          ...state.chat,
          uploadStatus: "indexing",
          uploadProgress: 0,
          currentJobId: data.job_id,
        },
      }));

      chatApi.connectToIndexingProgress(
        getToken,
        data.job_id,
        (progressData) => {
          set((state) => ({
            chat: {
              ...state.chat,
              uploadProgress: progressData.progress_percent || 0,
            },
          }));
        },
        () => {
          set((state) => ({
            chat: {
              ...state.chat,
              uploadStatus: "completed",
              uploadProgress: 100,
              currentJobId: null,
            },
          }));

          if (get().chat.currentCollection?.id === collectionId) {
            get().selectCollection(getToken, collectionId);
          }
        },
        (error) => {
          console.error("Indexing progress error:", error);
          set((state) => ({
            chat: {
              ...state.chat,
              uploadStatus: "failed",
              uploadError: getErrorMessage(error),
              currentJobId: null,
            },
          }));
        }
      );
    } catch (error) {
      console.error("Failed to upload document:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadStatus: "failed",
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  deleteDocument: async (getToken, documentId) => {
    try {
      await chatApi.deleteDocument(getToken, documentId);

      const currentCollection = get().chat.currentCollection;
      if (currentCollection) {
        await get().selectCollection(getToken, currentCollection.id);
      }
    } catch (error) {
      console.error("Failed to delete document:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  removeDocumentFromCollection: async (getToken, collectionId, documentId) => {
    try {
      await chatApi.removeDocumentFromCollection(getToken, collectionId, documentId);
      await get().selectCollection(getToken, collectionId);
    } catch (error) {
      console.error("Failed to remove document from collection:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          uploadError: getErrorMessage(error),
        },
      }));
    }
  },

  resetUploadStatus: () => {
    set((state) => ({
      chat: {
        ...state.chat,
        uploadStatus: null,
        uploadProgress: 0,
        uploadError: null,
        currentJobId: null,
      },
    }));
  },
});
