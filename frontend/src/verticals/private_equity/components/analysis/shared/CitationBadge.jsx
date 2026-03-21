import { FileText } from "lucide-react";

export default function CitationBadge({ span, docName, onCitationClick }) {
  if (!span?.source_document_id || !span?.source_page_number) return null;
  const name = docName || "Source";
  const shortName = name.length > 20 ? `${name.slice(0, 18)}…` : name;

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onCitationClick({
          documentId: span.source_document_id,
          page: span.source_page_number,
          filename: name,
        });
      }}
      className="inline-flex items-center gap-1 text-xs text-primary hover:text-primary/80 hover:underline font-medium transition-colors"
      title={`Open ${name} at page ${span.source_page_number}`}
    >
      <FileText className="w-3 h-3" />
      {shortName} &middot; p.{span.source_page_number}
    </button>
  );
}
