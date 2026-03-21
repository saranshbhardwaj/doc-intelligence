import { useState, useRef, useEffect } from "react";
import { AlertTriangle, Loader2, AlertCircle } from "lucide-react";
import { createAuthenticatedApi } from "@/api/client";
import { streamJobProgress } from "@/api/sse-utils";

export const STAGE_LABELS = {
  initialization: "Initializing analysis",
  load_documents: "Loading documents",
  document_classification: "Classifying documents",
  amendment_linking: "Linking amendments",
  clause_extraction: "Extracting clauses",
  numeric_reconciliation: "Extracting metrics",
  llm_numeric_extraction: "Running LLM metric extraction",
  per_doc_analysis: "Analyzing documents",
  synthesis: "Synthesizing findings",
  verification: "Verifying findings",
  summary_generation: "Generating summary",
  llm_summary: "Running LLM summary generation",
};

async function getJobStatus(jobId, getToken) {
  const api = createAuthenticatedApi(getToken);
  const response = await api.get(`/api/jobs/${jobId}/status`);
  return response.data;
}


/**
 * Hook to stream analysis run progress via SSE (Server-Sent Events)
 * @param {string} jobId - The job ID returned from startAnalysis
 * @param {object} options - { getToken, onComplete, onError }
 * @returns {object} { run, isRunning }
 */
export function useAnalysisRun(jobId, { getToken, onComplete, onError } = {}) {
  const [run, setRun] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const sseCleanupRef = useRef(null);

  // Keep latest callbacks in refs so the SSE effect never needs to restart
  // just because a parent re-rendered and passed a new function reference.
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
  });

  useEffect(() => {
    if (!jobId || !getToken) return;

    setRun((prev) => prev ?? {
      status: "running",
      current_stage: "",
      progress_percent: 0,
      message: "Reconnecting to analysis…",
      reconnecting: true,
    });

    // Start SSE stream for this job
    streamJobProgress(jobId, getToken, {
      fetchInitialState: true,
      getJobStatus,
      onProgress: (data) => {
        setRun((prev) => ({
          ...(prev || {}),
          status: data.status || "running",
          current_stage: data.current_stage || "",
          progress_percent: data.progress_percent ?? 0,
          message: data.message || "",
          reconnecting: false,
        }));
      },
      onComplete: (data) => {
        // Extract pipeline_warnings from the completed run metadata if present
        const runWarnings = data.metadata_json?.pipeline_warnings || [];
        setWarnings(runWarnings);
        setRun((prev) => ({
          ...(prev || {}),
          status: "completed",
          progress_percent: 100,
          message: data.message || "Analysis completed",
          reconnecting: false,
        }));
        onCompleteRef.current?.(data);
      },
      onError: (error) => {
        if (error?.isRetryable) {
          setRun((prev) => ({
            ...(prev || {}),
            status: prev?.status || "running",
            message: error?.message || prev?.message || "Reconnecting to analysis…",
            reconnecting: true,
          }));
          return;
        }

        setRun((prev) => ({
          ...(prev || {}),
          status: "failed",
          error_stage: error?.error_stage,
          error_message: error?.error_message || error?.message,
          reconnecting: false,
        }));
        onErrorRef.current?.(error);
      },
    }).then((cleanup) => {
      sseCleanupRef.current = cleanup;
    });

    return () => {
      if (sseCleanupRef.current) {
        sseCleanupRef.current();
        sseCleanupRef.current = null;
      }
    };
  // Only jobId and getToken are real SSE restart triggers.
  // Callbacks are accessed via refs — no need to include them.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, getToken]);

  return {
    run,
    warnings,
    isRunning: !!run && !["completed", "failed"].includes(run?.status),
  };
}

/**
 * Banner showing pipeline warnings after a completed analysis
 */
export function WarningBanner({ warnings }) {
  if (!warnings || warnings.length === 0) return null;
  return (
    <div className="flex items-start gap-3 px-4 py-2 bg-amber-500/10 border-b border-amber-500/30 text-sm shrink-0">
      <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <span className="text-amber-700 font-medium">Analysis completed with warnings</span>
        <ul className="mt-1 space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i} className="text-amber-600 text-xs truncate">{w}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/**
 * Banner component showing real-time analysis progress
 */
export function AnalysisBanner({ run }) {
  if (!run) return null;

  if (run.status === "failed") {
    return (
      <div className="flex items-center gap-3 px-4 py-2 bg-destructive/10 border-b border-destructive/30 text-sm shrink-0">
        <AlertCircle className="w-3.5 h-3.5 text-destructive shrink-0" />
        <span className="text-destructive font-medium">Analysis failed</span>
        {run.error_message && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="text-destructive/80 truncate">{run.error_message}</span>
          </>
        )}
      </div>
    );
  }

  if (run.status === "completed") return null;

  const label = STAGE_LABELS[run.current_stage] ?? "Processing";
  const pct = run.progress_percent ?? 0;
  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-primary/5 border-b border-primary/20 text-sm shrink-0">
      <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
      <span className="text-primary font-medium">Analysis running</span>
      <span className="text-muted-foreground">·</span>
      <span className="text-muted-foreground">{run.reconnecting ? (run.message || "Reconnecting to analysis…") : label}</span>
      <div className="flex-1 max-w-xs">
        <div className="h-1.5 rounded-full bg-primary/20 overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>
      <span className="text-xs text-muted-foreground tabular-nums w-8 text-right">{pct}%</span>
    </div>
  );
}
