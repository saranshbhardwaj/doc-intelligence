/**
 * Chat Mode API
 *
 * Handles all API calls for multi-document chat:
 * - Collections management
 * - Document uploads to collections
 * - Chat with RAG (SSE streaming)
 * - Session management
 * - Export functionality
 */

import { createAuthenticatedApi } from "./client";
import { streamJobProgress } from "./sse-utils";

/**
 * Collections API
 */

export async function createCollection(getToken, { name, description }) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("name", name);
  if (description) formData.append("description", description);

  const response = await api.post("/api/chat/collections", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function listCollections(
  getToken,
  { limit = 50, offset = 0 } = {}
) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get("/api/chat/collections", {
    params: { limit, offset },
  });
  return response.data;
}

export async function getCollection(getToken, collectionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/collections/${collectionId}`);
  return response.data;
}

export async function deleteCollection(getToken, collectionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/chat/collections/${collectionId}`);
  return response.data;
}

/**
 * Document Upload API
 */

export async function uploadDocument(getToken, collectionId, file, onProgress) {
  const api = createAuthenticatedApi(getToken);
  const formData = new FormData();
  formData.append("file", file);

  const response = await api.post(
    `/api/chat/collections/${collectionId}/documents`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          onProgress(percent);
        }
      },
    }
  );
  return response.data;
}

/**
 * Connect to SSE stream for document indexing progress
 *
 * Modernized to use the unified streamJobProgress utility with:
 * - Auto-reconnect on connection loss
 * - Initial state fetching for page refresh support
 * - Better error handling with actual error messages
 *
 * @param {Function} getToken - Clerk's getToken function
 * @param {string} jobId - Job ID to stream progress for
 * @param {Function} onProgress - Called with progress updates
 * @param {Function} onComplete - Called when indexing completes
 * @param {Function} onError - Called on error
 * @param {Object} options - Additional options
 * @param {boolean} options.autoReconnect - Enable auto-reconnect (default: true)
 * @param {boolean} options.fetchInitialState - Fetch initial state on mount (default: false)
 * @returns {Promise<Function>} Cleanup function to close the connection
 */
export async function connectToIndexingProgress(
  getToken,
  jobId,
  onProgress,
  onComplete,
  onError,
  { autoReconnect = true, fetchInitialState = false } = {}
) {
  // Use unified SSE utility with document indexing support
  return streamJobProgress(jobId, getToken, {
    onProgress,
    onComplete,
    onError: (errorData) => {
      // Convert error object to Error instance for backward compatibility
      const errorMsg =
        typeof errorData === "string"
          ? errorData
          : errorData?.message || "Indexing failed";
      onError(new Error(errorMsg));
    },
    onEnd: (data) => {
      console.log("[Document Indexing] SSE stream ended:", data?.reason);
    },
    autoReconnect,
    fetchInitialState,
    getJobStatus: fetchInitialState ? getJobStatus : null,
  });
}

/**
 * Get job status for document indexing
 * Used by SSE utility for initial state fetching
 */
