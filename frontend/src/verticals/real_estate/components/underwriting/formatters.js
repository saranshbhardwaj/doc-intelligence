export const DOC_TYPE_LABELS = {
  om: 'Offering Memo',
  rent_roll: 'Rent Roll',
  t12: 'T-12',
};

export function formatCurrency(value) {
  if (value == null) return '—';
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

export function formatCurrencyPrecise(value) {
  if (value == null) return '—';
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPercent(value) {
  if (value == null) return '—';
  return `${(value > 1 ? value : value * 100).toFixed(1)}%`;
}

export function formatRatioPercent(value) {
  if (value == null) return '—';
  return `${(value * 100).toFixed(0)}%`;
}

export function formatMultiple(value) {
  if (value == null) return '—';
  return `${value.toFixed(2)}×`;
}

export function formatCompactCurrency(value) {
  if (value == null) return '—';
  if (Math.abs(value) >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

export function formatEvidenceValue(formatter, value) {
  return value == null ? '—' : formatter(value);
}

export function pickUnitMix(artifact, persistedInputs) {
  const candidates = [
    artifact.rent_roll_data?.unit_mix,
    artifact.unit_mix,
    persistedInputs.unit_mix,
    artifact.om_data?.unit_mix,
  ];
  for (const candidate of candidates) {
    if (Array.isArray(candidate) && candidate.length > 0) return candidate;
  }
  return [];
}

function normalizeSizeLabel(value) {
  if (!value) return '';
  return String(value)
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/[×]/g, 'x')
    .replace(/ft|feet|sq\.?/g, '')
    .replace(/[^0-9x]/g, '');
}

function normalizeClimateLabel(value) {
  const raw = String(value || '').toLowerCase();
  if (raw === 'cc' || raw.includes('climate')) return 'cc';
  if (raw === 'nc' || raw.includes('non')) return 'nc';
  return 'unknown';
}

function isParkingOrOtherRow(row) {
  const label = `${row?.unit_category || ''}`.toLowerCase();
  return ['parking', 'residential', 'apartment', 'office', 'commercial'].some((kw) => label.includes(kw));
}

function isStorageRow(row) {
  if (!row) return false;
  if (['parking', 'residential', 'office', 'other'].includes(row.unit_category)) return false;
  return !isParkingOrOtherRow(row);
}

function isClimateRow(row) {
  if (!row || !isStorageRow(row)) return false;
  if (row.climate_type === 'CC') return true;
  if (row.climate_type === 'NC') return false;
  return false;
}

function hasRows(rows) {
  return Array.isArray(rows) && rows.length > 0;
}

export function getRevenueBasis(artifact = {}, persistedInputs = {}, sourceCitations = {}) {
  if (artifact.expense_basis?.source === 'om_noi') {
    return {
      label: 'OM-stated NOI quick screen',
      tone: 'warning',
      source: 'om_noi',
      detail: 'Returns are driven by OM-stated NOI. Upload a T-12 to verify actual revenue and expenses.',
    };
  }

  const months = persistedInputs.operational?.income_basis_months
    ?? artifact.income_basis_months
    ?? artifact.om_data?.income_basis_months
    ?? artifact.t12_data?.summary?.period_months
    ?? null;
  const note = persistedInputs.operational?.income_basis_note
    ?? artifact.income_basis_note
    ?? artifact.om_data?.income_basis_note
    ?? null;

  if (months != null) {
    const isAnnualized = months < 12;
    return {
      label: isAnnualized ? `T-${months} annualized` : 'T-12 actuals',
      tone: isAnnualized ? 'warning' : 'success',
      source: isAnnualized ? 'annualized_income' : 't12',
      detail: note || (isAnnualized
        ? `Revenue is based on ${months} months of income and annualized for underwriting.`
        : 'Revenue is based on a trailing 12-month operating statement.'),
    };
  }

  if (
    artifact.rent_roll_data?.summary?.avg_in_place_rent_per_unit_monthly != null
    || sourceCitations.avg_in_place_rent_per_unit_monthly?.doc_type === 'rent_roll'
  ) {
    return {
      label: 'Rent roll',
      tone: 'success',
      source: 'rent_roll',
      detail: 'Revenue support includes rent-roll-level in-place rent evidence.',
    };
  }

  if (
    artifact.om_data?.gpr_annual_projected != null
    || artifact.om_data?.gross_potential_rent_annual != null
    || sourceCitations.gross_potential_rent_annual?.doc_type === 'om'
  ) {
    return {
      label: 'Offering memo',
      tone: 'warning',
      source: 'om',
      detail: 'Revenue comes from broker or OM-stated assumptions. Validate against T-12 and rent roll before relying on it.',
    };
  }

  if (persistedInputs.operational?.gross_potential_rent_annual != null) {
    return {
      label: 'Manual / saved input',
      tone: 'active',
      source: 'manual',
      detail: 'Revenue is coming from the saved underwriting input set rather than a cited source basis.',
    };
  }

  return {
    label: 'Missing',
    tone: 'danger',
    source: 'missing',
    detail: 'No clear revenue source basis was found. Treat returns as incomplete until revenue support is added.',
  };
}

export function getUnitMixSource(artifact = {}, persistedInputs = {}, coverage = null) {
  if (hasRows(artifact.rent_roll_data?.unit_mix)) {
    return {
      label: 'Rent roll',
      tone: 'success',
      source: 'rent_roll',
      detail: 'Unit mix is sourced from rent roll rows.',
    };
  }
  if (coverage?.isPartial) {
    return {
      label: 'Partial OM unit schedule',
      tone: 'warning',
      source: 'om_partial',
      detail: `${coverage.extractedUnits} of ${coverage.propertyUnits} property units are represented in extracted OM unit rows.`,
    };
  }
  if (hasRows(artifact.unit_mix)) {
    return {
      label: 'Extracted OM unit mix',
      tone: 'active',
      source: 'extracted',
      detail: 'Unit mix was extracted from OM/unit schedule data. Validate against the rent roll when available.',
    };
  }
  if (hasRows(persistedInputs.unit_mix)) {
    return {
      label: 'Manual / saved input',
      tone: 'active',
      source: 'manual',
      detail: 'Unit mix comes from saved underwriting inputs.',
    };
  }
  if (hasRows(artifact.om_data?.unit_mix)) {
    return {
      label: 'Offering memo',
      tone: 'warning',
      source: 'om',
      detail: 'Unit mix is OM-supported. Validate against the rent roll when possible.',
    };
  }
  return {
    label: 'Missing',
    tone: 'danger',
    source: 'missing',
    detail: 'No unit mix is available. Per-door, occupancy, and rent-position reads need manual review.',
  };
}

export function getUnitMixSummary(unitMix = []) {
  const rows = Array.isArray(unitMix) ? unitMix : [];
  const storageRows = rows.filter(isStorageRow);
  const climateRows = storageRows.filter(isClimateRow);
  const nonClimateRows = storageRows.filter((row) => !isClimateRow(row));
  const parkingOtherRows = rows.filter((row) => !isStorageRow(row));

  const sumUnits = (items) => items.reduce((sum, row) => sum + (Number(row?.num_units) || 0), 0);
  const rowsWithOccupancy = rows.filter((row) => row?.occupancy_pct != null || row?.occupied_units != null).length;
  const totalUnits = sumUnits(rows);

  return {
    totalRows: rows.length,
    totalUnits,
    climateUnits: sumUnits(climateRows),
    nonClimateUnits: sumUnits(nonClimateRows),
    parkingOtherUnits: sumUnits(parkingOtherRows),
    rowsWithOccupancy,
    hasOccupancy: rowsWithOccupancy > 0,
  };
}

export function getRentCompCoverage(unitMix = [], rentComps = [], rentPositionAnalysis = []) {
  const storageRows = (Array.isArray(unitMix) ? unitMix : [])
    .filter((row) => isStorageRow(row) && normalizeSizeLabel(row?.size));
  const positionRows = Array.isArray(rentPositionAnalysis) ? rentPositionAnalysis : [];
  const compRows = Array.isArray(rentComps) ? rentComps : [];

  const isSizeOnly = positionRows.length > 0
    && positionRows.every(r => r.match_basis === 'size_only' || r.climate_type === 'Mixed');

  // Zero-comp rows are emitted so the UI can show coverage gaps — exclude them from matched counts.
  const matchedPositionRows = positionRows.filter(
    r => (r.comp_count ?? 0) > 0 && r.comp_average_rent != null
  );

  // Mirror backend _size_bucket thresholds for bucket-level coverage in size-only mode.
  const getSizeBucket = (sqft) => {
    if (!sqft || sqft <= 0) return null;
    if (sqft < 25)  return 'locker';
    if (sqft < 75)  return 'small';
    if (sqft < 150) return 'medium';
    if (sqft < 300) return 'large';
    return 'xlarge';
  };

  const subjectSizeMap = new Map();
  storageRows.forEach((row) => {
    const sizeKey = normalizeSizeLabel(row.size);
    const climateKey = normalizeClimateLabel(row.climate_type || '');
    const key = climateKey === 'unknown' ? sizeKey : `${sizeKey}-${climateKey}`;
    if (!subjectSizeMap.has(key)) {
      subjectSizeMap.set(key, {
        label: row.size || 'Unknown size',
        sizeKey,
        climateKey,
        bucket: getSizeBucket(row.standard_sqft),
      });
    }
  });
  const subjectSizes = [...subjectSizeMap.values()];

  // In size-only mode the backend collapses multiple subject sizes into one bucket row.
  // Count and report coverage at bucket granularity so 10x10 and 5x10 in the same
  // bucket don't each count as separate "unmatched" sizes.
  const effectiveSubjectSizes = isSizeOnly
    ? [...new Map(subjectSizes.filter(s => s.bucket).map(s => [s.bucket, s])).values()]
    : subjectSizes;
  const totalBuckets = effectiveSubjectSizes.length || subjectSizes.length;

  const matchedKeys = new Set(matchedPositionRows.map((row) => {
    const sizeKey = normalizeSizeLabel(row?.size);
    const climateKey = normalizeClimateLabel(row?.climate_type);
    return climateKey === 'unknown' ? sizeKey : `${sizeKey}-${climateKey}`;
  }));
  const matchedSizes = new Set(matchedPositionRows.map((row) => normalizeSizeLabel(row?.size)).filter(Boolean));
  const matchedBucketSet = new Set(matchedPositionRows.map((row) => row?.bucket).filter(Boolean));
  const compSizes = new Set(compRows.map((row) => normalizeSizeLabel(row?.size)).filter(Boolean));

  const unmatchedLabels = effectiveSubjectSizes
    .filter((subjectSize) => {
      if (isSizeOnly) {
        return !matchedBucketSet.has(subjectSize.bucket);
      }
      const keyedMatch = matchedKeys.has(`${subjectSize.sizeKey}-${subjectSize.climateKey}`);
      return !(keyedMatch || matchedSizes.has(subjectSize.sizeKey) || compSizes.has(subjectSize.sizeKey));
    })
    .map((subjectSize) => subjectSize.label);

  const matchedBuckets = totalBuckets > 0 ? totalBuckets - unmatchedLabels.length : matchedPositionRows.length;
  const unmatchedCount = Math.max(totalBuckets - matchedBuckets, 0);
  const hasUnmatchedBuckets = positionRows.some(r => r.comp_count === 0 || r.comp_average_rent == null);
  const tone = totalBuckets === 0 ? 'neutral'
    : matchedBuckets === 0 ? 'danger'
    : (unmatchedCount > 0 || (isSizeOnly && hasUnmatchedBuckets)) ? 'warning'
    : 'success';

  return {
    totalBuckets,
    matchedBuckets,
    unmatchedCount,
    unmatchedLabels: [...new Set(unmatchedLabels)].slice(0, 6),
    compRows: compRows.length,
    tone,
    label: totalBuckets > 0 ? `${matchedBuckets}/${totalBuckets} subject sizes matched` : `${compRows.length} comp rows`,
    detail: totalBuckets > 0
      ? (isSizeOnly
          ? 'Comps matched by unit size only — climate type not classified. Ratios are directional; verify against classified comps when available.'
          : 'Subject storage sizes are matched to same-size comp rows when available; unmatched sizes should be reviewed manually.')
      : 'Add subject unit mix to measure rent-position coverage against the comp set.',
  };
}

export function buildDerivedMixedRevenueWarning(unitMix) {
  if (!Array.isArray(unitMix) || unitMix.length === 0) return null;

  const nonStorageRows = unitMix.filter((row) => !isStorageRow(row));
  if (nonStorageRows.length === 0) return null;

  const nonStorageUnits = nonStorageRows.reduce((s, r) => s + (r?.num_units || 0), 0);
  const totalUnits = unitMix.reduce((s, r) => s + (r?.num_units || 0), 0);
  const rowRent = (row) => {
    const units = Number(row?.num_units) || 0;
    const rent = Number(row?.current_rent ?? row?.market_rent) || 0;
    return units > 0 && rent > 0 ? units * rent * 12 : 0;
  };
  const nonStorageRent = nonStorageRows.reduce((s, r) => s + rowRent(r), 0);
  const totalRent = unitMix.reduce((s, r) => s + rowRent(r), 0);
  const unitShare = totalUnits > 0 ? nonStorageUnits / totalUnits : null;
  const rentShare = totalRent > 0 ? nonStorageRent / totalRent : null;
  const isMaterial = (unitShare != null && unitShare >= 0.20) || (rentShare != null && rentShare >= 0.15);
  const detail = nonStorageUnits > 0 && totalUnits > 0
    ? `${nonStorageUnits} of ${totalUnits} units/spaces (${(unitShare * 100).toFixed(0)}%) appear to be parking or residential`
    : 'parking or residential rows appear in the extracted unit mix';
  const rentDetail = rentShare != null ? `, representing approximately ${(rentShare * 100).toFixed(0)}% of unit-mix scheduled rent` : '';
  const materialDetail = isMaterial ? ' This is a material non-storage exposure.' : '';

  return {
    key: isMaterial ? 'mixed_revenue_material' : 'mixed_revenue_unit_mix',
    message: `Mixed revenue detected: ${detail}${rentDetail}.${materialDetail} The current underwriting model still applies blended self-storage assumptions, so per-door metrics and growth interpretations should be reviewed manually.`,
  };
}

export function parseCitationPage(citationToken) {
  if (!citationToken) return null;
  const match = String(citationToken).match(/:p(\d+)\]/i);
  if (!match) return null;
  const page = Number.parseInt(match[1], 10);
  return Number.isFinite(page) && page > 0 ? page : null;
}

export function normalizeCitation(fieldCitation, citationContext, citationToken) {
  if (!citationToken) return null;
  const contextEntry = citationContext?.[citationToken] || null;
  return {
    ...fieldCitation,
    citation: citationToken,
    page: contextEntry?.page ?? parseCitationPage(citationToken),
    document_id: contextEntry?.document_id ?? fieldCitation?.document_id,
    filename: contextEntry?.filename ?? fieldCitation?.filename,
    bbox: contextEntry?.bbox ?? fieldCitation?.bbox ?? null,
    source_kind: contextEntry?.source_kind ?? fieldCitation?.source_kind,
    sheet_name: contextEntry?.sheet_name ?? fieldCitation?.sheet_name,
    row_start: contextEntry?.row_start ?? fieldCitation?.row_start,
    row_end: contextEntry?.row_end ?? fieldCitation?.row_end,
    source_text: contextEntry?.source_text ?? fieldCitation?.source_text,
  };
}

export function getFieldCitation(fieldCitations, citationContext, fieldKey) {
  if (!fieldCitations) return null;
  const rawCitation = fieldCitations[fieldKey]
    ?? fieldCitations[`om.${fieldKey}`]
    ?? fieldCitations[`t12.${fieldKey}`]
    ?? fieldCitations[`rent_roll.${fieldKey}`]
    ?? null;

  if (!rawCitation || rawCitation.is_default) return null;

  if (rawCitation.is_derived) {
    return {
      doc_type: 'derived',
      is_derived: true,
      formula: rawCitation.formula ?? null,
      entries: [],
    };
  }

  return {
    ...rawCitation,
    entries: (rawCitation.citations || [])
      .map((token) => normalizeCitation(rawCitation, citationContext, token))
      .filter(Boolean),
  };
}

export function flattenCitationEntries(citations) {
  const uniqueEntries = new Map();
  (citations || []).filter(Boolean).forEach((citation) => {
    const docTypeLabel = DOC_TYPE_LABELS[citation.doc_type] || citation.doc_type || 'Document';
    (citation.entries || []).forEach((entry, index) => {
      const id = `${citation.doc_type || 'document'}-${entry.citation || entry.page || index}`;
      if (!uniqueEntries.has(id)) {
        uniqueEntries.set(id, {
          id,
          label: entry.source_kind === 'spreadsheet' && entry.sheet_name
            ? `${docTypeLabel} ${entry.sheet_name}${entry.row_start ? ` rows ${entry.row_start}-${entry.row_end}` : ''}`
            : entry.page ? `${docTypeLabel} p${entry.page}` : `Open ${docTypeLabel}`,
          title: citation.source_text || entry.filename || docTypeLabel,
          entry,
        });
      }
    });
  });
  return [...uniqueEntries.values()];
}
