import { useMemo, useState } from "react";

import { DOCS_PAGE_SIZE } from "../../../analysis/displayConstants";
import DocumentAnalysisCard from "./DocumentAnalysisCard";

export default function ByDocumentTab({ docs, checklist, findings, docNameMap, onCitationClick, roomId, setFindings }) {
  const [docsPage, setDocsPage] = useState(1);

  const sortedDocs = useMemo(() => {
    return [...docs].sort((a, b) => {
      const aFindings = findings.filter((finding) =>
        finding.source_document_id === a.document_id ||
        finding.evidence_spans?.some((span) => span.source_document_id === a.document_id)
      ).length;
      const bFindings = findings.filter((finding) =>
        finding.source_document_id === b.document_id ||
        finding.evidence_spans?.some((span) => span.source_document_id === b.document_id)
      ).length;
      if (aFindings !== bFindings) return bFindings - aFindings;
      return (a.filename || "").localeCompare(b.filename || "");
    });
  }, [docs, findings]);

  const visibleDocs = sortedDocs.slice(0, docsPage * DOCS_PAGE_SIZE);
  const hasMore = visibleDocs.length < sortedDocs.length;

  return (
    <div className="space-y-2">
      {sortedDocs.length === 0 ? (
        <p className="text-sm text-muted-foreground text-center py-8">No documents in this room.</p>
      ) : (
        <>
          {visibleDocs.map((doc) => (
            <DocumentAnalysisCard
              key={doc.id}
              doc={doc}
              checklist={checklist}
              findings={findings}
              docNameMap={docNameMap}
              onCitationClick={onCitationClick}
              roomId={roomId}
              onFindingUpdated={(updated) =>
                setFindings((prev) => prev.map((item) => (item.id === updated.id ? updated : item)))
              }
            />
          ))}
          {hasMore && (
            <button
              onClick={() => setDocsPage((value) => value + 1)}
              className="w-full text-xs text-muted-foreground hover:text-foreground border border-border/60 rounded-lg py-2.5 hover:bg-muted/30 transition-colors mt-2"
            >
              Show {Math.min(DOCS_PAGE_SIZE, sortedDocs.length - visibleDocs.length)} more documents
            </button>
          )}
        </>
      )}
    </div>
  );
}
