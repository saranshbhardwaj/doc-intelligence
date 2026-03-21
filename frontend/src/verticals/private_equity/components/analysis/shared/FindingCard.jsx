import { useState } from "react";

import { useAppAuth } from "@/hooks/useAppAuth";
import { updateFinding } from "../../../../api/pe-diligence";
import {
  ASSESSMENT_STYLES,
  FINDING_STATUS_STYLES,
  SEVERITY_STYLES,
} from "../../../analysis/displayConstants";
import {
  getAnalysisCategoryLabel,
  getAssessmentLabel,
  getFindingStatusLabel,
} from "../../../analysis/formatters";
import CitationBadge from "./CitationBadge";

export default function FindingCard({ finding, roomId, docNameMap, onCitationClick, onUpdated, compact }) {
  const { getToken } = useAppAuth();
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  async function updateStatus(newStatus) {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await updateFinding(getToken, roomId, finding.id, { status: newStatus });
      onUpdated(updated);
    } catch (err) {
      setSaveError(err.response?.data?.detail || "Update failed");
    } finally {
      setSaving(false);
    }
  }

  const severityStyle = SEVERITY_STYLES[finding.severity] || SEVERITY_STYLES.low;
  const statusStyle = FINDING_STATUS_STYLES[finding.status] || FINDING_STATUS_STYLES.open;
  const isDimmed = finding.status !== "open";
  const span = finding.evidence_spans?.[0];

  return (
    <div className={`bg-card border rounded-xl ${compact ? "p-3" : "p-4"} shadow-sm transition-opacity ${isDimmed ? "opacity-60" : ""}`}>
      <div className="flex items-start gap-3 mb-2">
        <span className={`text-xs px-2 py-0.5 rounded-full font-bold capitalize border shrink-0 mt-0.5 ${severityStyle}`}>
          {finding.severity}
        </span>
        {finding.metadata?.assessment && finding.metadata.assessment !== "standard" && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold uppercase tracking-wide border shrink-0 mt-0.5 ${ASSESSMENT_STYLES[finding.metadata.assessment] || ""}`}>
            {getAssessmentLabel(finding.metadata.assessment)}
          </span>
        )}
        <div className="flex-1 min-w-0">
          <p className={`${compact ? "text-xs" : "text-sm"} font-semibold leading-tight`}>{finding.title}</p>
          {finding.category && (
            <p className="text-xs text-muted-foreground mt-0.5 capitalize">
              {getAnalysisCategoryLabel(finding.category)}
            </p>
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize shrink-0 ${statusStyle}`}>
          {getFindingStatusLabel(finding.status)}
        </span>
      </div>

      {!compact && <p className="text-sm text-foreground leading-relaxed mb-2">{finding.description}</p>}
      {compact && finding.description && (
        <p className="text-xs text-muted-foreground leading-relaxed mb-2 line-clamp-2">{finding.description}</p>
      )}

      {finding.evidence_quote && (
        <div className="mb-2 space-y-1.5">
          <blockquote className="border-l-2 border-muted pl-3 text-xs text-muted-foreground italic">
            &ldquo;{finding.evidence_quote}&rdquo;
          </blockquote>
          <CitationBadge
            span={span || { source_document_id: finding.source_document_id, source_page_number: finding.source_page_number }}
            docName={docNameMap[span?.source_document_id || finding.source_document_id]}
            onCitationClick={onCitationClick}
          />
        </div>
      )}

      {!compact && finding.recommendation && (
        <p className="text-xs text-muted-foreground bg-muted/40 rounded p-2 mb-3">
          <span className="font-medium">Recommendation:</span> {finding.recommendation}
        </p>
      )}

      {saveError && <p className="text-xs text-destructive mb-2">{saveError}</p>}

      {finding.status === "open" && (
        <div className="flex gap-2">
          <button onClick={() => updateStatus("resolved")} disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors">
            Resolve
          </button>
          <button onClick={() => updateStatus("dismissed")} disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors">
            Dismiss
          </button>
        </div>
      )}
      {finding.status !== "open" && (
        <button onClick={() => updateStatus("open")} disabled={saving}
          className="text-xs px-2.5 py-1.5 rounded-lg border hover:bg-muted font-medium disabled:opacity-50 transition-colors">
          Reopen
        </button>
      )}
    </div>
  );
}
