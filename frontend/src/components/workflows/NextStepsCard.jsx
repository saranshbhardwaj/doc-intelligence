import { CheckSquare } from "lucide-react";

export default function NextStepsCard({ nextSteps }) {
  if (!nextSteps || nextSteps.length === 0) return null;

  // Sort by priority
  const sorted = [...nextSteps].sort(
    (a, b) => (a.priority || 99) - (b.priority || 99)
  );

  return (
    <div className="bg-card rounded-xl shadow-md p-6 border-l-4 border-indigo-500">
      <div className="flex items-center gap-3 mb-4">
        <CheckSquare className="w-6 h-6 text-indigo-600" />
        <h2 className="text-xl font-bold text-foreground">Next Steps</h2>
      </div>

      <div className="space-y-3">
        {sorted.map((step, idx) => (
          <div
            key={idx}
            className="flex items-start gap-4 p-4 bg-background dark:bg-gray-700 rounded-lg"
          >
            <div className="flex-shrink-0 w-8 h-8 bg-indigo-600 text-foreground rounded-full flex items-center justify-center font-bold text-sm">
              {step.priority || idx + 1}
            </div>
            <div className="flex-1">
              <p className="font-semibold text-foreground mb-1">
                {step.action}
              </p>
              <div className="flex items-center gap-3 text-sm text-muted-foreground dark:text-muted-foreground">
                <span>Owner: {step.owner || "N/A"}</span>
                {step.timeline_days && (
                  <span>Timeline: {step.timeline_days} days</span>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
