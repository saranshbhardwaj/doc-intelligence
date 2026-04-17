import { useMemo } from "react";
import { AlertTriangle } from "lucide-react";

import { AnalysisTriggerButton } from "../../AnalysisTriggerButton";
import { WORKSTREAM_LABELS } from "../../../analysis/displayConstants";
import { getCoverageStatusLabel, getCoverageWorkstreamLabel } from "../../../analysis/formatters";

export default function ExecutiveSummary({ checklist, findings, summary, analysisStatus, roomId, isRunning, onAnalysisStart }) {
  const covered = checklist.filter((item) => item.status === "covered").length;
  const partial = checklist.filter((item) => item.status === "partial").length;
  const missing = checklist.filter((item) => item.status === "missing").length;
  const openFindings = findings.filter((finding) => finding.status === "open").length;
  const highFindings = findings.filter((finding) => finding.severity === "high" && finding.status === "open").length;
  const mediumFindings = findings.filter((finding) => finding.severity === "medium" && finding.status === "open").length;
  const lowFindings = findings.filter((finding) => finding.severity === "low" && finding.status === "open").length;

  const completionPct = checklist.length > 0 ? Math.round((covered / checklist.length) * 100) : 0;
  const workstreamStrip = useMemo(() => {
    return [...(summary?.coverage?.workstreams || [])]
      .sort((a, b) => {
        const order = { gap: 0, partial: 1, covered: 2 };
        return (order[a.status] ?? 3) - (order[b.status] ?? 3);
      })
      .slice(0, 6);
  }, [summary]);

  return (
    <div className="space-y-3 mb-6">
      <div className="flex items-center justify-between">
        <div>
          {analysisStatus?.has_delta && (
            <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>
                <strong>{analysisStatus?.added_doc_count || 0} new document{(analysisStatus?.added_doc_count || 0) !== 1 ? "s" : ""}</strong> haven't been analyzed yet
              </span>
            </div>
          )}
        </div>
        <AnalysisTriggerButton
          roomId={roomId}
          isRunning={isRunning}
          onStart={onAnalysisStart}
          status={analysisStatus}
          loading={analysisStatus?.loading}
        />
      </div>

      <div className="bg-card border rounded-xl p-4 shadow-sm">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="text-center">
            <p className="text-2xl font-black text-primary">{completionPct}%</p>
            <div className="w-full bg-muted rounded-full h-1.5 mt-1.5 mx-auto max-w-[60px]">
              <div className="bg-primary h-1.5 rounded-full transition-all" style={{ width: `${completionPct}%` }} />
            </div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-1">Checklist</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black text-green-600">{covered}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Covered</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black text-yellow-600">{partial}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Partial</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-black text-red-500">{missing}</p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Missing</p>
          </div>
          <div className="text-center">
            <div className="flex items-center justify-center gap-1.5">
              <p className={`text-2xl font-black ${highFindings > 0 ? "text-red-500" : openFindings > 0 ? "text-yellow-600" : "text-green-600"}`}>
                {openFindings}
              </p>
            </div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-0.5">Open Findings</p>
          </div>
        </div>

        {openFindings > 0 && (
          <div className="flex items-center gap-3 mt-3 pt-3 border-t">
            <span className="text-xs text-muted-foreground font-medium">By severity:</span>
            <span className="pe-sev-high">{highFindings} High</span>
            <span className="pe-sev-medium">{mediumFindings} Medium</span>
            <span className="pe-sev-low">{lowFindings} Low</span>
          </div>
        )}

        {workstreamStrip.length > 0 && (
          <div className="mt-3 pt-3 border-t">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs text-muted-foreground font-medium">Missing by workstream</span>
              <span className="text-[11px] text-muted-foreground">Fast coverage signal</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {workstreamStrip.map((stream) => (
                <span
                  key={stream.category}
                  className={`pe-chip ${
                    stream.status === "gap"
                      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400"
                      : stream.status === "partial"
                        ? "border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400"
                        : "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400"
                  }`}
                >
                  <span className="font-semibold">{getCoverageWorkstreamLabel(stream.category) || WORKSTREAM_LABELS[stream.category]}</span>
                  <span className="opacity-80">· {getCoverageStatusLabel(stream.status)}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
