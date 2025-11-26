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
 * NOTE: EventSource doesn't support custom headers, so auth token is passed as query parameter
 */
export function connectToIndexingProgress(
  getToken,
  jobId,
  onProgress,
  onComplete,
  onError
) {
  getToken().then((token) => {
    // Pass token as query parameter (EventSource doesn't support headers)
    const eventSource = new EventSource(
      `${
        import.meta.env.VITE_API_URL
      }/api/chat/jobs/${jobId}/progress?token=${encodeURIComponent(token)}`
    );

    let endEventReceived = false; // Track if we received the end event

    eventSource.addEventListener("progress", (event) => {
      try {
        const data = JSON.parse(event.data);
        onProgress(data);
      } catch (err) {
        console.error("Failed to parse progress event:", err);
      }
    });

    eventSource.addEventListener("complete", (event) => {
      try {
        const data = JSON.parse(event.data);
        onComplete(data);
      } catch (err) {
        console.error("Failed to parse complete event:", err);
      }
    });

    eventSource.addEventListener("error", (event) => {
      try {
        const data = JSON.parse(event.data);
        eventSource.close();
        endEventReceived = true;
        onError(new Error(data.message || "Indexing failed"));
      } catch (err) {
        console.error("Failed to parse error event:", err);
      }
    });

    eventSource.addEventListener("end", (event) => {
      console.log("Received end event, closing SSE connection");
      endEventReceived = true;
      eventSource.close();
    });

    eventSource.onerror = (error) => {
      // Only treat as error if we didn't receive the end event
      if (!endEventReceived) {
        console.error("SSE connection error:", error);
        eventSource.close();
        onError(new Error("Connection lost"));
      }
    };

    return () => eventSource.close();
  });
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
  const { onSession, onChunk, onComplete, onError } = callbacks;

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
