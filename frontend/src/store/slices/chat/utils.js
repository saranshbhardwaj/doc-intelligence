/**
 * Chat slice helpers
 */

export const getErrorMessage = (error) => {
  return error?.message || "An unexpected error occurred";
};
