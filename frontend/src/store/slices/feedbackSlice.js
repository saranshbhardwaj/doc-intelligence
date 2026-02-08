/**
 * Feedback Slice
 *
 * Manages feedback submission state and UI coordination.
 * Integrates with localStorage for persistence via feedbackRules.js
 */

import {
  markFeedbackSubmitted,
  hasFeedbackBeenSubmitted,
} from "../../utils/feedbackRules";

export const createFeedbackSlice = (set, get) => ({
  feedback: {
    // Track which modals are currently open
    openModals: {}, // { [entityId]: true/false }

    // Track feedback submission in progress
    submitting: {}, // { [entityId]: true/false }
  },

  // Open feedback modal for an entity
  openFeedbackModal: (operationType, entityId) => {
    set((state) => ({
      feedback: {
        ...state.feedback,
        openModals: {
          ...state.feedback.openModals,
          [`${operationType}_${entityId}`]: true,
        },
      },
    }));
  },

  // Close feedback modal for an entity
  closeFeedbackModal: (operationType, entityId) => {
    set((state) => ({
      feedback: {
        ...state.feedback,
        openModals: {
          ...state.feedback.openModals,
          [`${operationType}_${entityId}`]: false,
        },
      },
    }));
  },

  // Check if feedback modal is open
  isFeedbackModalOpen: (operationType, entityId) => {
    const state = get();
    return state.feedback.openModals[`${operationType}_${entityId}`] || false;
  },

  // Mark feedback as submitted (updates localStorage and state)
  submitFeedback: (operationType, entityId) => {
    // Update localStorage via utility
    markFeedbackSubmitted(operationType, entityId);

    // Close modal
    set((state) => ({
      feedback: {
        ...state.feedback,
        openModals: {
          ...state.feedback.openModals,
          [`${operationType}_${entityId}`]: false,
        },
        submitting: {
          ...state.feedback.submitting,
          [`${operationType}_${entityId}`]: false,
        },
      },
    }));
  },

  // Check if feedback has been submitted for an entity
  hasFeedbackBeenSubmitted: (operationType, entityId) => {
    return hasFeedbackBeenSubmitted(operationType, entityId);
  },

  // Set feedback submission in progress
  setFeedbackSubmitting: (operationType, entityId, isSubmitting) => {
    set((state) => ({
      feedback: {
        ...state.feedback,
        submitting: {
          ...state.feedback.submitting,
          [`${operationType}_${entityId}`]: isSubmitting,
        },
      },
    }));
  },

  // Check if feedback is being submitted
  isFeedbackSubmitting: (operationType, entityId) => {
    const state = get();
    return state.feedback.submitting[`${operationType}_${entityId}`] || false;
  },
});
