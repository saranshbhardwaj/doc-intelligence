// src/api/feedback.js
import { api } from "./client";

export async function submitFeedback(feedbackData) {
  const response = await api.post("/api/feedback", feedbackData);
  return response.data;
}
