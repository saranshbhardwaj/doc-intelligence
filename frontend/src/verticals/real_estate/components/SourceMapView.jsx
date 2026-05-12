import React, { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CitationBadge } from './CitationBadge';
import { tierForConfidence } from '../utils/sourceMapConfidence';
import { groupSourceMapCitationsByPage } from '../utils/sourceMapCitations';

// Canonical display order and friendly names for each group.
const COLUMN_MAP_KEYS = [
  { key: 'current',    label: 'Current / In-Place' },
  { key: 't12',        label: 'Trailing 12 Months (T12)' },
  { key: 'year1',      label: 'Year 1' },
  { key: 'pro_forma',  label: 'Pro Forma' },
  { key: 'stabilized', label: 'Stabilized' },
];

const SECTION_PRESENCE_KEYS = [
  { key: 'current_operating_statement_present',   label: 'Current Operating Statement' },
  { key: 'year1_operating_statement_present',     label: 'Year 1 Operating Statement' },
  { key: 'pro_forma_operating_statement_present', label: 'Pro Forma Operating Statement' },
  { key: 't12_present',                           label: 'T12 Operating Statement' },
  { key: 'unit_mix_present',                      label: 'Unit Mix' },
  { key: 'rent_roll_present',                     label: 'Rent Roll' },
  { key: 'rent_comps_present',                    label: 'Rent Comps' },
  { key: 'market_summary_present',                label: 'Market Summary' },
];

function ConfidenceDot({ tier }) {
  if (tier === 'unknown') return null;
  return (
    <span
      className={cn(
        'inline-block h-2 w-2 rounded-full shrink-0',
        tier === 'high' && 'bg-success',
        tier === 'mid'  && 'bg-warning',
        tier === 'low'  && 'bg-destructive',
      )}
    />
  );
}

function StructureRow({ friendlyLabel, entry, citationContext, onCitationClick }) {
  const detected = entry?.present === true;
  const tier = detected ? tierForConfidence(entry?.confidence) : 'unknown';
  const pct = entry?.confidence != null ? Math.round(entry.confidence * 100) : null;
  const groupedCitations = groupSourceMapCitationsByPage(entry?.citations ?? []);

  return (
    <div className="flex items-start gap-3 py-2 px-3 rounded-md hover:bg-muted/40 transition-colors">
      <div className="flex items-center gap-2 w-48 shrink-0 pt-0.5">
        <ConfidenceDot tier={tier} />
        <span className={cn(
          'text-xs font-medium leading-snug',
          detected ? 'text-foreground' : 'text-muted-foreground',
        )}>
          {friendlyLabel}
        </span>
      </div>

      {detected ? (
        <>
          <span className="text-xs text-muted-foreground italic truncate flex-1 pt-0.5">
            {entry.label || '—'}
          </span>
          <span className={cn(
            'text-xs tabular-nums shrink-0 pt-0.5 w-10 text-right',
            tier === 'high' && 'text-success',
            tier === 'mid'  && 'text-warning',
            tier === 'low'  && 'text-destructive',
          )}>
            {pct != null ? `${pct}%` : ''}
          </span>
          {groupedCitations.length > 0 && (
            <div className="flex items-center flex-wrap gap-1.5 shrink-0">
              {groupedCitations.map((group) => {
                const primaryCitation = group.primaryCitation;
                const sourceIndexMatch = String(primaryCitation).match(/\[(?:S|D)(\d+):/i);
                const sourceIndex = sourceIndexMatch?.[1] ? Number.parseInt(sourceIndexMatch[1], 10) : null;
                const bbox = sourceIndex != null
                  ? citationContext?.citations?.find((citation) => citation.source_index === sourceIndex)?.bbox ?? null
                  : null;

                return (
                  <CitationBadge
                    key={`${group.label}-${primaryCitation}`}
                    citation={primaryCitation}
                    label={group.label}
                    onClick={onCitationClick}
                    bbox={bbox}
                  />
                );
              })}
            </div>
          )}
        </>
      ) : (
        <span className="text-xs text-muted-foreground/50 italic pt-0.5">not detected</span>
      )}
    </div>
  );
}

function SectionGroup({ title, keys, data, citationContext, onCitationClick }) {
  const detectedCount = keys.filter(({ key }) => data?.[key]?.present === true).length;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2 bg-muted/50 border-b border-border">
        <span className="text-xs font-semibold text-foreground tracking-[0.08px]">{title}</span>
        <span className="text-[10px] text-muted-foreground tabular-nums">
          {detectedCount} / {keys.length} detected
        </span>
      </div>
      <div className="divide-y divide-border/50">
        {keys.map(({ key, label }) => (
          <StructureRow
            key={key}
            friendlyLabel={label}
            entry={data?.[key]}
            citationContext={citationContext}
            onCitationClick={onCitationClick}
          />
        ))}
      </div>
    </div>
  );
}

