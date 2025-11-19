import { Lightbulb } from "lucide-react";

export default function OpportunitiesCard({ opportunities }) {
  if (!opportunities || opportunities.length === 0) return null;

  const getImpactColor = (impact) => {
    const i = (impact || "").toLowerCase();
    if (i === "high") return "bg-green-600 text-foreground";
    if (i === "medium") return "bg-primary text-foreground";
    return "bg-card0 text-foreground";
  };

  return (
    <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-green-500">
      <div className="flex items-center gap-3 mb-4">
        <Lightbulb className="w-6 h-6 text-green-600" />
        <h2 className="text-xl font-bold text-foreground">Opportunities</h2>
      </div>

      <div className="space-y-4">
        {opportunities.map((opp, idx) => (
          <div
            key={idx}
            className="p-4 bg-background dark:bg-gray-700 rounded-lg"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded ${getImpactColor(
                      opp.impact
                    )}`}
                  >
                    {opp.impact || "Medium"} Impact
                  </span>
                  {opp.category && (
                    <span className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground">
                      {opp.category}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground dark:text-gray-300">
                  {opp.description}
                </p>
              </div>
            </div>
            {opp.citations && opp.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {opp.citations.map((cite, cIdx) => (
                  <span
                    key={cIdx}
                    className="text-xs font-mono text-muted-foreground"
                  >
                    {cite}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
