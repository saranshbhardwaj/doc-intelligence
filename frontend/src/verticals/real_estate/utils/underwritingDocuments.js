export const EMPTY_UNDERWRITING_DOCS = { om: null, t12: null, rent_roll: null };

const SLOT_LABELS = {
  om: 'Offering Memorandum',
  t12: 'T-12 / T-6 Statement',
  rent_roll: 'Rent Roll',
};

export function buildSelectedDocsFromRun(run) {
  const docs = Array.isArray(run?.source_documents) && run.source_documents.length
    ? run.source_documents
    : run?.document_ids || [];

  return docs.reduce((acc, doc) => {
    const docType = doc?.doc_type;
    const documentId = doc?.document_id || doc?.id;
    if (!docType || !documentId || !(docType in acc)) return acc;

    acc[docType] = {
      document_id: documentId,
      doc_type: docType,
      name: doc.name || doc.filename || SLOT_LABELS[docType] || 'Document',
    };
    return acc;
  }, { ...EMPTY_UNDERWRITING_DOCS });
}

export function buildSelectedDoc(docType, document) {
  if (!docType || !document) return null;
  return {
    document_id: document.id,
    doc_type: docType,
    name: document.name || document.filename || 'Document',
  };
}

export function buildExtractionDocuments(selectedDocs, fallbackDocuments = []) {
  const selected = Object.values(selectedDocs || {})
    .filter(Boolean)
    .map(({ document_id, doc_type }) => ({ document_id, doc_type }));

  if (selected.length) return selected;

  return (fallbackDocuments || []).filter(
    (doc) => doc && typeof doc === 'object' && doc.document_id && doc.doc_type,
  );
}

export function hydrateProjectDataFromRun(previousProjectData, run) {
  if (!run) return previousProjectData;

  const { name: _ignoredName, ...projectInputs } = run.inputs?.project || {};
  return {
    ...previousProjectData,
    ...projectInputs,
    name: run.name || previousProjectData.name,
    address: run.address || projectInputs.address || previousProjectData.address,
  };
}
