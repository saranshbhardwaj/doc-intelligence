import { useMemo, useState } from "react";
import { ChevronRight, Link2 } from "lucide-react";

import { DOC_TYPE_COLORS, DOC_TYPE_LABELS } from "../../../constants";
import { DOC_STATUS_CFG } from "../../../analysis/displayConstants";
import ChecklistRow from "../shared/ChecklistRow";
import FindingCard from "../shared/FindingCard";
import AmendmentChainTree from "./AmendmentChainTree";

export default function DocumentAnalysisCard({
  doc, checklist, findings, docNameMap, onCitationClick, roomId, onFindingUpdated,
}) {
  const [expanded, setExpanded] = useState(false);

  const docId = doc.document_id;
  const classification = doc.metadata?.document_classification;
  const docType = classification?.document_type;
  const amendmentLink = doc.metadata?.amendment_link;
  const amendmentParent = amendmentLink?.parent_document_id;
  const parentDoc = amendmentParent ? docNameMap[amendmentParent] : null;

  const docChecklist = useMemo(() =>
    checklist.filter((item) => {
      if (item.matched_document_id === docId) return true;
      return item.evidence_spans?.some((span) => span.source_document_id === docId);
    }),
  [checklist, docId]);

  const docFindings = useMemo(() =>
    findings.filter((finding) => {
      if (finding.source_document_id === docId) return true;
      return finding.evidence_spans?.some((span) => span.source_document_id === docId);
    }),
  [findings, docId]);

  const checklistCovered = docChecklist.filter((item) => item.status === "covered").length;
  const checklistTotal = docChecklist.length;
  const openFindings = docFindings.filter((finding) => finding.status === "open").length;
  const highFindings = docFindings.filter((finding) => finding.severity === "high" && finding.status === "open").length;
  const hasAnalysisData = docChecklist.length > 0 || docFindings.length > 0 || docType;

  const docStatus = highFindings > 0 ? "conflict"
    : openFindings > 0 ? "warning"
    : docFindings.length > 0 ? "ok"
    : "neutral";
  const statusCfg = DOC_STATUS_CFG[docStatus];
  const StatusIcon = statusCfg.icon;

  const topFindings = useMemo(() =>
    docFindings
      .filter((finding) => finding.status === "open")
      .sort((a, b) => ({ high: 0, medium: 1, low: 2 }[a.severity] ?? 2) - ({ high: 0, medium: 1, low: 2 }[b.severity] ?? 2))
      .slice(0, 2),
  [docFindings]);

  return (
    <div className="bg-card border rounded-xl overflow-hidden shadow-sm">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/20 transition-colors"
        onClick={() => setExpanded((value) => !value)}
      >
        <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${statusCfg.bg}`}>
          <StatusIcon className={`w-4 h-4 ${statusCfg.text}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold truncate">{doc.filename}</span>
            {docType && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium whitespace-nowrap ${DOC_TYPE_COLORS[docType] || DOC_TYPE_COLORS.other}`}>
                {DOC_TYPE_LABELS[docType] || docType}
              </span>
            )}
          </div>
          {amendmentParent && (
            <div className="flex items-center gap-1 text-xs text-blue-500 mt-0.5">
              <Link2 className="w-3 h-3" />
              <span className="truncate max-w-[200px]">Amends: {parentDoc || "Parent document"}</span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {hasAnalysisData && (
            <>
              {checklistTotal > 0 && (
                <span className="text-xs text-muted-foreground">
                  {checklistCovered}/{checklistTotal} checklist
                </span>
              )}
              {openFindings > 0 && (
                <span className={`text-xs font-medium ${highFindings > 0 ? "text-red-500" : "text-yellow-600"}`}>
                  {openFindings} finding{openFindings !== 1 ? "s" : ""}
                </span>
              )}
            </>
          )}
          {!hasAnalysisData && (
            <span className="text-xs text-muted-foreground">No analysis data</span>
          )}
          <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        </div>
      </div>

      {expanded && (
        <div className="border-t px-4 py-3 space-y-4">
          {amendmentParent && (
            <AmendmentChainTree
              docId={docId}
              docNameMap={docNameMap}
              amendmentLink={amendmentLink}
              parentDoc={parentDoc}
            />
          )}

          {topFindings.length > 0 && (
            <div className="bg-muted/30 rounded-lg p-3 space-y-2">
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                Key Issues
              </h4>
              {topFindings.map((finding) => (
                <div key={finding.id} className="flex items-start gap-2">
                  <span className={`pe-sev-${finding.severity} shrink-0 mt-0.5`}>{finding.severity}</span>
                  <p className="text-xs text-foreground leading-relaxed">{finding.title}</p>
                </div>
              ))}
            </div>
          )}

          {docChecklist.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                Checklist Items ({docChecklist.length})
              </h4>
              <div className="bg-background border rounded-lg overflow-hidden">
                {docChecklist.map((item) => (
                  <ChecklistRow
                    key={item.id}
                    item={item}
                    docNameMap={docNameMap}
                    onCitationClick={onCitationClick}
                  />
                ))}
              </div>
            </div>
          )}

          {docFindings.length > 0 && (
            <div>
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
                Findings ({docFindings.length})
              </h4>
              <div className="space-y-2">
                {[...docFindings]
                  .sort((a, b) => {
                    if (a.status === "open" && b.status !== "open") return -1;
                    if (b.status === "open" && a.status !== "open") return 1;
                    const sev = { high: 0, medium: 1, low: 2 };
                    return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
                  })
                  .map((finding) => (
                    <FindingCard
                      key={finding.id}
                      finding={finding}
                      roomId={roomId}
                      docNameMap={docNameMap}
                      onCitationClick={onCitationClick}
                      onUpdated={onFindingUpdated}
                      compact
                    />
                  ))}
              </div>
            </div>
          )}

          {!hasAnalysisData && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No analysis data extracted from this document yet.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
