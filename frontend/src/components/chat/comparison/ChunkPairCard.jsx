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
import { useChatActions } from "../../../store";
import SimilarityIndicator from "./SimilarityIndicator";

const DOC_STYLES = {
  A: "border-l-4 border-l-doc-a bg-doc-a/5",
  B: "border-l-4 border-l-doc-b bg-doc-b/5",
  C: "border-l-4 border-l-doc-c bg-doc-c/5",
};

const DOC_LABELS = {
  A: "Doc A",
  B: "Doc B",
  C: "Doc C",
};

export default function ChunkPairCard({ pair, docIndex = 0 }) {
  const { highlightChunk } = useChatActions();
  const { chunk_a, chunk_b, similarity, topic } = pair;

  const handleCitationClick = (chunk, docLabel) => {
    // Dispatch highlight action with bbox
    const bbox = chunk.bbox || {
      page: chunk.page,
      x0: 0,
      y0: 0,
      x1: 1,
      y1: 1,
    };
    highlightChunk({
      ...bbox,
      docId: docLabel,
      chunkText: chunk.text?.substring(0, 50),
    });
  };

  const documentLabels = ["A", "B", "C"];
  const docALabel = documentLabels[0];
  const docBLabel = documentLabels[1];

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
              {DOC_LABELS[docALabel]}
            </Badge>
            {chunk_a.page && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7 px-2.5 text-muted-foreground hover:text-foreground"
                onClick={() => handleCitationClick(chunk_a, docALabel)}
              >
                <span className="mr-1">p.</span>
                <span className="font-medium">{chunk_a.page}</span>
              </Button>
            )}
          </div>
          <p className="text-sm text-foreground/85 leading-relaxed line-clamp-5">
            {chunk_a.text}
          </p>
        </div>

        {/* Chunk B */}
        <div className={`p-4 rounded-lg ${DOC_STYLES[docBLabel]}`}>
          <div className="flex items-center justify-between mb-3">
            <Badge className="bg-doc-b/10 text-doc-b border-0 text-xs font-medium px-2.5 py-1">
              <FileText className="w-3 h-3 mr-1.5" />
              {DOC_LABELS[docBLabel]}
            </Badge>
            {chunk_b.page && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs h-7 px-2.5 text-muted-foreground hover:text-foreground"
                onClick={() => handleCitationClick(chunk_b, docBLabel)}
              >
                <span className="mr-1">p.</span>
                <span className="font-medium">{chunk_b.page}</span>
              </Button>
            )}
          </div>
          <p className="text-sm text-foreground/85 leading-relaxed line-clamp-5">
            {chunk_b.text}
          </p>
        </div>
      </div>
    </Card>
  );
}
