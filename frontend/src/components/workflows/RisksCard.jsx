import { AlertTriangle } from "lucide-react";

export default function RisksCard({ risks }) {
  if (!risks || risks.length === 0) return null;

  const getSeverityColor = (severity) => {
    const s = (severity || "").toLowerCase();
    if (s === "critical") return "bg-red-600 text-foreground";
    if (s === "high") return "bg-orange-500 text-foreground";
    if (s === "medium") return "bg-yellow-500 text-foreground";
    return "bg-primary text-foreground";
  };

  return (
    <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-orange-500">
      <div className="flex items-center gap-3 mb-4">
        <AlertTriangle className="w-6 h-6 text-orange-600" />
        <h2 className="text-xl font-bold text-foreground">Key Risks</h2>
      </div>

      <div className="space-y-4">
        {risks.map((risk, idx) => (
          <div
            key={idx}
            className="p-4 bg-background dark:bg-gray-700 rounded-lg"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded ${getSeverityColor(
                      risk.severity
                    )}`}
                  >
                    {risk.severity || "Medium"}
                  </span>
                  {risk.category && (
                    <span className="text-xs font-semibold text-muted-foreground dark:text-muted-foreground">
                      {risk.category}
                    </span>
                  )}
                </div>
                <p className="text-muted-foreground dark:text-gray-300">
                  {risk.description}
                </p>
              </div>
            </div>
            {risk.citations && risk.citations.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {risk.citations.map((cite, cIdx) => (
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
