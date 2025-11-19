import { Card } from "../ui/card";
import { Badge } from "../ui/badge";
import { Progress } from "../ui/progress";

// Minimal neutral stage descriptors
const STAGES = [
  { key: "parsing", label: "Parsing" },
  { key: "chunking", label: "Indexing" },
  { key: "summarizing", label: "Summarizing" },
  { key: "extracting", label: "Extracting" },
];

export default function ProgressTracker({ progress, error, onRetry }) {
  if (!progress && !error) return null;

  // Error state simplified
  if (error) {
    // Handle both string errors and object errors
    const errorMessage = typeof error === "string" ? error : error.message;
    const errorStage = typeof error === "object" ? error.stage : null;
    const isRetryable = typeof error === "object" ? error.isRetryable : false;

    return (
      <Card className="mt-4 p-4 border border-red-300 dark:border-red-600 bg-red-50 dark:bg-red-950/40">
        <div className="flex items-start gap-3">
          <span className="text-xl">⚠️</span>
          <div className="space-y-1 flex-1">
            <p className="font-medium text-red-800 dark:text-red-300">
              {errorMessage}
            </p>
            {errorStage && (
              <p className="text-xs text-red-700 dark:text-red-400">
                Stage: {errorStage}
              </p>
            )}
            {isRetryable && onRetry && (
              <button
                onClick={onRetry}
                className="text-xs px-2 py-1 rounded bg-red-600 text-foreground hover:bg-destructive"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      </Card>
    );
  }

  // Progress state
  const { percent, message, stages, stage, details } = progress;
  const compression = details?.compression_ratio;

  return (
    <Card className="mt-4 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-sm">Processing Document</h3>
        <span className="text-xs text-muted-foreground">{percent}%</span>
      </div>
      <Progress value={percent} />
      <p className="text-sm text-muted-foreground min-h-[1.25rem]">{message}</p>
      <ol className="flex flex-wrap gap-2 text-xs">
        {STAGES.map((s) => {
          const done = stages?.[s.key];
          const current = stage === s.key;
          return (
            <li key={s.key} className="flex items-center gap-1">
              <Badge
                variant={done ? "default" : current ? "secondary" : "outline"}
              >
                {done ? "✔" : current ? "•" : ""} {s.label}
              </Badge>
            </li>
          );
        })}
      </ol>
      {compression && (
        <div className="text-xs text-muted-foreground">
          Compression: {compression}
        </div>
      )}
      {percent === 100 && (
        <div className="text-xs text-green-600 dark:text-green-400 font-medium">
          Completed
        </div>
      )}
    </Card>
  );
}