const SKIP_REASON_LABELS = {
  missing_section: 'Section not present in this OM',
  structure_key_missing: 'Structure key not detected',
  low_structure_confidence: 'Low structure confidence',
};

function formatFieldId(id) {
  if (!id) return '?';
  // Strip common prefixes (e.g. "rediq_", "napkin_", "actuals_")
  const stripped = id.replace(/^(rediq|napkin|actuals|proforma|market)_/, '');
  // Convert snake_case to Title Case words
  return stripped
    .split('_')
    .map(w => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function SkippedSection({ skippedCells }) {
  const [open, setOpen] = useState(false);
  if (!skippedCells?.length) return null;

  const byReason = {};
  for (const cell of skippedCells) {
    const reason = cell.skip_reason || 'unknown';
    if (!byReason[reason]) byReason[reason] = [];
    const label = cell.excel_sheet
      ? `${formatFieldId(cell.target_id)} (${cell.excel_sheet} ${cell.excel_cell || ''})`
      : formatFieldId(cell.target_id);
    byReason[reason].push(label);
  }

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center justify-between w-full px-3 py-2 bg-muted/50 border-b border-border hover:bg-muted/70 transition-colors"
      >
        <span className="text-xs font-semibold text-foreground tracking-[0.08px]">
          Skipped Fields
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground tabular-nums">
            {skippedCells.length} skipped — section absent or undetected
          </span>
          {open
            ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
            : <ChevronRight className="h-3 w-3 text-muted-foreground" />
          }
        </div>
      </button>
      {open && (
        <div className="divide-y divide-border/50 px-3 py-2 flex flex-col gap-2">
          {Object.entries(byReason).map(([reason, ids]) => (
            <div key={reason}>
              <p className="text-[10px] font-medium text-muted-foreground mb-1">
                {SKIP_REASON_LABELS[reason] || reason}
              </p>
              <p className="text-[10px] text-muted-foreground/70">
                {ids.slice(0, 6).join(', ')}{ids.length > 6 ? ` +${ids.length - 6} more` : ''}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function SourceMapView({ omStructure, cellStatus, citationContext, onCitationClick }) {
  const effective = omStructure?.effective;
  const columnMap = effective?.column_map ?? {};
  const sectionPresence = effective?.section_presence ?? {};
  const detectedAt = omStructure?.detected_at;

  const allKeys = [...COLUMN_MAP_KEYS, ...SECTION_PRESENCE_KEYS];
  const allData = { ...columnMap, ...sectionPresence };
  const detectedCount = allKeys.filter(({ key }) => allData[key]?.present === true).length;
  const absentKeys = allKeys
    .filter(({ key }) => allData[key] && allData[key].present === false)
    .map(({ label }) => label);

  const skippedCells = cellStatus?.skipped_cells;

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="px-1 flex flex-col gap-0.5">
        <p className="text-xs text-foreground font-medium">
          Detected {detectedCount} of {allKeys.length} structural keys
        </p>
        {absentKeys.length > 0 && (
          <p className="text-[10px] text-muted-foreground">
            Not present in this OM: {absentKeys.slice(0, 4).join(', ')}
            {absentKeys.length > 4 ? ` +${absentKeys.length - 4} more` : ''}
          </p>
        )}
        {detectedAt && (
          <p className="text-[10px] text-muted-foreground/60">
            Detected at {new Date(detectedAt).toLocaleString()}
          </p>
        )}
      </div>
      <SectionGroup
        title="Operating Statement Columns"
        keys={COLUMN_MAP_KEYS}
        data={columnMap}
        citationContext={citationContext}
        onCitationClick={onCitationClick}
      />
      <SectionGroup
        title="Document Sections"
        keys={SECTION_PRESENCE_KEYS}
        data={sectionPresence}
        citationContext={citationContext}
        onCitationClick={onCitationClick}
      />
      <SkippedSection skippedCells={skippedCells} />
    </div>
  );
}
