/**
 * Enhanced Risks Card - Production-quality risk display
 *
 * Features:
 * - Severity-based grouping and color coding
 * - Count summary banner
 * - Category organization
 * - Hover effects and smooth transitions
 * - Citation badges
 * - Auto-detected indicator
 */

import { AlertTriangle, ShieldAlert, AlertCircle, TrendingDown } from "lucide-react";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

export default function RisksCard({ risks }) {
  if (!risks || risks.length === 0) return null;

  // Count by severity
  const counts = risks.reduce(
    (acc, risk) => {
      const severity = (risk.severity || "Medium").toLowerCase();
      if (severity === "critical" || severity === "high") acc.high++;
      else if (severity === "medium") acc.medium++;
      else acc.low++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );

  // Group by category
  const byCategory = risks.reduce((acc, risk) => {
    const cat = risk.category || "Other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(risk);
    return acc;
  }, {});

  const getSeverityColor = (severity) => {
    const s = (severity || "Medium").toLowerCase();
    if (s === "critical" || s === "high") return {
      border: "border-destructive",
      bg: "bg-destructive/10",
      badge: "bg-destructive",
      text: "text-destructive"
    };
    if (s === "medium") return {
      border: "border-warning",
      bg: "bg-warning/10",
      badge: "bg-warning",
      text: "text-warning"
    };
    return {
      border: "border-primary",
      bg: "bg-primary/10",
      badge: "bg-primary",
      text: "text-primary"
    };
  };

  return (
    <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-destructive">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-destructive/5 to-destructive/10 dark:from-destructive/10 dark:to-destructive/20 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-destructive/10 rounded-lg">
            <ShieldAlert className="w-6 h-6 text-destructive" />
          </div>
          <h2 className="text-xl font-bold text-foreground">Key Risks</h2>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Summary Banner */}
        <div className="p-4 bg-destructive/10 dark:bg-destructive/20 border-l-4 border-destructive rounded-r-lg">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-destructive mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="font-bold text-destructive mb-1">
                {risks.length} Risk{risks.length !== 1 ? "s" : ""} Identified
              </h3>
              <p className="text-sm text-muted-foreground mb-3">
                Comprehensive risk assessment from document analysis and financial metrics.
              </p>
              <div className="flex gap-3 text-sm flex-wrap">
                {counts.high > 0 && (
                  <Badge variant="destructive" className="px-3 py-1">
                    {counts.high} High/Critical
                  </Badge>
                )}
                {counts.medium > 0 && (
                  <Badge className="bg-warning text-warning-foreground px-3 py-1">
                    {counts.medium} Medium
                  </Badge>
                )}
                {counts.low > 0 && (
                  <Badge variant="secondary" className="px-3 py-1">
                    {counts.low} Low
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Risks by Category */}
        {Object.entries(byCategory).map(([category, categoryRisks]) => (
          <div key={category}>
            <h4 className="text-sm font-bold text-muted-foreground uppercase mb-3 flex items-center gap-2">
              <TrendingDown className="w-4 h-4" />
              {category} Risks
            </h4>
            <div className="space-y-3">
              {categoryRisks.map((risk, index) => {
                const colors = getSeverityColor(risk.severity);

                return (
                  <div
                    key={index}
                    className={`border-l-4 ${colors.border} ${colors.bg} p-4 rounded-r-lg shadow-sm hover:shadow-md transition-all duration-200 hover:translate-x-1`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1">
                        {/* Header with severity badge */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <Badge className={`${colors.badge} text-white font-bold text-xs`}>
                            {risk.severity || "Medium"}
                          </Badge>
                          {risk.category && (
                            <span className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded">
                              {risk.category}
                            </span>
                          )}
                        </div>

                        {/* Description */}
                        <p className="text-sm text-foreground mb-3 leading-relaxed">
                          {risk.description}
                        </p>

                        {/* Citations */}
                        {risk.citations && risk.citations.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-3">
                            {risk.citations.map((cite, cIdx) => (
                              <Badge
                                key={cIdx}
                                variant="outline"
                                className="text-xs font-mono"
                              >
                                {cite}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}
