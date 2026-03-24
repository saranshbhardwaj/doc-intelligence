import { useState } from "react";

import { useAppAuth } from "@/hooks/useAppAuth";

import { updateFinding } from "../../../../api/pe-diligence";
import {
  ASSESSMENT_STYLES,
  CHECKLIST_STATUS,
  FINDING_STATUS_STYLES,
  SEVERITY_STYLES,
} from "../../analysis/displayConstants";
import {
  getAnalysisCategoryLabel,
  getAssessmentLabel,
  getFindingStatusLabel,
  humanizeLabel,
} from "../../analysis/formatters";

const VERIFICATION_STYLES = {
  verified: "bg-green-500/10 text-green-600 border-green-500/20",
  needs_review: "bg-amber-500/10 text-amber-600 border-amber-500/20",
};

const WORKFLOW_BADGE_STYLES = {
  ic_blocker: "bg-destructive/10 text-destructive border-destructive/30",
  specialist_review: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  underwriting_input: "bg-primary/5 text-primary border-primary/20",
  diligence_gap: "bg-muted text-muted-foreground border-border/70",
  confirmatory_review: "bg-muted text-muted-foreground border-border/70",
};

export function CitationBadge({ span, docName, onCitationClick }) {
  if (!span?.source_document_id || !span?.source_page_number) return null;
  const name = docName || "Source";
  const shortName = name.length > 20 ? `${name.slice(0, 18)}…` : name;

  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        onCitationClick({
          documentId: span.source_document_id,
          page: span.source_page_number,
          filename: name,
        });
      }}
      className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 hover:underline font-medium transition-colors"
      title={`Open ${name} at page ${span.source_page_number}`}
    >
      <span>{shortName} &middot; p.{span.source_page_number}</span>
    </button>
  );
}

export function ChecklistRow({ item, docNameMap, onCitationClick }) {
  const [expanded, setExpanded] = useState(false);
  const cfg = CHECKLIST_STATUS[item.status] || CHECKLIST_STATUS.missing;
  const Icon = cfg.icon;
  const span = item.evidence_spans?.[0];
  const evidence = span?.quote || item.evidence_quote;

  return (
    <div className="border-b last:border-0">
      <div
        className="flex items-start gap-3 px-4 py-3 hover:bg-muted/20 cursor-pointer"
        onClick={() => evidence && setExpanded((value) => !value)}
      >
        <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${cfg.color}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium leading-tight">{item.title}</p>
          {item.category && (
            <p className="text-xs text-muted-foreground mt-0.5 capitalize">
              {getAnalysisCategoryLabel(item.category)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {item.confidence != null && (
            <span className="text-xs text-muted-foreground">
              {Math.round(item.confidence * 100)}%
            </span>
          )}
          <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
          {evidence && (
            <span className="text-muted-foreground">{expanded ? "˄" : "˅"}</span>
          )}
        </div>
      </div>
      {expanded && evidence && (
        <div className="px-4 pb-3 pl-11 space-y-1.5">
          <blockquote className="border-l-2 border-muted pl-3 text-xs text-muted-foreground italic">
            &ldquo;{evidence}&rdquo;
          </blockquote>
          <CitationBadge
            span={span || { source_document_id: item.matched_document_id, source_page_number: item.matched_page_number }}
            docName={docNameMap[span?.source_document_id || item.matched_document_id]}
            onCitationClick={onCitationClick}
          />
        </div>
      )}
    </div>
  );
}

export function FindingCard({ finding, roomId, docNameMap, onCitationClick, onUpdated, compact }) {
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
  const verification = finding.metadata?.verification || {};
  const workflow = finding.metadata?.workflow || {};
  const verificationStyle = VERIFICATION_STYLES[verification.status] || VERIFICATION_STYLES.verified;
  const workflowStyle = WORKFLOW_BADGE_STYLES[workflow.bucket] || WORKFLOW_BADGE_STYLES.confirmatory_review;
  const reviewReasons = verification.reasons || [];
  const analystAction = verification.analyst_action || workflow.next_step_hint;

  return (
    <div className={`glass-card rounded-xl ${compact ? "p-3" : "p-4"} transition-opacity ${isDimmed ? "opacity-50" : ""}`}>
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

      {(verification.status || workflow.bucket || finding.metadata?.assessment) && (
        <div className="flex flex-wrap gap-1.5 mb-2">
          {verification.status && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide ${verificationStyle}`}>
              {verification.status === "needs_review" ? "Needs review" : "Verified"}
            </span>
          )}
          {workflow.bucket && (
            <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide ${workflowStyle}`}>
              {humanizeLabel(workflow.bucket)}
            </span>
          )}
          {verification.review_priority === "high" && (
            <span className="text-[10px] px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide bg-destructive/10 text-destructive border-destructive/30">
              High priority
            </span>
          )}
        </div>
      )}

      {!compact && <p className="text-sm text-foreground leading-relaxed mb-2">{finding.description}</p>}
      {compact && finding.description && (
        <p className="text-xs text-muted-foreground leading-relaxed mb-2 line-clamp-2">{finding.description}</p>
      )}

      {!compact && reviewReasons.length > 0 && (
        <div className="mb-2 rounded-lg border border-border/70 bg-muted/30 p-2.5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-1">Review flags</p>
          <div className="flex flex-wrap gap-1.5">
            {reviewReasons.map((reason) => (
              <span key={reason} className="text-[10px] px-1.5 py-0.5 rounded-full border border-border/70 bg-background text-muted-foreground font-medium">
                {humanizeLabel(reason)}
              </span>
            ))}
          </div>
        </div>
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

      {!compact && analystAction && (
        <div className="text-xs rounded-lg border border-primary/20 bg-primary/5 text-foreground p-2 mb-3">
          <span className="font-medium text-primary">Analyst next step:</span> {analystAction}
        </div>
      )}

      {saveError && <p className="text-xs text-destructive mb-2">{saveError}</p>}

      {finding.status === "open" && (
        <div className="flex gap-2">
          <button
            onClick={() => updateStatus("resolved")}
            disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors"
          >
            Resolve
          </button>
          <button
            onClick={() => updateStatus("dismissed")}
            disabled={saving}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400 hover:brightness-95 font-medium disabled:opacity-50 transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}
      {finding.status !== "open" && (
        <button
          onClick={() => updateStatus("open")}
          disabled={saving}
          className="text-xs px-2.5 py-1.5 rounded-lg border hover:bg-muted font-medium disabled:opacity-50 transition-colors"
        >
          Reopen
        </button>
      )}
    </div>
  );
}

export function FilterPill({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs px-2.5 py-1 rounded-full font-semibold transition-colors ${
        active
          ? "bg-primary text-primary-foreground"
          : "bg-background border border-border/60 text-muted-foreground hover:text-foreground hover:border-border"
      }`}
    >
      {children}
    </button>
  );
}

export function TabButton({ active, children, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-lg transition-all duration-200 ${
        active
          ? "bg-primary text-primary-foreground shadow-sm"
          : "text-muted-foreground hover:bg-muted/70 hover:text-foreground"
      }`}
    >
      {children}
    </button>
  );
}
