import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { DatabaseZap, Plus, RadioTower } from 'lucide-react';

import CandidateDetailPanel from '../components/acquisitions/CandidateDetailPanel';
import CandidateQueue from '../components/acquisitions/CandidateQueue';
import HandoffPreviewDialog from '../components/acquisitions/HandoffPreviewDialog';
import LibraryDocumentPickerDialog from '../components/acquisitions/LibraryDocumentPickerDialog';
import NewCandidateDialog from '../components/acquisitions/NewCandidateDialog';
import SourceHealthPanel from '../components/acquisitions/SourceHealthPanel';
import { useAppAuth } from '../../../hooks/useAppAuth';
import { useAcquisitionActions, useAcquisitions } from '../../../store';
import { listCollections } from '../../../api';
import { dealCandidates, mockLibraryDocuments, sourceConnectors } from '../data/mockDealCandidates';
import { filterCandidates, getDefaultCandidate, getLibraryDocumentType, getWorkspaceMetrics } from '../utils/acquisitionWorkspace';

export default function AcquisitionWorkspacePage() {
  const navigate = useNavigate();
  const { getToken } = useAppAuth();
  const acquisitions = useAcquisitions();
  const {
    createRunFromAcquisitionCandidate,
    createAcquisitionCandidate,
    attachAcquisitionDocument,
    detachAcquisitionDocument,
    loadAcquisitionCandidates,
    selectAcquisitionCandidate,
  } = useAcquisitionActions();
  const [filters, setFilters] = useState({ sourceType: 'all', status: 'all', minConfidence: 0, query: '' });
  const [selectedId, setSelectedId] = useState(() => getDefaultCandidate(dealCandidates)?.id || null);
  const [handoffOpen, setHandoffOpen] = useState(false);
  const [libraryPickerOpen, setLibraryPickerOpen] = useState(false);
  const [libraryDocuments, setLibraryDocuments] = useState([]);
  const [isAttachingDocument, setIsAttachingDocument] = useState(false);
  const [detachingDocumentId, setDetachingDocumentId] = useState(null);
  const [newCandidateOpen, setNewCandidateOpen] = useState(false);
  const [sourceStatusOpen, setSourceStatusOpen] = useState(false);
  const apiCandidates = acquisitions.candidates || [];
  const isMockMode = !apiCandidates.length;
  const candidates = isMockMode ? dealCandidates : apiCandidates;
  const metrics = useMemo(() => getWorkspaceMetrics(candidates), [candidates]);
  const filteredCandidates = useMemo(() => filterCandidates(candidates, filters), [candidates, filters]);
  const selectedCandidate = filteredCandidates.find((candidate) => candidate.id === selectedId) || filteredCandidates[0] || null;

  useEffect(() => {
    loadAcquisitionCandidates(getToken);
  }, [getToken, loadAcquisitionCandidates]);

  useEffect(() => {
    if (selectedCandidate?.id) {
      selectAcquisitionCandidate(selectedCandidate.id);
    }
  }, [selectAcquisitionCandidate, selectedCandidate?.id]);

  const handleCreateRun = async () => {
    if (!selectedCandidate || isMockMode) return null;
    const result = await createRunFromAcquisitionCandidate(getToken, selectedCandidate.id);
    if (result?.run_id) {
      navigate(`/app/re/underwriting/new?run_id=${result.run_id}`);
    }
    return result;
  };

  const handleCreateCandidate = async (payload) => {
    const candidate = await createAcquisitionCandidate(getToken, payload);
    setSelectedId(candidate.id);
    return candidate;
  };

  const loadLibraryDocuments = async () => {
    if (isMockMode) return;
    try {
      const response = await listCollections(getToken, { includeDocuments: true });
      const docs = (response.collections || []).flatMap((collection) => (
        (collection.documents || []).map((doc) => ({
          ...doc,
          name: doc.filename || doc.name,
          type: getLibraryDocumentType(doc),
          fileType: doc.filename?.split('.').pop()?.toUpperCase() || 'FILE',
          collectionName: collection.name,
        }))
      )).filter((doc) => doc.status === 'completed' && doc.has_embeddings);
      setLibraryDocuments(docs);
    } catch (err) {
      console.error('Failed to load Library documents:', err);
    }
  };

  const handleOpenLibraryPicker = () => {
    setLibraryPickerOpen(true);
    loadLibraryDocuments();
  };

  const handleAttachLibraryDocument = async (payload) => {
    if (!selectedCandidate || isMockMode) return null;
    setIsAttachingDocument(true);
    try {
      const candidate = await attachAcquisitionDocument(getToken, selectedCandidate.id, payload);
      setSelectedId(candidate.id);
      return candidate;
    } finally {
      setIsAttachingDocument(false);
    }
  };

  const handleDetachLibraryDocument = async (doc) => {
    const documentId = doc?.document_id || doc?.documentId || doc?.id;
    if (!selectedCandidate || isMockMode || !documentId) return null;
    setDetachingDocumentId(documentId);
    try {
      const candidate = await detachAcquisitionDocument(getToken, selectedCandidate.id, documentId);
      setSelectedId(candidate.id);
      return candidate;
    } finally {
      setDetachingDocumentId(null);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="border-b border-border/70 bg-card/40 px-5 py-4 sm:px-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
              <DatabaseZap className="h-3.5 w-3.5" /> Deal Discovery
            </div>
            <h1 className="mt-1 text-2xl font-semibold tracking-tight text-foreground">Acquisition Workspace</h1>
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">
              Self-storage deal discovery feeding underwriting and IC memo generation.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSourceStatusOpen(true)}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground"
            >
              <RadioTower className="h-4 w-4" /> Source Status
            </button>
            <button
              type="button"
              onClick={() => setNewCandidateOpen(true)}
              className="inline-flex items-center gap-2 rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground"
            >
              <Plus className="h-4 w-4" /> New Candidate
            </button>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Candidates" value={metrics.total} />
          <Metric label="Self-storage likely" value={metrics.selfStorageLikely} />
          <Metric label="Ready to underwrite" value={metrics.readyToUnderwrite} />
          <Metric label="Missing docs" value={metrics.missingDocs} />
        </div>
        {isMockMode ? (
          <p className="mt-3 text-xs text-muted-foreground">
            Showing mock candidates until acquisition candidates are created through the API.
          </p>
        ) : null}
      </div>
      <div className="grid gap-3 p-4 lg:grid-cols-[minmax(380px,0.95fr)_minmax(520px,1.25fr)] lg:p-5">
        <CandidateQueue
          candidates={filteredCandidates}
          filters={filters}
          onFiltersChange={setFilters}
          selectedId={selectedCandidate?.id}
          onSelect={setSelectedId}
          isPrototype={isMockMode}
        />
        <CandidateDetailPanel
          candidate={selectedCandidate}
          onCreateCandidate={() => setNewCandidateOpen(true)}
          onOpenHandoff={() => setHandoffOpen(true)}
          onOpenLibrary={handleOpenLibraryPicker}
          onDetachDocument={handleDetachLibraryDocument}
          detachingDocumentId={detachingDocumentId}
          onOpenUnderwritingRun={(runId) => navigate(`/app/re/underwriting/new?run_id=${encodeURIComponent(runId)}`)}
          isPrototype={isMockMode}
        />
        <HandoffPreviewDialog
          open={handoffOpen}
          candidate={selectedCandidate}
          onClose={() => setHandoffOpen(false)}
          onCreate={handleCreateRun}
          isCreating={acquisitions.handoffStatus === 'creating'}
          error={acquisitions.error}
          isPrototype={isMockMode}
        />
        <SourceHealthPanel
          connectors={sourceConnectors}
          open={sourceStatusOpen}
          onClose={() => setSourceStatusOpen(false)}
        />
        <LibraryDocumentPickerDialog
          open={libraryPickerOpen}
          candidate={selectedCandidate}
          documents={isMockMode ? mockLibraryDocuments : libraryDocuments}
          onClose={() => setLibraryPickerOpen(false)}
          onAttach={handleAttachLibraryDocument}
          isAttaching={isAttachingDocument}
          isPrototype={isMockMode}
        />
        <NewCandidateDialog
          open={newCandidateOpen}
          onClose={() => setNewCandidateOpen(false)}
          onCreate={handleCreateCandidate}
        />
      </div>
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/80 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
    </div>
  );
}