// src/api.js
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_URL,
  timeout: 300_000, // 3 minutes
  headers: {
    // common headers if needed
  },
});

export async function uploadFile(file, { onUploadProgress, signal } = {}) {
  // Use FormData so backend receives as multipart/form-data
  const form = new FormData();
  form.append("file", file);

  try {
    const response = await api.post("/api/extract", form, {
      onUploadProgress,
      signal, // AbortController signal
      // eslint-disable-next-line no-unused-vars
      validateStatus: (s) => true, // Let caller handle status codes
    });

    return response;
  } catch (err) {
    // Network or abort error
    if (axios.isCancel(err)) throw err;
    throw new Error(`Network error: ${err.message || String(err)}`);
  }
}
