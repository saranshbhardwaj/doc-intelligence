import React from 'react';
import { cn } from '@/lib/utils';
import { CitationBadges } from './CitationBadge';
import { tierForConfidence } from '../utils/sourceMapConfidence';

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
          {entry.citations?.length > 0 && (
            <CitationBadges
              citations={entry.citations}
              citationContext={citationContext}
              onCitationClick={onCitationClick}
              className="shrink-0"
            />
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

export default function SourceMapView({ omStructure, citationContext, onCitationClick }) {
  const effective = omStructure?.effective;
  const columnMap = effective?.column_map ?? {};
  const sectionPresence = effective?.section_presence ?? {};
  const detectedAt = omStructure?.detected_at;

  return (
    <div className="flex flex-col gap-3 p-3">
      {detectedAt && (
        <p className="text-[10px] text-muted-foreground px-1">
          Detected at {new Date(detectedAt).toLocaleString()}
        </p>
      )}
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
    </div>
  );
}
