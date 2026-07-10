import { describe, expect, it } from 'vitest';
import { dealCandidates, mockLibraryDocuments } from '../data/mockDealCandidates';
import {
  filterLibraryDocuments,
  filterCandidates,
  formatCandidateLocation,
  getCandidateConfidence,
  getDefaultCandidate,
  getDocumentStatus,
  getEffectiveMissingItems,
  getHandoffBlockers,
  getExistingUnderwritingRunId,
  getLibraryDocumentType,
  getReadinessAction,
  isLibraryDocumentReady,
  getSuggestedLibraryDocuments,
  getUnderwritingReadiness,
  getWorkspaceMetrics,
  sortCandidates,
} from './acquisitionWorkspace';

describe('acquisitionWorkspace helpers', () => {
  it('summarizes acquisition workspace metrics', () => {
    const metrics = getWorkspaceMetrics(dealCandidates);

    expect(metrics.total).toBeGreaterThanOrEqual(8);
    expect(metrics.selfStorageLikely).toBeGreaterThanOrEqual(4);
    expect(metrics.readyToUnderwrite).toBeGreaterThanOrEqual(2);
    expect(metrics.missingDocs).toBeGreaterThanOrEqual(2);
  });

  it('filters by source, status, confidence, and text query', () => {
    const result = filterCandidates(dealCandidates, {
      sourceType: 'gmail',
      status: 'needs_docs',
      minConfidence: 80,
      query: 'austin',
    });

    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Austin Mini Storage');
  });

  it('prioritizes ready and high-confidence candidates first', () => {
    const [first] = sortCandidates(dealCandidates);

    expect(first.status).toBe('ready_to_underwrite');
    expect(first.assetClass).toBe('self_storage');
  });

  it('selects a ready self-storage candidate by default', () => {
    const candidate = getDefaultCandidate(dealCandidates);

    expect(candidate.status).toBe('ready_to_underwrite');
    expect(candidate.assetClass).toBe('self_storage');
  });

  it('formats location and document state safely', () => {
    const candidate = dealCandidates.find((item) => item.name === 'Tulsa Deal 169');

    expect(formatCandidateLocation(candidate)).toContain('Tulsa');
    expect(getDocumentStatus(candidate, 'om')).toBe('available');
    expect(getDocumentStatus(candidate, 't12')).toBe('missing');
    expect(getDocumentStatus({ documents: [{ doc_type: 'om', status: 'attached' }] }, 'om')).toBe('attached');
  });

  it('does not report document slots as missing after they are attached by doc_type', () => {
    const candidate = {
      missingItems: ['om', 'rent_roll', 't12', 'price'],
      documents: [
        { doc_type: 'om', status: 'attached', processingStatus: 'completed', hasEmbeddings: true },
        { doc_type: 'rent_roll', status: 'attached', processingStatus: 'completed', hasEmbeddings: true },
      ],
    };

    expect(getEffectiveMissingItems(candidate)).toEqual(['t12', 'price']);
  });

  it('suggests library documents that match the selected candidate first', () => {
    const candidate = dealCandidates.find((item) => item.name === 'Tulsa Deal 169');
    const suggestions = getSuggestedLibraryDocuments(candidate, mockLibraryDocuments);

    expect(suggestions[0].dealCandidateId).toBe(candidate.id);
    expect(suggestions.some((doc) => doc.type === 'rent_roll')).toBe(true);
    expect(suggestions.some((doc) => doc.type === 't12')).toBe(true);
  });

  it('filters mock library documents by query and type', () => {
    const result = filterLibraryDocuments(mockLibraryDocuments, {
      query: 'tulsa',
      type: 'rent_roll',
    });

    expect(result).toHaveLength(1);
    expect(result[0].name).toContain('Rent Roll');
  });

  it('infers likely Library document types from real document filenames', () => {
    expect(getLibraryDocumentType({ filename: 'Tulsa Storage Offering Memorandum.pdf' })).toBe('om');
    expect(getLibraryDocumentType({ name: 'Austin Mini Storage rent-roll.xlsx' })).toBe('rent_roll');
    expect(getLibraryDocumentType({ filename: 'Phoenix_T-12_statement.pdf' })).toBe('t12');
    expect(getLibraryDocumentType({ name: 'Property exterior photos.zip' })).toBe('photos');
    expect(getLibraryDocumentType({ name: 'Closing checklist.pdf' })).toBe('other');
  });

  it('preserves explicit Library document types before filename inference', () => {
    expect(getLibraryDocumentType({ doc_type: 'om', filename: 'Unknown document.pdf' })).toBe('om');
    expect(getLibraryDocumentType({ type: 'rent_roll', name: 'other.pdf' })).toBe('rent_roll');
  });

  it('detects ready Library documents from API and mock shapes', () => {
    expect(isLibraryDocumentReady({ status: 'completed', has_embeddings: true })).toBe(true);
    expect(isLibraryDocumentReady({ status: 'completed', chunk_count: 2 })).toBe(true);
    expect(isLibraryDocumentReady({ status: 'processing', has_embeddings: true })).toBe(false);
  });

  it('derives top-funnel confidence labels without making an investment recommendation', () => {
    expect(getCandidateConfidence({ assetClass: 'self_storage', assetClassConfidence: 92, evidence: [{ detail: 'OM references self storage' }] })).toMatchObject({
      label: 'Strong Match',
      tone: 'strong',
      percent: 92,
    });
    expect(getCandidateConfidence({ assetClass: 'self_storage', assetClassConfidence: 78, evidence: [] })).toMatchObject({
      label: 'Likely Match',
      tone: 'likely',
      percent: 78,
    });
    expect(getCandidateConfidence({ assetClass: 'unknown', assetClassConfidence: 58, evidence: [] })).toMatchObject({
      label: 'Needs Review',
      tone: 'review',
    });
    expect(getCandidateConfidence({ assetClass: 'retail', assetClassConfidence: 91, evidence: [] })).toMatchObject({
      label: 'Not Relevant',
      tone: 'muted',
    });
  });

  it('derives underwriting readiness separately from candidate confidence', () => {
    const baseCandidate = {
      id: 'candidate-1',
      assetClass: 'self_storage',
      assetClassConfidence: 95,
      underwritingRunId: null,
      documents: [],
    };

    expect(getUnderwritingReadiness(baseCandidate, { isPrototype: true })).toMatchObject({
      label: 'Sample Data',
      tone: 'muted',
    });
    expect(getUnderwritingReadiness(baseCandidate, { isPrototype: false })).toMatchObject({
      label: 'Needs Indexed OM',
      tone: 'warning',
    });
    expect(getUnderwritingReadiness({
      ...baseCandidate,
      documents: [{ type: 'om', status: 'attached', processingStatus: 'processing', chunkCount: 0 }],
    }, { isPrototype: false })).toMatchObject({
      label: 'OM Processing',
      tone: 'warning',
    });
    expect(getUnderwritingReadiness({
      ...baseCandidate,
      documents: [{ type: 'om', status: 'attached', processingStatus: 'completed', hasEmbeddings: true }],
    }, { isPrototype: false })).toMatchObject({
      label: 'Ready for Underwriting',
      tone: 'ready',
    });
    const inUnderwritingCandidate = { ...baseCandidate, underwritingRunId: 'run-1' };
    const inUnderwritingReadiness = getUnderwritingReadiness(inUnderwritingCandidate, { isPrototype: false });
    expect(inUnderwritingReadiness).toMatchObject({
      label: 'In Underwriting',
      tone: 'ready',
    });
    expect(inUnderwritingReadiness.blockers).toEqual(getHandoffBlockers(inUnderwritingCandidate, { isPrototype: false }));

    const lowConfidenceReadyCandidate = {
      ...baseCandidate,
      assetClassConfidence: 69,
      documents: [{ type: 'om', status: 'attached', processingStatus: 'completed', hasEmbeddings: true }],
    };
    expect(getUnderwritingReadiness(lowConfidenceReadyCandidate, { isPrototype: false })).toMatchObject({
      label: 'Needs Review',
      tone: 'warning',
      nextAction: 'Review the candidate classification.',
    });
    expect(getHandoffBlockers(lowConfidenceReadyCandidate, { isPrototype: false })).toContain('Review candidate confidence before underwriting.');
  });

  it('maps readiness states to primary action labels without investment recommendations', () => {
    expect(getReadinessAction({ label: 'Sample Data' })).toMatchObject({ label: 'Create Real Candidate', intent: 'create_candidate' });
    expect(getReadinessAction({ label: 'Needs Indexed OM' })).toMatchObject({ label: 'Attach from Library', intent: 'attach_library' });
    expect(getReadinessAction({ label: 'OM Processing' })).toMatchObject({ label: 'View Library Status', intent: 'view_library_status' });
    expect(getReadinessAction({ label: 'In Underwriting' })).toMatchObject({ label: 'Open Underwriting Run', intent: 'open_underwriting_run' });
    expect(getReadinessAction({ label: 'Ready for Underwriting' })).toMatchObject({ label: 'Create Full Underwriting Run', intent: 'create_underwriting_run' });
    expect(getReadinessAction({ label: 'Needs Review' })).toMatchObject({ label: 'Review Candidate', intent: 'review_candidate' });
  });

  it('normalizes existing underwriting run ids from API and frontend candidate shapes', () => {
    expect(getExistingUnderwritingRunId({ underwritingRunId: 'run-camel' })).toBe('run-camel');
    expect(getExistingUnderwritingRunId({ underwriting_run_id: 'run-snake' })).toBe('run-snake');
    expect(getExistingUnderwritingRunId({ underwritingRunId: null, underwriting_run_id: null })).toBeNull();
  });

  it('reports handoff blockers for persisted candidates', () => {
    const candidate = {
      id: 'candidate-1',
      assetClass: 'self_storage',
      underwritingRunId: null,
      documents: [],
    };

    expect(getHandoffBlockers(candidate, { isPrototype: false })).toContain('Attach an indexed OM document before creating a run.');
    expect(getHandoffBlockers({ ...candidate, assetClass: 'retail' }, { isPrototype: false })).toContain('Candidate is not self-storage.');
    expect(getHandoffBlockers({ ...candidate, underwritingRunId: 'run-1' }, { isPrototype: false })).toContain('Candidate already has an underwriting run.');
    expect(getHandoffBlockers({ ...candidate, documents: [{ type: 'om', status: 'available', processingStatus: 'completed', hasEmbeddings: true }] }, { isPrototype: false })).toEqual([]);
  });
});
