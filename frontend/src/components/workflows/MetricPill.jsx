/**
 * Metric Pill - Compact metric display for quick scanning
 *
 * Uses existing tokenized classes for semantic colors
 */

import { Badge } from "../ui/badge";

export default function MetricPill({ metric, richCitations = [], onCitationClick }) {
  if (!metric) return null;

  // Get rich citation data for the citation token
  const getRichCitation = (token) => {
    return richCitations.find(
      (rc) => rc.token === token || rc.id === token
    );
  };

  // Get status styling using existing tokens
  const getStatusClass = () => {
    if (!metric.status) return "";

    const statusMap = {
      strong: "bg-success/10 text-success border-success/20",
      positive: "bg-success/10 text-success border-success/20",
      moderate: "bg-warning/10 text-warning border-warning/20",
      negative: "bg-destructive/10 text-destructive border-destructive/20",
      monitor: "bg-warning/10 text-warning border-warning/20",
      weak: "bg-muted text-muted-foreground border-border",
    };

    return statusMap[metric.status] || "";
  };

  return (
    <div className={`px-3 py-2 rounded-lg border ${getStatusClass() || "bg-card border-border"}`}>
      {/* Label */}
      <div className="text-xs font-medium text-muted-foreground mb-1">
        {metric.label}
        {(metric.period || metric.year) && (
          <span className="ml-1 opacity-60">
            ({metric.period || metric.year})
          </span>
        )}
      </div>

      {/* Value */}
      <div className="flex items-baseline gap-2">
        <div className={`text-base font-bold ${metric.status ? "" : "text-foreground"}`}>
          {metric.value}
        </div>

        {/* Citation badge */}
        {metric.citation && (() => {
          const richCite = getRichCitation(metric.citation);

          // Extract filename without extension and truncate if needed
          const getShortFilename = (filename) => {
            if (!filename || filename === "Unknown") return "Doc";
            const nameWithoutExt = filename.replace(/\.[^/.]+$/, "");
            return nameWithoutExt.length > 20 ? nameWithoutExt.substring(0, 17) + "..." : nameWithoutExt;
          };

          const displayText = richCite
            ? `[${getShortFilename(richCite.document)}:p${richCite.page || '?'}]`
            : metric.citation;

          // If we have rich citation and click handler, make it clickable
          if (richCite && onCitationClick) {
            return (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onCitationClick(richCite);
                }}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors cursor-pointer border border-blue-300 dark:border-blue-700"
                title={`Click to view: ${richCite.document || 'Document'} - Page ${richCite.page || '?'}`}
              >
                {displayText}
              </button>
            );
          }

          // Fallback: non-clickable badge
          return (
            <Badge variant="outline" className="text-[10px] font-mono px-1 py-0">
              {displayText}
            </Badge>
          );
        })()}
      </div>
    </div>
  );
}
