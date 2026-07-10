const STATUS_RANK = {
  ready_to_underwrite: 0,
  in_underwriting: 1,
  needs_docs: 2,
  needs_review: 3,
  new: 4,
  watchlist: 5,
  archived: 6,
  not_relevant: 7,
};

const PRIORITY_RANK = { high: 0, medium: 1, low: 2 };

const LIBRARY_DOCUMENT_TYPES = new Set(['om', 'rent_roll', 't12', 'photos', 'other']);
const UNDERWRITING_DOCUMENT_TYPES = new Set(['om', 'rent_roll', 't12']);

function normalizeLibraryDocumentType(value) {
  const normalized = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  if (normalized === 'rentroll' || normalized === 'rent_rolls') return 'rent_roll';
  if (normalized === 't_12' || normalized === 'ttm') return 't12';
  if (normalized === 'photo') return 'photos';
  return LIBRARY_DOCUMENT_TYPES.has(normalized) ? normalized : null;
}

function getAssetClassConfidencePercent(candidate) {
  return Math.round(candidate?.assetClassConfidence ?? ((candidate?.asset_class_confidence || 0) * 100));
}

function needsCandidateConfidenceReview(candidate) {
  const rawConfidence = candidate?.assetClassConfidence ?? candidate?.asset_class_confidence;
  return rawConfidence != null && (candidate?.assetClass || candidate?.asset_class) === 'self_storage' && getAssetClassConfidencePercent(candidate) < 70;
}

export function getLibraryDocumentType(doc) {
  const explicitType = normalizeLibraryDocumentType(doc?.doc_type || doc?.type);
  if (explicitType) return explicitType;

  const name = [doc?.filename, doc?.name, doc?.file_name, doc?.original_filename]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  if (!name) return 'other';
  if (/(^|[^a-z0-9])(rent\s*roll|rent-roll|rent_roll|rr)([^a-z0-9]|$)/.test(name)) return 'rent_roll';
  if (/(^|[^a-z0-9])(t\s*[-_]?\s*12|twelve\s*month|trailing\s*(twelve|12)|operating\s*statement)([^a-z0-9]|$)/.test(name)) return 't12';
  if (/\b(photo|photos|image|images|pictures?)\b/.test(name)) return 'photos';
  if (/\b(om|offering\s*(memorandum|memo)|information\s*memorandum|cim)\b/.test(name)) return 'om';
  return 'other';
}

export function getReadinessAction(readiness) {
  switch (readiness?.label) {
    case 'Sample Data':
      return { label: 'Create Real Candidate', intent: 'create_candidate' };
    case 'Needs Indexed OM':
      return { label: 'Attach from Library', intent: 'attach_library' };
    case 'OM Processing':
      return { label: 'View Library Status', intent: 'view_library_status' };
    case 'In Underwriting':
      return { label: 'Open Underwriting Run', intent: 'open_underwriting_run' };
    case 'Ready for Underwriting':
      return { label: 'Create Full Underwriting Run', intent: 'create_underwriting_run' };
    case 'Needs Review':
      return { label: 'Review Candidate', intent: 'review_candidate' };
    default:
      return { label: 'Review Candidate', intent: 'review_candidate' };
  }
}

export function getExistingUnderwritingRunId(candidate) {
  return candidate?.underwritingRunId || candidate?.underwriting_run_id || null;
}

export function getWorkspaceMetrics(candidates) {
  const list = Array.isArray(candidates) ? candidates : [];
  return {
    total: list.length,
    selfStorageLikely: list.filter((candidate) => (
      candidate.assetClass === 'self_storage' && candidate.assetClassConfidence >= 80
    )).length,
    readyToUnderwrite: list.filter((candidate) => candidate.status === 'ready_to_underwrite').length,
    missingDocs: list.filter((candidate) => (candidate.missingItems || []).some((item) => ['om', 'rent_roll', 't12'].includes(item))).length,
  };
}

export function sortCandidates(candidates) {
  return [...(candidates || [])].sort((a, b) => {
    const statusDelta = (STATUS_RANK[a.status] ?? 99) - (STATUS_RANK[b.status] ?? 99);
    if (statusDelta !== 0) return statusDelta;
    const priorityDelta = (PRIORITY_RANK[a.priority] ?? 99) - (PRIORITY_RANK[b.priority] ?? 99);
    if (priorityDelta !== 0) return priorityDelta;
    const readinessDelta = (b.readinessScore || 0) - (a.readinessScore || 0);
    if (readinessDelta !== 0) return readinessDelta;
    return (b.assetClassConfidence || 0) - (a.assetClassConfidence || 0);
  });
}

