/**
 * Highlight Card - Elegant display for section highlights
 *
 * Uses existing tokenized classes: primary, success, warning, destructive, muted
 * Renders key facts with visual hierarchy and proper currency formatting
 */

import { TrendingUp, TrendingDown, Building2, DollarSign, Target, BarChart3, Award } from "lucide-react";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";
import { formatCurrency } from "../../utils/formatters";

const ICON_MAP = {
  company: Building2,
  metric: DollarSign,
  stat: Target,
};

export default function HighlightCard({ highlight, currency = "USD", richCitations = [], onCitationClick }) {
  if (!highlight) return null;

  const Icon = ICON_MAP[highlight.type] || Target;

  // Get rich citation data for the citation token
  const getRichCitation = (token) => {
    return richCitations.find(
      (rc) => rc.token === token || rc.id === token
    );
  };

  // Format the value based on type
  const formatValue = () => {
    // If already formatted, use that
    if (highlight.formatted) {
      return highlight.formatted;
    }

    // If numeric and type is metric, format as currency
    if (typeof highlight.value === "number" && highlight.type === "metric") {
      return formatCurrency(highlight.value, currency);
    }

    // Otherwise return as is
    return highlight.value;
  };

  // Get trend indicator
  const renderTrend = () => {
    if (!highlight.trend) return null;

    const isUp = highlight.trend === "up";
    const TrendIcon = isUp ? TrendingUp : TrendingDown;
    const trendClass = isUp
      ? "text-success"
      : "text-destructive";

    return (
      <div className={`flex items-center gap-1 ${trendClass}`}>
        <TrendIcon className="w-3 h-3" />
        {highlight.trend_value && (
          <span className="text-xs font-semibold">{highlight.trend_value}</span>
        )}
      </div>
    );
  };

  // Get status badge
  const renderStatus = () => {
    if (!highlight.status) return null;

    const statusConfig = {
      strong: { variant: "default", className: "bg-success text-success-foreground" },
      positive: { variant: "default", className: "bg-success text-success-foreground" },
      moderate: { variant: "default", className: "bg-warning text-foreground" },
      weak: { variant: "secondary", className: "" },
      negative: { variant: "destructive", className: "" },
      monitor: { variant: "default", className: "bg-warning text-foreground" },
    };

    const config = statusConfig[highlight.status] || statusConfig.moderate;

    return (
      <Badge variant={config.variant} className={`text-xs ${config.className}`}>
        {highlight.status}
      </Badge>
    );
  };

  return (
    <Card className="p-4 hover:shadow-md transition-shadow border-l-4 border-primary">
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div className="p-2 bg-primary/10 rounded-lg flex-shrink-0">
          <Icon className="w-4 h-4 text-primary" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Label */}
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-1">
            {highlight.label}
            {(highlight.year || highlight.period) && (
              <span className="ml-1 text-muted-foreground/60">
                ({highlight.year || highlight.period})
              </span>
            )}
          </div>

          {/* Value with trend/status */}
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <div className="text-lg font-bold text-foreground">
              {formatValue()}
            </div>
            {renderTrend()}
            {renderStatus()}
          </div>

          {/* Detail */}
          {highlight.detail && (
            <div className="text-sm text-muted-foreground">
              {highlight.detail}
            </div>
          )}

          {/* Citation */}
          {highlight.citation && (() => {
            const richCite = getRichCitation(highlight.citation);

            // Extract filename without extension and truncate if needed
            const getShortFilename = (filename) => {
              if (!filename || filename === "Unknown") return "Doc";
              const nameWithoutExt = filename.replace(/\.[^/.]+$/, ""); // Remove extension
              return nameWithoutExt.length > 20 ? nameWithoutExt.substring(0, 17) + "..." : nameWithoutExt;
            };

            const displayText = richCite
              ? `[${getShortFilename(richCite.document)}:p${richCite.page || '?'}]`
              : highlight.citation;

            // If we have rich citation data and click handler, make it clickable
            if (richCite && onCitationClick) {
              return (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onCitationClick(richCite);
                  }}
                  className="inline-flex items-center px-2 py-1 rounded text-xs font-mono font-semibold bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors cursor-pointer border border-blue-300 dark:border-blue-700 mt-2"
                  title={`Click to view: ${richCite.document || 'Document'} - Page ${richCite.page || '?'}`}
                >
                  {displayText}
                </button>
              );
            }

            // Fallback: non-clickable badge
            return (
              <Badge variant="outline" className="text-xs font-mono mt-2">
                {displayText}
              </Badge>
            );
          })()}
        </div>
      </div>
    </Card>
  );
}
