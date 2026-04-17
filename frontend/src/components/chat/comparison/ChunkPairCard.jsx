/**
 * ChunkPairCard Component
 *
 * Displays a pair of semantically similar chunks from 2 documents
 * side-by-side with:
 * - Document labels (Doc A, Doc B)
 * - Chunk text
 * - Page citations (clickable)
 * - Similarity indicator
 * - Topic label
 */

import { FileText } from "lucide-react";
import { Badge } from "../../ui/badge";
import { Card } from "../../ui/card";
import { Button } from "../../ui/button";
import ReactMarkdown from "react-markdown";
import { useChatActions } from "../../../store";
import { useAppAuth } from "@/hooks/useAppAuth";
import SimilarityIndicator from "./SimilarityIndicator";

const DOC_STYLES = {
  A: "border-l-4 border-l-doc-a bg-doc-a/5",
  B: "border-l-4 border-l-doc-b bg-doc-b/5",
  C: "border-l-4 border-l-doc-c bg-doc-c/5",
};

export default function ChunkPairCard({ pair, documents = [] }) {
  const { getToken } = useAppAuth();
  const { highlightChunk, setActivePdfDocument } = useChatActions();
  const { chunk_a, chunk_b, similarity, topic } = pair;

  const handleCitationClick = async (chunk, docId) => {
    if (!docId) return;
    const bbox = chunk.bbox || {
      page: chunk.page,
      x0: 0,
      y0: 0,
      x1: 1,
      y1: 1,
    };
    await setActivePdfDocument(docId, getToken);
    highlightChunk({ ...bbox, docId, chunkText: chunk.text?.substring(0, 50) });
  };

  const documentLabels = ["A", "B", "C"];
  const docALabel = documentLabels[0];
  const docBLabel = documentLabels[1];
  const docAName = documents[0]?.filename?.replace(/\.[^/.]+$/, "") || "Doc A";
  const docBName = documents[1]?.filename?.replace(/\.[^/.]+$/, "") || "Doc B";
  const truncate = (s, n) => s.length > n ? s.slice(0, n) + "…" : s;

  return (
    <Card className="p-5 border border-border/50 mb-4 hover:shadow-lg transition-all animate-fade-in">
      {/* Header with topic and similarity */}
      <div className="flex items-start justify-between mb-4 pb-3 border-b border-border/30">
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-foreground tracking-tight">
            {topic}
          </h4>
        </div>
        <SimilarityIndicator similarity={similarity} />
      </div>

      {/* Side-by-side chunks */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Chunk A */}
        <div className={`p-4 rounded-lg ${DOC_STYLES[docALabel]}`}>
          <div className="flex items-center justify-between mb-3">
            <Badge className="bg-doc-a/10 text-doc-a border-0 text-xs font-medium px-2.5 py-1">
              <FileText className="w-3 h-3 mr-1.5" />
              {truncate(docAName, 22)}
            </Badge>
            {chunk_a.page && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7 px-2.5 text-muted-foreground hover:text-foreground"
                onClick={() => handleCitationClick(chunk_a, documents[0]?.id)}
              >
                <span className="mr-1">p.</span>
                <span className="font-medium">{chunk_a.page}</span>
              </Button>
            )}
          </div>
          <div className="text-sm text-foreground/85 leading-relaxed prose prose-sm dark:prose-invert max-w-none line-clamp-5">
            <ReactMarkdown>{chunk_a.text}</ReactMarkdown>
          </div>
        </div>

        {/* Chunk B */}
        <div className={`p-4 rounded-lg ${DOC_STYLES[docBLabel]}`}>
          <div className="flex items-center justify-between mb-3">
            <Badge className="bg-doc-b/10 text-doc-b border-0 text-xs font-medium px-2.5 py-1">
              <FileText className="w-3 h-3 mr-1.5" />
              {truncate(docBName, 22)}
            </Badge>
            {chunk_b.page && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7 px-2.5 text-muted-foreground hover:text-foreground"
                onClick={() => handleCitationClick(chunk_b, documents[1]?.id)}
              >
                <span className="mr-1">p.</span>
                <span className="font-medium">{chunk_b.page}</span>
              </Button>
            )}
          </div>
          <div className="text-sm text-foreground/85 leading-relaxed prose prose-sm dark:prose-invert max-w-none line-clamp-5">
            <ReactMarkdown>{chunk_b.text}</ReactMarkdown>
          </div>
        </div>
      </div>
    </Card>
  );
}
