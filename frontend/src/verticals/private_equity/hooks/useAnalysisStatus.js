import { useState, useEffect, useCallback } from "react";
import { getAnalysisStatus } from "../../../api/pe-diligence";

/**
 * Hook to check for document delta since last completed analysis run.
 * @param {string} roomId - Room ID
 * @param {Function} getToken - Function to get auth token
 * @returns {Object} { has_completed_run, has_delta, added_doc_count, removed_doc_count, last_run_completed_at, loading, error, refresh }
 */
export function useAnalysisStatus(roomId, { getToken }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(() => {
    if (!roomId || !getToken) {
      setStatus(null);
      return;
    }
    setLoading(true);
    setError(null);
    getAnalysisStatus(getToken, roomId)
      .then(data => {
        setStatus(data);
        setError(null);
      })
      .catch(err => {
        setError(err);
        setStatus(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [roomId, getToken]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  return {
    ...status,
    loading,
    error,
    refresh: fetchStatus,
  };
}
