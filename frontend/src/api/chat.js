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

export async function listCollections(getToken, { limit = 50, offset = 0 } = {}) {
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
export function connectToIndexingProgress(getToken, jobId, onProgress, onComplete, onError) {
  getToken().then((token) => {
    // Pass token as query parameter (EventSource doesn't support headers)
    const eventSource = new EventSource(
      `${import.meta.env.VITE_API_URL}/api/chat/jobs/${jobId}/progress?token=${encodeURIComponent(token)}`
    );

    eventSource.addEventListener("progress", (event) => {
      try {
        const data = JSON.parse(event.data);
        onProgress(data);

        if (data.status === "completed") {
          eventSource.close();
          onComplete(data);
        } else if (data.status === "failed") {
          eventSource.close();
          onError(new Error(data.error_message || "Indexing failed"));
        }
      } catch (err) {
        console.error("Failed to parse progress event:", err);
      }
    });

    eventSource.onerror = (error) => {
      console.error("SSE connection error:", error);
      eventSource.close();
      onError(new Error("Connection lost"));
    };

    return () => eventSource.close();
  });
}

/**
 * Chat API (SSE streaming)
 */

export function sendChatMessage(
  getToken,
  collectionId,
  message,
  sessionId,
  numChunks = 5,
  callbacks = {}
) {
  const { onSession, onChunk, onComplete, onError } = callbacks;

  getToken().then((token) => {
    const formData = new FormData();
    formData.append("message", message);
    if (sessionId) formData.append("session_id", sessionId);
    formData.append("num_chunks", numChunks.toString());

    // Use fetch for SSE streaming
    fetch(
      `${import.meta.env.VITE_API_URL}/api/chat/collections/${collectionId}/chat`,
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
 */

export async function listSessions(getToken, collectionId, limit = 20) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(
    `/api/chat/collections/${collectionId}/sessions`,
    {
      params: { limit },
    }
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
 * Export API
 */

export async function exportSession(getToken, sessionId) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/chat/sessions/${sessionId}/export`);
  return response.data;
}
