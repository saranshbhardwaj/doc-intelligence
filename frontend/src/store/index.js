/**
 * Main Zustand Store
 *
 * Combines all slices and provides centralized state management
 * with persistence for extraction state across navigation.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { useShallow } from 'zustand/react/shallow';
import { createExtractionSlice } from './slices/extractionSlice';
import { createUserSlice } from './slices/userSlice';

/**
 * Main store combining all slices
 */
export const useStore = create(
  persist(
    (...args) => ({
      ...createExtractionSlice(...args),
      ...createUserSlice(...args),
    }),
    {
      name: 'sand-cloud-storage', // localStorage key
      storage: createJSONStorage(() => sessionStorage), // Use sessionStorage for extraction state
      partialize: (state) => ({
        // Only persist extraction state (jobId, extractionId) for reconnection
        // Don't persist isProcessing or progress - they will be restored via reconnection
        // Don't persist user data (should be fetched fresh)
        extraction: {
          jobId: state.extraction.jobId,
          extractionId: state.extraction.extractionId,
        },
      }),
    }
  )
);

/**
 * Selector hooks for easy access to specific slices
 */

// Extraction selectors
export const useExtraction = () => useStore((state) => state.extraction);
export const useExtractionActions = () =>
  useStore(
    useShallow((state) => ({
      uploadDocument: state.uploadDocument,
      retryExtraction: state.retryExtraction,
      reconnectExtraction: state.reconnectExtraction,
      cancelExtraction: state.cancelExtraction,
      resetExtraction: state.resetExtraction,
      setResult: state.setResult,
      setError: state.setError,
      setProgress: state.setProgress,
      setProcessing: state.setProcessing,
    }))
  );

// User selectors
export const useUser = () => useStore((state) => state.user);
export const useUserActions = () =>
  useStore(
    useShallow((state) => ({
      fetchUserInfo: state.fetchUserInfo,
      fetchExtractions: state.fetchExtractions,
      loadMoreExtractions: state.loadMoreExtractions,
      refreshDashboard: state.refreshDashboard,
      clearUserData: state.clearUserData,
    }))
  );

export default useStore;
