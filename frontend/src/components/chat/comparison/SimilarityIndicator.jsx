/**
 * SimilarityIndicator Component
 *
 * Visual progress bar with color coding for semantic similarity using design tokens:
 * - similarity-high (≥80%): High Match
 * - similarity-mid (60-79%): Partial
 * - similarity-low (<60%): Low
 */

import { Badge } from "../../ui/badge";
import { Progress } from "../../ui/progress";

export default function SimilarityIndicator({ similarity = 0 }) {
  const percentage = Math.round(similarity * 100);

  const getConfig = () => {
    if (similarity >= 0.8) return {
      color: "bg-similarity-high",
      label: "High Match",
      textColor: "text-similarity-high"
    };
    if (similarity >= 0.6) return {
      color: "bg-similarity-mid",
      label: "Partial",
      textColor: "text-similarity-mid"
    };
    return {
      color: "bg-similarity-low",
      label: "Low",
      textColor: "text-similarity-low"
    };
  };

  const config = getConfig();

  return (
    <div className="flex items-center gap-3">
      <div className="w-20">
        <Progress
          value={percentage}
          className="h-1.5"
          indicatorClassName={config.color}
        />
        <span className={`text-[10px] ${config.textColor} font-medium tabular-nums`}>
          {percentage}%
        </span>
      </div>
      <Badge variant="outline" className={`text-[10px] ${config.textColor} border-current`}>
        {config.label}
      </Badge>
    </div>
  );
}
