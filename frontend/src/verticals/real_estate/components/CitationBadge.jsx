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
  const match = citation.match(/\[D\d+:p(\d+)\]/);
  return match && match[1] ? parseInt(match[1], 10) : null;
}

/**
 * Single citation badge - ChatGPT inspired
 */
export function CitationBadge({
  citation,
  onClick,
  className,
  sourceText = null
}) {
  const pageNumber = parseCitationPage(citation);
  const displayText = pageNumber ? `Page ${pageNumber}` : citation;

  const handleClick = (e) => {
    e.stopPropagation();
    if (onClick && pageNumber) {
      onClick(pageNumber);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={!onClick || !pageNumber}
      className={cn(
        "inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium",
        "bg-muted text-muted-foreground border border-border",
        "transition-all duration-200",
        "animate-chip-fade-in",
        onClick && pageNumber && "hover:bg-accent hover:text-accent-foreground cursor-pointer",
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

  return (
    <div className={cn("flex items-center flex-wrap gap-1.5", className)}>
      {citationArray.map((citation, index) => (
        <CitationBadge
          key={`${citation}-${index}`}
          citation={citation}
          onClick={onCitationClick}
          sourceText={extractedData?.source_text}
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
