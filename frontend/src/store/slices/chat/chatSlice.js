/**
 * Chat Slice for Zustand Store
 *
 * Session-centric architecture:
 * - Collections are folders for browsing documents
 * - Sessions are independent and maintain their own document selection
 * - Chat happens within sessions, not directly with collections
 */

import { createChatCollectionActions } from "./collectionActions";
import { createChatDocumentActions } from "./documentActions";
import { createChatSessionActions } from "./sessionActions";
import { createChatMessageActions } from "./messageActions";
import { createChatIndexingActions } from "./indexingActions";
import { createChatComparisonActions } from "./comparisonActions";
import { createChatPdfActions } from "./pdfActions";

const initialChatState = {
  // Collections (for document browsing only)
  collections: [],
  collectionsLoading: false,
  collectionsError: null,

  // Current collection (for document browsing)
  currentCollection: null,
  collectionLoading: false,
  collectionError: null,

  // Document indexing jobs (Map: documentId -> job state)
  indexingJobs: {},

  // Upload state
  uploadStatus: null,
  uploadProgress: 0,
  uploadError: null,
  currentJobId: null,

  // Current session (with documents)
  currentSession: null,
  messages: [],
  isStreaming: false,
  isThinking: false,
  streamingMessage: "",
  chatError: null,

  // Comparison mode state
  comparison: {
    isActive: false,
    context: null,
    selectedPairIndex: null,
    viewMode: "cards",
    expandedTopics: [],
  },

  // Multi-document PDF viewer state
  pdfViewer: {
    activeDocumentId: null,
    urlCache: {},
    highlightBbox: null,
    isLoadingUrl: false,
  },

  // Sessions list
  sessions: [],
  sessionsLoading: false,
};

export const createChatSlice = (set, get) => ({
  chat: initialChatState,
  ...createChatCollectionActions(set, get),
  ...createChatDocumentActions(set, get),
  ...createChatSessionActions(set, get),
  ...createChatMessageActions(set, get),
  ...createChatIndexingActions(set, get),
  ...createChatComparisonActions(set, get),
  ...createChatPdfActions(set, get),
});
