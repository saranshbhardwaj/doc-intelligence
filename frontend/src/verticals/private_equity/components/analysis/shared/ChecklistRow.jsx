import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { CHECKLIST_STATUS } from "../../../analysis/displayConstants";
import { getAnalysisCategoryLabel } from "../../../analysis/formatters";
import CitationBadge from "./CitationBadge";

export default function ChecklistRow({ item, docNameMap, onCitationClick }) {
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
            <span className="text-muted-foreground">
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </span>
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
