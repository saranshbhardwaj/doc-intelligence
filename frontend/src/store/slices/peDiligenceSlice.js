/**
 * PE Diligence Slice for Zustand Store
 *
 * Centralizes shared state across all PE Diligence pages:
 * - Room metadata (fetched once, shared across Documents/Analysis/Dashboard)
 * - Documents list (fetched once, avoids 3× redundant calls)
 * - Analysis job ID (persisted — survives page refresh for SSE reconnect)
 * - Analysis status (delta detection for Run Analysis button)
 * - Analysis completion signal (timestamp — child pages watch to re-fetch their data)
 */

import { getRoom, listRoomDocuments, getAnalysisStatus } from '../../api/pe-diligence';

export const createPeDiligenceSlice = (set) => ({
  // ========== State ==========
  peDiligence: {
    roomId: null,                // currently loaded room (for cache-busting on room switch)
    room: null,                  // object from getRoom()

    documents: [],
    documentsLoading: false,
    documentsError: null,

    analysisJobId: null,         // PERSISTED — for SSE reconnect on page refresh
    analysisWarnings: [],        // warnings from last completed analysis

    analysisStatus: null,        // { has_completed_run, has_delta, added_doc_count, removed_doc_count, last_run_completed_at }
    analysisStatusLoading: false,

    analysisCompletedAt: null,   // ISO string signal — child pages watch this to re-fetch their data
  },

  // ========== Actions ==========

  peLoadRoom: async (roomId, getToken) => {
    try {
      const room = await getRoom(getToken, roomId);
      set(s => ({ peDiligence: { ...s.peDiligence, room } }));
    } catch (err) {
      console.error('[peDiligence] peLoadRoom:', err);
    }
  },

  peLoadDocuments: async (roomId, getToken) => {
    set(s => ({ peDiligence: { ...s.peDiligence, documentsLoading: true, documentsError: null } }));
    try {
      const documents = await listRoomDocuments(getToken, roomId);
      set(s => ({ peDiligence: { ...s.peDiligence, documents, documentsLoading: false } }));
    } catch (err) {
      set(s => ({
        peDiligence: {
          ...s.peDiligence,
          documentsLoading: false,
          documentsError: err.message || 'Failed to load documents',
        },
      }));
    }
  },

  // Silent refresh — no loading spinner (used after upload, delete, analysis completion)
  peRefreshDocuments: async (roomId, getToken) => {
    try {
      const documents = await listRoomDocuments(getToken, roomId);
      set(s => ({ peDiligence: { ...s.peDiligence, documents } }));
    } catch (err) {
      console.error('[peDiligence] peRefreshDocuments:', err);
    }
  },

  peSetAnalysisJob: (roomId, jobId) => {
    set(s => ({ peDiligence: { ...s.peDiligence, roomId, analysisJobId: jobId } }));
  },

  peClearAnalysisJob: () => {
    set(s => ({ peDiligence: { ...s.peDiligence, analysisJobId: null } }));
  },

  peSetAnalysisWarnings: (warnings) => {
    set(s => ({ peDiligence: { ...s.peDiligence, analysisWarnings: warnings } }));
  },

  // Called by PELayout onComplete — triggers RoomAnalysis/RoomDashboard to re-fetch their data
  peMarkAnalysisCompleted: () => {
    set(s => ({ peDiligence: { ...s.peDiligence, analysisCompletedAt: new Date().toISOString() } }));
  },

  peRefreshAnalysisStatus: async (roomId, getToken) => {
    set(s => ({ peDiligence: { ...s.peDiligence, analysisStatusLoading: true } }));
    try {
      const analysisStatus = await getAnalysisStatus(getToken, roomId);
      set(s => ({ peDiligence: { ...s.peDiligence, analysisStatus, analysisStatusLoading: false } }));
    } catch {
      set(s => ({ peDiligence: { ...s.peDiligence, analysisStatusLoading: false } }));
    }
  },

  // Reset all room-scoped state when switching between rooms
  peClearRoom: () => {
    set(s => ({
      peDiligence: {
        ...s.peDiligence,
        room: null,
        documents: [],
        documentsLoading: false,
        documentsError: null,
        analysisJobId: null,
        analysisWarnings: [],
        analysisStatus: null,
        analysisStatusLoading: false,
        analysisCompletedAt: null,
      },
    }));
  },
});
