import { Play, RefreshCw, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../../../components/ui/dropdown-menu";

/**
 * Smart analysis trigger button that adapts based on analysis status.
 * Shows delta info and defaults to incremental analysis when docs have changed.
 *
 * @param {string} roomId - Room ID
 * @param {boolean} isRunning - Analysis currently running
 * @param {Function} onStart - Callback: onStart(incremental: bool)
 * @param {Object} status - From useAnalysisStatus: { has_completed_run, has_delta, added_doc_count, removed_doc_count }
 * @param {boolean} loading - Status loading state
 */
export function AnalysisTriggerButton({ roomId: _roomId, isRunning, onStart, status, loading }) {
  if (loading) {
    return (
      <button disabled className="pe-action-primary opacity-50 cursor-not-allowed">
        <Play className="w-4 h-4" />
        {isRunning ? "Analysis Running…" : "Loading…"}
      </button>
    );
  }

  const hasCompletedRun = status?.has_completed_run;
  const hasDelta = status?.has_delta;
  const addedCount = status?.added_doc_count ?? 0;
  const removedCount = status?.removed_doc_count ?? 0;

  // No prior run: single "Run Analysis" button
  if (!hasCompletedRun) {
    return (
      <button
        onClick={() => onStart(false)}
        disabled={isRunning}
        title={isRunning ? "Analysis is already running" : "Run full analysis on all documents"}
        className="pe-action-primary disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Play className="w-4 h-4" />
        {isRunning ? "Analysis Running…" : "Run Analysis"}
      </button>
    );
  }

  // Prior run exists but no delta: single "Re-run Analysis" button
  if (!hasDelta) {
    return (
      <button
        onClick={() => onStart(false)}
        disabled={isRunning}
        title={isRunning ? "Analysis is already running" : "Re-run analysis on all documents"}
        className="pe-action-primary disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <RefreshCw className="w-4 h-4" />
        {isRunning ? "Analysis Running…" : "Re-run Analysis"}
      </button>
    );
  }

  // Prior run + delta: split button with primary as incremental
  const deltaLabel = addedCount > 0 && removedCount > 0
    ? `${addedCount} new, ${removedCount} removed`
    : addedCount > 0
    ? `${addedCount} new`
    : `${removedCount} removed`;

  return (
    <div className="flex items-stretch">
      <button
        onClick={() => onStart(true)}
        disabled={isRunning}
        title={isRunning ? "Analysis is already running" : `Update analysis — only ${deltaLabel}`}
        className="pe-action-primary rounded-r-none border-r border-primary/40 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Play className="w-4 h-4" />
        <span>{isRunning ? "Analysis Running…" : `Update Analysis (${addedCount} new)`}</span>
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            disabled={isRunning}
            className="pe-action-primary rounded-l-none px-2 disabled:opacity-50 disabled:cursor-not-allowed"
            title="More analysis options"
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuItem onClick={() => onStart(true)}>
            <Play className="w-3.5 h-3.5 mr-2" />
            Update Analysis
            <span className="ml-auto text-xs text-muted-foreground">{deltaLabel}</span>
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onStart(false)}>
            <RefreshCw className="w-3.5 h-3.5 mr-2" />
            Full Re-run
            <span className="ml-auto text-xs text-muted-foreground">all docs</span>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
