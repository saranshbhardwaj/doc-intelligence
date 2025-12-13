/**
 * Enhanced Opportunities Card - Production-quality opportunities display
 *
 * Features:
 * - Impact-based grouping and color coding
 * - Count summary banner
 * - Category organization
 * - Hover effects and smooth transitions
 * - Citation badges
 * - Visual indicators for growth potential
 */

import { Lightbulb, TrendingUp, Sparkles, Target } from "lucide-react";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

export default function OpportunitiesCard({ opportunities }) {
  if (!opportunities || opportunities.length === 0) return null;

  // Count by impact
  const counts = opportunities.reduce(
    (acc, opp) => {
      const impact = (opp.impact || "Medium").toLowerCase();
      if (impact === "high") acc.high++;
      else if (impact === "medium") acc.medium++;
      else acc.low++;
      return acc;
    },
    { high: 0, medium: 0, low: 0 }
  );

  // Group by category
  const byCategory = opportunities.reduce((acc, opp) => {
    const cat = opp.category || "Other";
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(opp);
    return acc;
  }, {});

  const getImpactColor = (impact) => {
    const i = (impact || "Medium").toLowerCase();
    if (i === "high") return {
      border: "border-success",
      bg: "bg-success/10",
      badge: "bg-success",
      text: "text-success"
    };
    if (i === "medium") return {
      border: "border-primary",
      bg: "bg-primary/10",
      badge: "bg-primary",
      text: "text-primary"
    };
    return {
      border: "border-muted",
      bg: "bg-muted",
      badge: "bg-muted",
      text: "text-muted-foreground"
    };
  };

  return (
    <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-success">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-success/5 to-success/10 dark:from-success/10 dark:to-success/20 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-success/10 rounded-lg">
            <Sparkles className="w-6 h-6 text-success" />
          </div>
          <h2 className="text-xl font-bold text-foreground">Growth Opportunities</h2>
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Summary Banner */}
        <div className="p-4 bg-success/10 border-l-4 border-success rounded-r-lg">
          <div className="flex items-start gap-3">
            <Target className="w-5 h-5 text-success mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <h3 className="font-bold text-success mb-1">
                {opportunities.length} Growth Opportunit{opportunities.length !== 1 ? "ies" : "y"} Identified
              </h3>
              <p className="text-sm text-muted-foreground mb-3">
                Strategic opportunities for value creation and competitive advantage.
              </p>
              <div className="flex gap-3 text-sm flex-wrap">
                {counts.high > 0 && (
                  <Badge className="bg-success text-success-foreground px-3 py-1">
                    {counts.high} High Impact
                  </Badge>
                )}
                {counts.medium > 0 && (
                  <Badge className="bg-primary text-primary-foreground px-3 py-1">
                    {counts.medium} Medium Impact
                  </Badge>
                )}
                {counts.low > 0 && (
                  <Badge variant="secondary" className="px-3 py-1">
                    {counts.low} Low Impact
                  </Badge>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Opportunities by Category */}
        {Object.entries(byCategory).map(([category, categoryOpps]) => (
          <div key={category}>
            <h4 className="text-sm font-bold text-muted-foreground uppercase mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4" />
              {category} Opportunities
            </h4>
            <div className="space-y-3">
              {categoryOpps.map((opp, index) => {
                const colors = getImpactColor(opp.impact);

                return (
                  <div
                    key={index}
                    className={`border-l-4 ${colors.border} ${colors.bg} p-4 rounded-r-lg shadow-sm hover:shadow-md transition-all duration-200 hover:translate-x-1`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-1">
                        {/* Header with impact badge */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <Badge className={`${colors.badge} text-white font-bold text-xs`}>
                            {opp.impact || "Medium"} Impact
                          </Badge>
                          {opp.category && (
                            <span className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded">
                              {opp.category}
                            </span>
                          )}
                        </div>

                        {/* Description */}
                        <p className="text-sm text-foreground mb-3 leading-relaxed">
                          {opp.description}
                        </p>

                        {/* Citations */}
                        {opp.citations && opp.citations.length > 0 && (
                          <div className="flex flex-wrap gap-2 mt-3">
                            {opp.citations.map((cite, cIdx) => (
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
