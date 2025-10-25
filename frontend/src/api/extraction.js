// src/api/extraction.js
import { api } from "./client";

export async function uploadFile(file, { onUploadProgress, signal } = {}) {
  const form = new FormData();
  form.append("file", file);

  try {
    const response = await api.post("/api/extract", form, {
      onUploadProgress,
      signal,
      validateStatus: () => true,
    });
    return response;
  } catch (err) {
    if (axios.isCancel(err)) throw err;
    throw new Error(`Network error: ${err.message || String(err)}`);
  }
}