async function getJobStatus(jobId, getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/jobs/${jobId}/status`);
  return response.data;
}

/**
 * Chat API (SSE streaming)
 *
 * Session-centric: Chat happens within a session that has its own documents
 */

export function sendChatMessage(
  getToken,
  sessionId,
  message,
  numChunks = 5,
  callbacks = {}
) {
  const { onSession, onChunk, onComplete, onError, onComparisonContext, onThinking } = callbacks;

  getToken().then((token) => {
    const formData = new FormData();
    formData.append("message", message);
    formData.append("num_chunks", numChunks.toString());

    // Use fetch for SSE streaming
    fetch(
      `${import.meta.env.VITE_API_URL}/api/chat/sessions/${sessionId}/chat`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
        },
        body: formData,
      }
    )
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${await response.text()}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || ""; // Keep incomplete event in buffer

          for (const event of events) {
            if (!event.trim()) continue;

            const lines = event.split("\n");
            let eventType = "";
            let eventData = "";

            for (const line of lines) {
              if (line.startsWith("event: ")) {
                eventType = line.slice(7);
              } else if (line.startsWith("data: ")) {
                eventData = line.slice(6);
              }
            }

            // Process event
            if (eventType === "session" && eventData) {
              const data = JSON.parse(eventData);
              onSession?.(data.session_id);
            } else if (eventType === "thinking" && eventData) {
              // Handle thinking event for progress feedback
              const data = JSON.parse(eventData);
              onThinking?.(data);
            } else if (eventType === "comparison_context" && eventData) {
              // Handle comparison context from backend
              const data = JSON.parse(eventData);
              onComparisonContext?.(data);
            } else if (eventType === "chunk" && eventData) {
              const data = JSON.parse(eventData);
              onChunk?.(data.chunk);
            } else if (eventType === "done") {
              onComplete?.();
            } else if (eventType === "error" && eventData) {
              const data = JSON.parse(eventData);
              onError?.(new Error(data.error));
            }
          }
        }
      })
      .catch((error) => {
        console.error("Chat streaming error:", error);
        onError?.(error);
      });
  });
}

/**
 * Session Management API
 *
 * Session-centric architecture:
 * - Sessions are independent of collections
 * - Each session maintains its own document selection
 */

export async function createSession(
  getToken,
  { title, description, documentIds }
) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post("/api/chat/sessions", {
    title,
    description,
    document_ids: documentIds,
  });
  return response.data;
}

export async function listSessions(getToken, { limit = 20, offset = 0 } = {}) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get("/api/chat/sessions", {
    params: { limit, offset },
  });
  return response.data;
}

export async function getSession(getToken, sessionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/sessions/${sessionId}`);
  return response.data;
}

export async function updateSession(getToken, sessionId, updates) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.patch(`/api/chat/sessions/${sessionId}`, updates);
  return response.data;
}

export async function addDocumentsToSession(getToken, sessionId, documentIds) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post(`/api/chat/sessions/${sessionId}/documents`, {
    document_ids: documentIds,
  });
  return response.data;
}

export async function removeDocumentFromSession(
  getToken,
  sessionId,
  documentId
) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(
    `/api/chat/sessions/${sessionId}/documents/${documentId}`
  );
  return response.data;
}

export async function getChatHistory(getToken, sessionId, limit) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/sessions/${sessionId}/messages`, {
    params: limit ? { limit } : {},
  });
  return response.data;
}

export async function deleteSession(getToken, sessionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/chat/sessions/${sessionId}`);
  return response.data;
}

/**
 * Document API
 */

export async function deleteDocument(getToken, documentId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(`/api/chat/documents/${documentId}`);
  return response.data;
}

export async function removeDocumentFromCollection(
  getToken,
  collectionId,
  documentId
) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.delete(
    `/api/chat/collections/${collectionId}/documents/${documentId}`
  );
  return response.data;
}

/**
 * Export API
 */

export async function exportSession(getToken, sessionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/sessions/${sessionId}/export`);
  return response.data;
}

/**
 * Document Usage API
 */

export async function getDocumentUsage(getToken, documentId) {
  /**
   * Get document usage information across all modes
   *
   * Input:
   *   - documentId: string
   *
   * Output:
   *   {
   *     document_id: string,
   *     document_name: string,
   *     usage: {
   *       chat_sessions: [
   *         {session_id: string, title: string, created_at: string},
   *         ...
   *       ],
   *       extracts: [
   *         {request_id: string, created_at: string, status: string},
   *         ...
   *       ],
   *       workflows: [
   *         {run_id: string, workflow_name: string, created_at: string},
   *         ...
   *       ]
   *     },
   *     total_usage_count: number
   *   }
   */
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/documents/${documentId}/usage`);
  return response.data;
}
