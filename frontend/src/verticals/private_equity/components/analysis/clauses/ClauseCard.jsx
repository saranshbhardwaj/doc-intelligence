import { ChevronRight } from "lucide-react";

import { PLAYBOOK_LABELS, REVIEW_BADGE } from "../../../analysis/displayConstants";
import { getAssessmentLabel } from "../../../analysis/formatters";
import CitationBadge from "../shared/CitationBadge";
import FieldPills from "./FieldPills";

export default function ClauseCard({ clause, docNameMap, onCitationClick }) {
  const citations = clause.citations || [];
  const extractedFields = clause.extracted_fields || {};

  return (
    <div className="pe-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{PLAYBOOK_LABELS[clause.playbook_id] || clause.playbook_id}</h3>
          <p className="text-xs text-muted-foreground mt-1">{clause.summary || "No summary available."}</p>
        </div>
        <span className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border ${REVIEW_BADGE[clause.review_status] || REVIEW_BADGE.not_reviewed}`}>
          {clause.review_status || "not_reviewed"}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="pe-chip">Assessment: {getAssessmentLabel(clause.assessment)}</span>
        {clause.version_label && <span className="pe-chip">Version: {clause.version_label}</span>}
        {clause.doc_type && <span className="pe-chip">Doc Type: {clause.doc_type.replace(/_/g, " ")}</span>}
      </div>

      <FieldPills fields={extractedFields} />

      {!!citations.length && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Supporting Citations</p>
          <div className="flex flex-wrap gap-2">
            {citations.map((citation, idx) => (
              <CitationBadge
                key={`${citation.document_id || idx}-${citation.page_number || idx}`}
                citation={citation}
                docNameMap={docNameMap}
                onClick={onCitationClick}
              />
            ))}
          </div>
        </div>
      )}

      {!!clause.notes?.length && (
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Notes</p>
          <div className="space-y-1.5">
            {clause.notes.map((note, idx) => (
              <div key={`${note}-${idx}`} className="text-sm text-foreground flex items-start gap-2">
                <ChevronRight className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                <span>{note}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
