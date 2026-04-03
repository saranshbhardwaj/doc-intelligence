/**
 * Citation Badge Component
 * ChatGPT-inspired citation display with tokenized Tailwind classes
 *
 * Uses only tokens from tailwind.config.js:
 * - Colors: background, foreground, card, primary, secondary, muted, accent, border
 * - Animations: chip-fade-in, fade-in
 */

import React from 'react';
import { FileText } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Parse citation token to extract page number
 */
function parseCitationPage(citation) {
  if (!citation) return null;
  const text = String(citation);

  // Canonical format: [S1:p15] or legacy [D1:p15]
  let match = text.match(/\[(?:S|D)\d+:p(\d+)\]/i);

  // Table format from extraction output: [Table 7:p15]
  if (!match) {
    match = text.match(/\[Table\s*\d+\s*:\s*p(\d+)\]/i);
  }

  // Fallback: any bracketed token with :pN, e.g. [Source:p15]
  if (!match) {
    match = text.match(/\[[^\]]*:\s*p(\d+)\]/i);
  }

  const page = match && match[1] ? parseInt(match[1], 10) : null;
  return Number.isFinite(page) && page > 0 ? page : null;
}

/**
 * Build click payload for a citation badge.
 * Prefer bbox payload when available (more precise than citation token page).
 */
function buildCitationPayload(pageNumber, bbox) {
  if (!bbox || typeof bbox !== 'object') return pageNumber || null;

  const bboxPage = Number(bbox.page);
  if (Number.isFinite(bboxPage)) {
    return { ...bbox, page: bboxPage };
  }

  return pageNumber || null;
}

/**
 * Single citation badge - ChatGPT inspired
 */
export function CitationBadge({
  citation,
  onClick,
  className,
  sourceText = null,
  bbox = null  // Optional bbox for PDF highlighting: { page, x0, y0, x1, y1 }
}) {
  const pageNumber = parseCitationPage(citation);
  const payload = buildCitationPayload(pageNumber, bbox);
  const effectivePage = typeof payload === 'number' ? payload : Number(payload?.page);
  const displayText = Number.isFinite(effectivePage) ? `Page ${effectivePage}` : citation;

  const handleClick = (e) => {
    e.stopPropagation();
    if (onClick && payload) {
      onClick(payload);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={!onClick || !payload}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium",
        "bg-muted text-muted-foreground border border-border",
        "transition-all duration-200",
        "animate-chip-fade-in",
        onClick && payload && "hover:bg-accent hover:text-accent-foreground cursor-pointer",
        !onClick && "cursor-default",
        className
      )}
      title={sourceText ? `"${sourceText.substring(0, 100)}..."` : displayText}
    >
      <FileText className="h-3 w-3" />
      <span>{displayText}</span>
    </button>
  );
}

/**
 * Multiple citation badges
 */
export function CitationBadges({
  citations = [],
  onCitationClick,
  className,
  extractedData = {}
}) {
  if (!citations || citations.length === 0) return null;

  const citationArray = Array.isArray(citations) ? citations : [citations];
  // Extract bbox from field data if available
  const bbox = extractedData?.bbox || null;

  return (
    <div className={cn("flex items-center flex-wrap gap-1.5", className)}>
      {citationArray.map((citation, index) => (
        <CitationBadge
          key={`${citation}-${index}`}
          citation={citation}
          onClick={onCitationClick}
          sourceText={extractedData?.source_text}
          bbox={bbox}
        />
      ))}
    </div>
  );
}

/**
 * Citation section with label
 */
export function CitationSection({
  citations,
  onCitationClick,
  label = "Source",
  className,
  extractedData
}) {
  if (!citations || citations.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-2 mt-2 pt-2 border-t border-border", className)}>
      <span className="text-xs text-muted-foreground font-medium">{label}:</span>
      <CitationBadges
        citations={citations}
        onCitationClick={onCitationClick}
        extractedData={extractedData}
      />
    </div>
  );
}

export default CitationBadge;
