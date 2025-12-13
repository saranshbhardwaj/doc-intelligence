/**
 * Metric Pill - Compact metric display for quick scanning
 *
 * Uses existing tokenized classes for semantic colors
 */

import { Badge } from "../ui/badge";

export default function MetricPill({ metric }) {
  if (!metric) return null;

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
        {metric.citation && (
          <Badge variant="outline" className="text-[10px] font-mono px-1 py-0">
            {metric.citation}
          </Badge>
        )}
      </div>
    </div>
  );
}
