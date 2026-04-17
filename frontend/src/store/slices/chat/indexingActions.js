/**
 * Indexing actions
 */
import { streamJobProgress } from "../../../api/sse-utils";
import { getJobStatus } from "../../../api/chat";

export const createChatIndexingActions = (set, get) => ({
  startDocumentIndexing: (jobId, documentId, collectionId, cleanup) => {
    set((state) => ({
      chat: {
        ...state.chat,
        indexingJobs: {
          ...state.chat.indexingJobs,
          [documentId]: {
            jobId,
            documentId,
            collectionId,
            isProcessing: true,
            progress_percent: 0,
            current_stage: "uploading",
            message: "Starting indexing...",
            error: null,
            cleanup,
          },
        },
      },
    }));
  },

  updateIndexingProgress: (documentId, progressData) => {
    set((state) => {
      const existingJob = state.chat.indexingJobs[documentId];
      if (!existingJob) {
        console.warn(`No indexing job found for document ${documentId}`);
        return state;
      }

      return {
        chat: {
          ...state.chat,
          indexingJobs: {
            ...state.chat.indexingJobs,
            [documentId]: {
              ...existingJob,
              progress_percent: progressData.progress_percent || 0,
              current_stage: progressData.current_stage,
              message: progressData.message,
            },
          },
        },
      };
    });
  },

  completeIndexing: (documentId) => {
    set((state) => {
      const job = state.chat.indexingJobs[documentId];

      if (job?.cleanup) {
        job.cleanup();
      }

      const { [documentId]: _, ...remainingJobs } = state.chat.indexingJobs;

      return {
        chat: {
          ...state.chat,
          indexingJobs: remainingJobs,
        },
      };
    });
  },

  failIndexing: (documentId, errorMessage) => {
    set((state) => {
      const existingJob = state.chat.indexingJobs[documentId];
      if (!existingJob) {
        console.warn(`No indexing job found for document ${documentId}`);
        return state;
      }

      return {
        chat: {
          ...state.chat,
          indexingJobs: {
            ...state.chat.indexingJobs,
            [documentId]: {
              ...existingJob,
              isProcessing: false,
              error: errorMessage,
            },
          },
        },
      };
    });
  },

  reconnectAllIndexingJobs: async (getToken) => {
    const { indexingJobs } = get().chat;

    if (!indexingJobs || Object.keys(indexingJobs).length === 0) {
      return;
    }

    const reconnectPromises = Object.entries(indexingJobs).map(
      async ([docId, job]) => {
        if (!job.jobId || job.cleanup) {
          return;
        }

        try {
          const cleanup = await streamJobProgress(job.jobId, getToken, {
            onProgress: (data) => {
              get().updateIndexingProgress(docId, data);
            },
            onComplete: () => {
              get().completeIndexing(docId);
            },
            onError: (errorData) => {
              const errorMsg =
                typeof errorData === "string"
                  ? errorData
                  : errorData?.message || "Indexing failed";

              if (
                errorData?.type === "not_found" ||
                errorData?.type === "connection_error"
              ) {
                get().clearIndexingJob(docId);
                return;
              }

              get().failIndexing(docId, errorMsg);
            },
            onEnd: () => {},
            fetchInitialState: true,
            getJobStatus,
          });

          // Guard: if the job was already completed/cleared by onComplete above,
          // don't re-add it. Spreading a missing entry would create a zombie
          // job with isProcessing: true that never resolves.
          set((state) => {
            const existing = state.chat.indexingJobs[docId];
            if (!existing) return state;
            return {
              chat: {
                ...state.chat,
                indexingJobs: {
                  ...state.chat.indexingJobs,
                  [docId]: { ...existing, cleanup, isProcessing: true },
                },
              },
            };
          });
        } catch (err) {
          console.error(`Reconnection failed for document ${docId}:`, err);
          get().failIndexing(docId, "Failed to reconnect");
        }
      }
    );

    await Promise.allSettled(reconnectPromises);
  },

  clearIndexingJob: (documentId) => {
    set((state) => {
      const job = state.chat.indexingJobs[documentId];

      if (job?.cleanup) {
        job.cleanup();
      }

      const { [documentId]: _, ...remainingJobs } = state.chat.indexingJobs;

      return {
        chat: {
          ...state.chat,
          indexingJobs: remainingJobs,
        },
      };
    });
  },

  clearAllIndexingJobs: () => {
    set((state) => {
      Object.values(state.chat.indexingJobs).forEach((job) => {
        if (job.cleanup) {
          job.cleanup();
        }
      });

      return {
        chat: {
          ...state.chat,
          indexingJobs: {},
        },
      };
    });
  },
});
