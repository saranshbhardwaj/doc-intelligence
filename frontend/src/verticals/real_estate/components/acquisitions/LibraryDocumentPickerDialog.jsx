import { useMemo, useState } from 'react';
import { FileSearch, X } from 'lucide-react';
import { filterLibraryDocuments, getLibraryDocumentType, getSuggestedLibraryDocuments, labelFromSnake } from '../../utils/acquisitionWorkspace';

const ASSIGNMENT_LABELS = {
  om: 'Offering Memorandum',
  rent_roll: 'Rent Roll',
  t12: 'T-12 / T-6 Statement',
  photos: 'Photos',
  other: 'Other',
};

export default function LibraryDocumentPickerDialog({ open, candidate, documents, onClose, onAttach, isAttaching = false, isPrototype = true }) {
  const [query, setQuery] = useState('');
  const [type, setType] = useState('all');
  const [selectedId, setSelectedId] = useState(null);
  const [assignAs, setAssignAs] = useState('om');

  const suggestedDocuments = useMemo(
    () => getSuggestedLibraryDocuments(candidate, documents),
    [candidate, documents],
  );
  const visibleDocuments = useMemo(
    () => filterLibraryDocuments(suggestedDocuments, { query, type }),
    [query, suggestedDocuments, type],
  );
  const selectedDocument = visibleDocuments.find((doc) => doc.id === selectedId);
  const assignmentLabel = ASSIGNMENT_LABELS[assignAs] || labelFromSnake(assignAs);

  if (!open || !candidate) return null;

  const handleAttach = async () => {
    if (!selectedDocument || !onAttach || isPrototype) return;
    await onAttach({ document_id: selectedDocument.id, doc_type: assignAs });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
      <div className="absolute inset-x-4 bottom-4 top-4 mx-auto flex max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-card shadow-xl sm:bottom-auto sm:max-h-[calc(100vh-4rem)]">
        <div className="shrink-0 border-b border-border px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Attach documents from Library</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Candidate: {candidate.name}. {isPrototype ? 'This prototype previews the attachment flow only.' : 'Choose the underwriting slot for each indexed Library document.'}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label="Close library document picker"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="grid gap-2 sm:grid-cols-[1fr_160px]">
            <label className="relative">
              <FileSearch className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search Library documents..."
                className="h-9 w-full rounded-md border border-border bg-background pl-8 pr-3 text-sm text-foreground outline-none"
              />
            </label>
            <select
              value={type}
              onChange={(event) => setType(event.target.value)}
              className="h-9 rounded-md border border-border bg-background px-2 text-sm text-foreground"
            >
              <option value="all">All types</option>
              <option value="om">OM</option>
              <option value="rent_roll">Rent roll</option>
              <option value="t12">T-12</option>
              <option value="photos">Photos</option>
              <option value="other">Other</option>
            </select>
          </div>

          <div className="mt-3 max-h-[min(360px,38vh)] space-y-2 overflow-y-auto pr-1">
            {visibleDocuments.map((doc) => {
              const selected = doc.id === selectedId;
              const suggested = doc.dealCandidateId === candidate.id;
              const docType = getLibraryDocumentType(doc);
              return (
                <button
                  key={doc.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(doc.id);
                    if (docType !== 'other') {
                      setAssignAs(docType);
                    }
                  }}
                  className={`w-full rounded-md border p-3 text-left transition-colors ${
                    selected ? 'border-primary/40 bg-primary/5' : 'border-border/70 bg-background/70 hover:border-primary/25'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-foreground">{doc.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {doc.fileType} · {labelFromSnake(docType)} · {doc.pages ? `${doc.pages} pages` : 'page count n/a'}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      {suggested ? (
                        <span className="rounded-full border border-primary/25 bg-primary/5 px-2 py-0.5 text-[10px] font-medium text-primary">
                          Suggested
                        </span>
                      ) : null}
                      <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {labelFromSnake(docType)}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
            {!visibleDocuments.length ? (
              <div className="rounded-md border border-border/70 bg-background/70 p-4 text-sm text-muted-foreground">
                No Library documents match this filter.
              </div>
            ) : null}
          </div>

          <div className="mt-4 rounded-md border border-border/70 bg-background/70 p-3">
            <div className="grid gap-2 sm:grid-cols-[1fr_180px] sm:items-end">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">Attachment preview</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {selectedDocument ? `${selectedDocument.name} will be attached as ${assignmentLabel} for ${candidate.name}.` : 'Select a Library document to preview the attachment.'}
                </p>
              </div>
              <label className="text-xs font-medium text-muted-foreground">
                Attach selected as
                <select
                  value={assignAs}
                  onChange={(event) => setAssignAs(event.target.value)}
                  className="mt-1 h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
                >
                  <option value="om">Offering Memorandum</option>
                  <option value="rent_roll">Rent Roll</option>
                  <option value="t12">T-12 / T-6 Statement</option>
                  <option value="photos">Photos</option>
                  <option value="other">Other</option>
                </select>
              </label>
            </div>
          </div>
        </div>
        <div className="shrink-0 border-t border-border px-4 py-3">
          <p className="mb-2 text-xs text-muted-foreground">
            Uploads stay in Library first, where Azure Document Intelligence parses documents before chunking and embeddings make them available to underwriting.
          </p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground">
              Cancel
            </button>
            <button
              type="button"
              disabled={!selectedDocument || isPrototype || isAttaching}
              onClick={handleAttach}
              className={`rounded-md px-3 py-2 text-sm font-medium ${
                isPrototype
                  ? 'bg-muted text-muted-foreground opacity-70'
                  : 'bg-primary text-primary-foreground disabled:opacity-70'
              }`}
            >
              {isPrototype ? 'Attach - Coming Soon' : isAttaching ? 'Attaching...' : `Attach as ${assignmentLabel}`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}