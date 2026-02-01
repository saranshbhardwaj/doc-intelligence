/**
 * Collections actions
 */
import * as chatApi from "../../../api/chat";
import { getErrorMessage } from "./utils";

export const createChatCollectionActions = (set, get) => ({
  fetchCollections: async (getToken) => {
    set((state) => ({
      chat: {
        ...state.chat,
        collectionsLoading: true,
        collectionsError: null,
      },
    }));

    try {
      const data = await chatApi.listCollections(getToken);
      set((state) => ({
        chat: {
          ...state.chat,
          collections: data.collections,
          collectionsLoading: false,
        },
      }));
    } catch (error) {
      console.error("Failed to fetch collections:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          collectionsLoading: false,
          collectionsError: getErrorMessage(error),
        },
      }));
    }
  },

  createCollection: async (getToken, { name, description }) => {
    try {
      const collection = await chatApi.createCollection(getToken, {
        name,
        description,
      });

      set((state) => ({
        chat: {
          ...state.chat,
          collections: [collection, ...state.chat.collections],
        },
      }));

      return collection;
    } catch (error) {
      console.error("Failed to create collection:", error);
      throw error;
    }
  },

  selectCollection: async (getToken, collectionId) => {
    set((state) => ({
      chat: {
        ...state.chat,
        collectionLoading: true,
        collectionError: null,
      },
    }));

    try {
      const collection = await chatApi.getCollection(getToken, collectionId);

      set((state) => ({
        chat: {
          ...state.chat,
          currentCollection: collection,
          collectionLoading: false,
        },
      }));
    } catch (error) {
      console.error("Failed to select collection:", error);
      set((state) => ({
        chat: {
          ...state.chat,
          collectionLoading: false,
          collectionError: getErrorMessage(error),
        },
      }));
    }
  },

  deleteCollection: async (getToken, collectionId) => {
    try {
      await chatApi.deleteCollection(getToken, collectionId);

      set((state) => ({
        chat: {
          ...state.chat,
          collections: state.chat.collections.filter((c) => c.id !== collectionId),
          currentCollection:
            state.chat.currentCollection?.id === collectionId
              ? null
              : state.chat.currentCollection,
        },
      }));
    } catch (error) {
      console.error("Failed to delete collection:", error);
      throw error;
    }
  },
});
