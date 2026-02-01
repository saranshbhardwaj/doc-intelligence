/**
 * ChunkClusterCard Component
 *
 * Displays a cluster of semantically similar chunks from 3+ documents
 * in a 3-column layout with:
 * - Document labels (Doc A, Doc B, Doc C)
 * - Chunk text
 * - Page citations (clickable)
 * - Average similarity indicator
 * - Topic label
 */

import { FileText } from "lucide-react";
import { Badge } from "../../ui/badge";
import { Card } from "../../ui/card";
import { Button } from "../../ui/button";
import { useChatActions } from "../../../store";
import SimilarityIndicator from "./SimilarityIndicator";

const DOC_COLORS = {
  A: "border-blue-200 bg-blue-50 dark:bg-blue-950/30",
  B: "border-purple-200 bg-purple-50 dark:bg-purple-950/30",
  C: "border-orange-200 bg-orange-50 dark:bg-orange-950/30",
};

const DOC_LABELS = {
  A: "Doc A",
  B: "Doc B",
  C: "Doc C",
};

export default function ChunkClusterCard({ cluster, docIndex = 0 }) {
  const { highlightChunk } = useChatActions();
  const { chunks, avg_similarity, topic } = cluster;

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
  const chunkArray = Object.entries(chunks).map(([docId, chunk]) => ({
    docId,
    docLabel: documentLabels[documentLabels.length - Object.keys(chunks).length],
    chunk,
  }));

  return (
    <Card className="p-4 border border-border mb-3 hover:shadow-md transition-shadow">
      {/* Header with topic and similarity */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <h4 className="text-sm font-semibold text-foreground mb-1">
            {topic}
          </h4>
        </div>
        <SimilarityIndicator similarity={avg_similarity} />
      </div>

      {/* Multi-column chunks */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {Object.entries(chunks).map(([docId, chunk], idx) => {
          const docLabel = documentLabels[idx];
          return (
            <div
              key={docId}
              className={`p-3 rounded-lg border-2 ${DOC_COLORS[docLabel]}`}
            >
              <div className="flex items-center justify-between mb-2">
                <Badge variant="secondary" className="text-xs">
                  <FileText className="w-3 h-3 mr-1" />
                  {DOC_LABELS[docLabel]}
                </Badge>
                {chunk.page && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-xs h-6 px-2"
                    onClick={() => handleCitationClick(chunk, docLabel)}
                  >
                    📄 p.{chunk.page}
                  </Button>
                )}
              </div>
              <p className="text-xs text-foreground/80 leading-relaxed line-clamp-4">
                {chunk.text}
              </p>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
