/**
 * Feedback API
 *
 * Handles feedback submission for all operation types:
 * - Chat messages (thumbs up/down)
 * - Workflow runs (star ratings)
 * - Template fills (star ratings)
 * - Extractions (star ratings)
 */

import { createAuthenticatedApi } from "./client";

/**
 * Submit feedback for any operation type
 *
 * @param {Function} getToken - Function to get auth token
 * @param {Object} feedbackData - Feedback data
 * @param {string} feedbackData.chat_message_id - Chat message ID (if chat feedback)
 * @param {string} feedbackData.workflow_run_id - Workflow run ID (if workflow feedback)
 * @param {string} feedbackData.template_fill_run_id - Template fill run ID (if template fill feedback)
 * @param {string} feedbackData.extraction_id - Extraction ID (if extraction feedback)
 * @param {string} feedbackData.rating_type - "thumbs" or "stars"
 * @param {number} feedbackData.rating_value - -1/1 for thumbs, 1-5 for stars
 * @param {string} feedbackData.comment - Optional comment
 * @param {string} feedbackData.feedback_category - Optional category (accuracy, speed, format, missing_data, other)
 * @param {Array<string>} feedbackData.tags - Optional tags
 * @param {Object} feedbackData.context_snapshot - Optional context snapshot
 * @returns {Promise<Object>} Response with success, message, and feedback_id
 */
export async function submitFeedback(getToken, feedbackData) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.post("/api/feedback", feedbackData);
  return response.data;
}
