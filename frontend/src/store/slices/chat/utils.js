/**
 * Chat slice helpers
 */

export const getErrorMessage = (error) => {
  // Surface structured 403 limit errors from backend detail payload
  const detail = error?.response?.data?.detail;
  if (detail?.error === 'chat_limit_exceeded') {
    return "Daily chat message limit reached. Your limit resets at midnight UTC.";
  }
  return error?.message || "An unexpected error occurred";
};
