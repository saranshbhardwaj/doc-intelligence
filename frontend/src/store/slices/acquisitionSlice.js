import {
  attachCandidateDocument,
  createAcquisitionCandidate,
  createUnderwritingRunFromCandidate,
  detachCandidateDocument,
  listAcquisitionCandidates,
} from '../../api/re-acquisitions';

export const createAcquisitionSlice = (set) => ({
  acquisitions: {
    candidates: [],
    selectedCandidateId: null,
    isLoading: false,
    error: null,
    handoffStatus: 'idle',
  },

  loadAcquisitionCandidates: async (getToken) => {
    set((state) => ({
      acquisitions: { ...state.acquisitions, isLoading: true, error: null },
    }));
    try {
      const data = await listAcquisitionCandidates(getToken);
      set((state) => ({
        acquisitions: {
          ...state.acquisitions,
          candidates: data.candidates || [],
          selectedCandidateId: state.acquisitions.selectedCandidateId || data.candidates?.[0]?.id || null,
          isLoading: false,
          error: null,
        },
      }));
    } catch (err) {
      set((state) => ({
        acquisitions: {
          ...state.acquisitions,
          isLoading: false,
          error: err?.message || 'Failed to load acquisition candidates.',
        },
      }));
    }
  },

  selectAcquisitionCandidate: (candidateId) => {
    set((state) => ({
      acquisitions: { ...state.acquisitions, selectedCandidateId: candidateId },
    }));
  },

  createAcquisitionCandidate: async (getToken, payload) => {
    const candidate = await createAcquisitionCandidate(getToken, payload);
    set((state) => ({
      acquisitions: {
        ...state.acquisitions,
        candidates: [candidate, ...state.acquisitions.candidates],
        selectedCandidateId: candidate.id,
        error: null,
      },
    }));
    return candidate;
  },

  attachAcquisitionDocument: async (getToken, candidateId, payload) => {
    const candidate = await attachCandidateDocument(getToken, candidateId, payload);
    set((state) => ({
      acquisitions: {
        ...state.acquisitions,
        candidates: state.acquisitions.candidates.map((item) => (
          item.id === candidate.id ? candidate : item
        )),
      },
    }));
    return candidate;
  },

  detachAcquisitionDocument: async (getToken, candidateId, documentId) => {
    const candidate = await detachCandidateDocument(getToken, candidateId, documentId);
    set((state) => ({
      acquisitions: {
        ...state.acquisitions,
        candidates: state.acquisitions.candidates.map((item) => (
          item.id === candidate.id ? candidate : item
        )),
      },
    }));
    return candidate;
  },

  createRunFromAcquisitionCandidate: async (getToken, candidateId) => {
    set((state) => ({
      acquisitions: { ...state.acquisitions, handoffStatus: 'creating', error: null },
    }));
    try {
      const result = await createUnderwritingRunFromCandidate(getToken, candidateId);
      set((state) => ({
        acquisitions: {
          ...state.acquisitions,
          handoffStatus: 'created',
          candidates: state.acquisitions.candidates.map((item) => (
            item.id === candidateId
              ? { ...item, status: 'in_underwriting', underwritingRunId: result.run_id }
              : item
          )),
        },
      }));
      return result;
    } catch (err) {
      set((state) => ({
        acquisitions: {
          ...state.acquisitions,
          handoffStatus: 'error',
          error: err?.response?.data?.detail || err?.message || 'Failed to create underwriting run.',
        },
      }));
      throw err;
    }
  },
});