export function filterCandidates(candidates, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return sortCandidates(candidates).filter((candidate) => {
    if (filters.sourceType && filters.sourceType !== 'all' && candidate.sourceType !== filters.sourceType) return false;
    if (filters.status && filters.status !== 'all' && candidate.status !== filters.status) return false;
    if (filters.minConfidence && candidate.assetClassConfidence < Number(filters.minConfidence)) return false;
    if (!query) return true;
    return [candidate.name, candidate.address, candidate.market, candidate.sourceName, candidate.facts?.broker]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
}

export function getDefaultCandidate(candidates) {
  return sortCandidates(candidates).find((candidate) => candidate.assetClass === 'self_storage') || candidates?.[0] || null;
}

export function formatCandidateLocation(candidate) {
  return candidate?.market || candidate?.address || 'Market not detected';
}

export function getDocumentStatus(candidate, type) {
  return candidate?.documents?.find((doc) => (doc.type || doc.doc_type) === type)?.status || 'missing';
}

export function getEffectiveMissingItems(candidate) {
  const missingItems = Array.isArray(candidate?.missingItems || candidate?.missing_items)
    ? (candidate.missingItems || candidate.missing_items)
    : [];
  const attachedTypes = new Set((candidate?.documents || [])
    .filter((doc) => doc.status !== 'detached')
    .map((doc) => doc.type || doc.doc_type)
    .filter((docType) => UNDERWRITING_DOCUMENT_TYPES.has(docType)));

  return missingItems.filter((item) => !attachedTypes.has(item));
}

export function isLibraryDocumentReady(doc) {
  if (!doc) return false;
  const status = doc.processingStatus || doc.processing_status || doc.status;
  const hasEmbeddings = doc.hasEmbeddings ?? doc.has_embeddings;
  const chunkCount = doc.chunkCount ?? doc.chunk_count;
  return status === 'completed' && (hasEmbeddings === true || Number(chunkCount || 0) > 0);
}

export function getCandidateConfidence(candidate) {
  if (!candidate) {
    return {
      label: 'Needs Review',
      tone: 'review',
      detail: 'Select a candidate to review source confidence.',
      percent: 0,
      reasons: ['No candidate selected.'],
    };
  }

  const assetClass = candidate.assetClass || candidate.asset_class;
  const percent = getAssetClassConfidencePercent(candidate);
  const evidence = Array.isArray(candidate.evidence) ? candidate.evidence : [];
  const facts = candidate.facts || {};
  const reasons = evidence.slice(0, 3).map((item) => item.detail || item.label).filter(Boolean);

  if (assetClass && assetClass !== 'self_storage' && assetClass !== 'unknown') {
    return {
      label: 'Not Relevant',
      tone: 'muted',
      detail: 'Source evidence does not currently classify this as self-storage.',
      percent,
      reasons: reasons.length ? reasons : ['Candidate is not classified as self-storage.'],
    };
  }

  if (assetClass === 'self_storage' && percent >= 85) {
    return {
      label: 'Strong Match',
      tone: 'strong',
      detail: 'Strong top-funnel match for a self-storage acquisition candidate.',
      percent,
      reasons: reasons.length ? reasons : ['Candidate is classified as self-storage with high confidence.'],
    };
  }

  if (assetClass === 'self_storage' && percent >= 70) {
    return {
      label: 'Likely Match',
      tone: 'likely',
      detail: 'Likely self-storage candidate; review source evidence before underwriting.',
      percent,
      reasons: reasons.length ? reasons : ['Candidate is classified as self-storage with moderate confidence.'],
    };
  }

  const fallbackReasons = [
    facts.address || candidate.address ? 'Address is available.' : null,
    facts.price ? 'Purchase price is available.' : null,
    facts.units ? 'Unit count is available.' : null,
  ].filter(Boolean);

  return {
    label: 'Needs Review',
    tone: 'review',
    detail: 'Source evidence is incomplete or confidence is uncertain.',
    percent,
    reasons: reasons.length ? reasons : fallbackReasons.length ? fallbackReasons : ['No source evidence captured yet.'],
  };
}

export function getUnderwritingReadiness(candidate, { isPrototype = false } = {}) {
  const blockers = getHandoffBlockers(candidate, { isPrototype });

  if (!candidate) {
    return {
      label: 'Needs Candidate',
      tone: 'muted',
      detail: 'Select a candidate before creating an underwriting run.',
      blockers,
      nextAction: 'Select a candidate.',
    };
  }

  if (isPrototype) {
    return {
      label: 'Sample Data',
      tone: 'muted',
      detail: 'This sample candidate previews the workflow. Create a real candidate to start underwriting.',
      blockers,
      nextAction: 'Create a real candidate.',
    };
  }

  if (candidate.underwritingRunId || candidate.underwriting_run_id) {
    return {
      label: 'In Underwriting',
      tone: 'ready',
      detail: 'This candidate already has an underwriting run.',
      blockers,
      nextAction: 'Open the existing underwriting run.',
    };
  }

  const assetClass = candidate.assetClass || candidate.asset_class;
  if (assetClass !== 'self_storage') {
    return {
      label: 'Needs Review',
      tone: 'warning',
      detail: 'Only self-storage candidates can move into this underwriting flow.',
      blockers,
      nextAction: 'Review the candidate classification.',
    };
  }

  if (needsCandidateConfidenceReview(candidate)) {
    return {
      label: 'Needs Review',
      tone: 'warning',
      detail: 'Self-storage classification confidence is below the threshold for full underwriting.',
      blockers,
      nextAction: 'Review the candidate classification.',
    };
  }

  const om = (candidate.documents || []).find((doc) => (doc.type || doc.doc_type) === 'om' && doc.status !== 'detached');
  if (!om) {
    return {
      label: 'Needs Indexed OM',
      tone: 'warning',
      detail: 'Attach an indexed OM from the Library before creating a full underwriting run.',
      blockers,
      nextAction: 'Attach an OM from the Library.',
    };
  }

  if (!isLibraryDocumentReady(om)) {
    return {
      label: 'OM Processing',
      tone: 'warning',
      detail: 'The attached OM is still processing in the Library.',
      blockers,
      nextAction: 'Wait for Library indexing to finish.',
    };
  }

  return {
    label: 'Ready for Underwriting',
    tone: 'ready',
    detail: 'Indexed OM is attached. Rent roll and T-12 can be added now or later.',
    blockers,
    nextAction: 'Create a full underwriting run.',
  };
}

export function getHandoffBlockers(candidate, { isPrototype = false } = {}) {
  if (!candidate) return ['Select a candidate first.'];
  if (isPrototype) return ['Create a real candidate before underwriting.'];
  const blockers = [];
  if ((candidate.assetClass || candidate.asset_class) !== 'self_storage') {
    blockers.push('Candidate is not self-storage.');
  }
  if (needsCandidateConfidenceReview(candidate)) {
    blockers.push('Review candidate confidence before underwriting.');
  }
  if (candidate.underwritingRunId || candidate.underwriting_run_id) {
    blockers.push('Candidate already has an underwriting run.');
  }
  const om = (candidate.documents || []).find((doc) => (doc.type || doc.doc_type) === 'om' && doc.status !== 'detached');
  if (!om) {
    blockers.push('Attach an indexed OM document before creating a run.');
  } else if (!isLibraryDocumentReady(om)) {
    blockers.push('OM is still processing in Library.');
  }
  return blockers;
}

export function getSuggestedLibraryDocuments(candidate, documents) {
  const list = Array.isArray(documents) ? documents : [];
  if (!candidate) return list;
  return [...list].sort((a, b) => {
    const aMatches = a.dealCandidateId === candidate.id ? 0 : 1;
    const bMatches = b.dealCandidateId === candidate.id ? 0 : 1;
    if (aMatches !== bMatches) return aMatches - bMatches;
    const aName = `${a.name || ''}`.toLowerCase();
    const bName = `${b.name || ''}`.toLowerCase();
    const candidateName = `${candidate.name || ''}`.toLowerCase();
    const aNameMatches = candidateName && aName.includes(candidateName.split(' ')[0]) ? 0 : 1;
    const bNameMatches = candidateName && bName.includes(candidateName.split(' ')[0]) ? 0 : 1;
    if (aNameMatches !== bNameMatches) return aNameMatches - bNameMatches;
    return aName.localeCompare(bName);
  });
}

export function filterLibraryDocuments(documents, filters = {}) {
  const query = (filters.query || '').trim().toLowerCase();
  return (documents || []).filter((doc) => {
    const docType = getLibraryDocumentType(doc);
    if (filters.type && filters.type !== 'all' && docType !== filters.type) return false;
    if (!query) return true;
    return [doc.name, docType, doc.fileType, doc.source]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
}

export function labelFromSnake(value) {
  if (!value) return 'Unknown';
  return String(value).split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}
