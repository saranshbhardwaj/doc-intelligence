/**
 * Feedback Fatigue Prevention Rules
 *
 * Controls when to auto-show feedback modals to prevent user fatigue
 * while still collecting useful feedback.
 *
 * Rules:
 * - Chat: Never auto-prompt (thumbs always visible but optional)
 * - Workflows: Max 1 prompt per 24 hours
 * - Template Fills: Max 1 prompt per 24 hours
 * - Extractions: Prompt every 5th extraction only
 *
 * Uses localStorage to track prompt history across sessions.
 */

const FEEDBACK_HISTORY_KEY = "feedback_prompt_history";
const MIN_PROMPT_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24 hours
const EXTRACTION_PROMPT_FREQUENCY = 5; // Every 5th extraction

/**
 * Get feedback prompt history from localStorage
 * @returns {Object} Feedback history object
 */
function getFeedbackHistory() {
  try {
    const history = localStorage.getItem(FEEDBACK_HISTORY_KEY);
    return history ? JSON.parse(history) : {};
  } catch (error) {
    console.warn("Failed to parse feedback history:", error);
    return {};
  }
}

/**
 * Save feedback prompt history to localStorage
 * @param {Object} history - Feedback history object
 */
function saveFeedbackHistory(history) {
  try {
    localStorage.setItem(FEEDBACK_HISTORY_KEY, JSON.stringify(history));
  } catch (error) {
    console.warn("Failed to save feedback history:", error);
  }
}

/**
 * Check if user should be prompted for feedback
 *
 * @param {string} operationType - "chat" | "workflow" | "template_fill" | "extraction"
 * @param {string} entityId - ID of the entity (for deduplication)
 * @returns {boolean} Whether to show feedback prompt
 */
export function shouldPromptForFeedback(operationType, entityId) {
  // Never auto-prompt for chat (thumbs are always visible)
  if (operationType === "chat") {
    return false;
  }

  const history = getFeedbackHistory();
  const now = Date.now();

  // Check if feedback already submitted for this entity
  const feedbackKey = `feedback_submitted_${operationType}_${entityId}`;
  if (localStorage.getItem(feedbackKey) === "true") {
    return false; // Already gave feedback for this specific entity
  }

  // For extractions: only prompt every Nth extraction
  if (operationType === "extraction") {
    const extractionCount = history.extraction_count || 0;
    const newCount = extractionCount + 1;

    // Update count
    saveFeedbackHistory({
      ...history,
      extraction_count: newCount,
    });

    // Only prompt if count is divisible by frequency
    if (newCount % EXTRACTION_PROMPT_FREQUENCY !== 0) {
      return false;
    }

    // Also check time-based rule
    const lastPrompt = history.extraction_last_prompt || 0;
    if (now - lastPrompt < MIN_PROMPT_INTERVAL_MS) {
      return false;
    }

    // Update last prompt time
    saveFeedbackHistory({
      ...history,
      extraction_count: newCount,
      extraction_last_prompt: now,
    });

    return true;
  }

  // For workflows and template fills: time-based rule only
  const lastPromptKey = `${operationType}_last_prompt`;
  const lastPrompt = history[lastPromptKey] || 0;

  if (now - lastPrompt < MIN_PROMPT_INTERVAL_MS) {
    return false; // Too soon since last prompt
  }

  // Update last prompt time
  saveFeedbackHistory({
    ...history,
    [lastPromptKey]: now,
  });

  return true;
}

/**
 * Mark feedback as submitted for a specific entity
 * This prevents prompting for the same entity again
 *
 * @param {string} operationType - "chat" | "workflow" | "template_fill" | "extraction"
 * @param {string} entityId - ID of the entity
 */
export function markFeedbackSubmitted(operationType, entityId) {
  const feedbackKey = `feedback_submitted_${operationType}_${entityId}`;
  localStorage.setItem(feedbackKey, "true");
}

/**
 * Check if feedback was already submitted for a specific entity
 *
 * @param {string} operationType - "chat" | "workflow" | "template_fill" | "extraction"
 * @param {string} entityId - ID of the entity
 * @returns {boolean} Whether feedback was already submitted
 */
export function hasFeedbackBeenSubmitted(operationType, entityId) {
  const feedbackKey = `feedback_submitted_${operationType}_${entityId}`;
  return localStorage.getItem(feedbackKey) === "true";
}

/**
 * Reset feedback prompt history (for testing or admin purposes)
 */
export function resetFeedbackHistory() {
  localStorage.removeItem(FEEDBACK_HISTORY_KEY);

  // Also clear all submitted feedback flags
  const keysToRemove = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith("feedback_submitted_")) {
      keysToRemove.push(key);
    }
  }
  keysToRemove.forEach((key) => localStorage.removeItem(key));
}
