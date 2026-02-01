/**
 * ComparisonSummaryCard Component
 *
 * Displays a summary view of the document comparison:
 * - Document labels with colored badges
 * - Key differences in visual pill cards
 * - "Open Full Comparison" button
 */

import { Maximize2, File } from "lucide-react";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Card } from "../../ui/card";

const DOC_COLORS = {
  "Document A": "bg-blue-500/10 text-blue-700 border-blue-200",
  "Document B": "bg-purple-500/10 text-purple-700 border-purple-200",
  "Document C": "bg-orange-500/10 text-orange-700 border-orange-200",
};

export default function ComparisonSummaryCard({ context, onOpenPanel }) {
  const { documents, paired_chunks, clustered_chunks } = context;
  const chunks = paired_chunks?.length > 0 ? paired_chunks : clustered_chunks;
  const isTwoDoc = context.num_documents === 2;

  // Extract key topics and similarity scores for summary
  const topTopics = chunks
    ?.slice(0, 3)
    .map((chunk, idx) => ({
      idx,
      topic: chunk.topic || `Section ${idx + 1}`,
      similarity: chunk.similarity || chunk.avg_similarity || 0,
    }));

  const getSimilarityColor = (sim) => {
    if (sim >= 0.8) return "bg-green-500/10 text-green-700 border-green-200";
    if (sim >= 0.6) return "bg-yellow-500/10 text-yellow-700 border-yellow-200";
    return "bg-red-500/10 text-red-700 border-red-200";
  };

  const getSimilarityLabel = (sim) => {
    if (sim >= 0.8) return "High";
    if (sim >= 0.6) return "Medium";
    return "Low";
  };

  return (
    <Card className="p-5 bg-gradient-to-br from-primary/5 to-primary/10 border border-primary/20">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-foreground flex items-center gap-2 mb-2">
            <span className="text-lg">📊</span>
            Document Comparison
          </h3>
          <div className="flex flex-wrap gap-2">
            {documents.map((doc, idx) => (
              <Badge
                key={doc.id}
                variant="outline"
                className={`px-3 py-1 border ${DOC_COLORS[doc.label] || "bg-gray-100"}`}
              >
                <File className="w-3 h-3 mr-1" />
                {doc.label}: {doc.filename.split("/").pop()}
              </Badge>
            ))}
          </div>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={onOpenPanel}
          className="gap-2"
        >
          <Maximize2 className="w-4 h-4" />
          <span className="hidden sm:inline">Open Full View</span>
        </Button>
      </div>

      {/* Key Differences (Top 3 topics) */}
      {topTopics && topTopics.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-3 uppercase tracking-wide">
            Key Topics Analyzed
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {topTopics.map((item) => (
              <div
                key={item.idx}
                className={`p-3 rounded-lg border ${getSimilarityColor(item.similarity)}`}
              >
                <p className="text-xs font-semibold truncate mb-1">
                  {item.topic}
                </p>
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">
                    {getSimilarityLabel(item.similarity)}
                  </span>
                  <span className="text-xs font-bold">
                    {(item.similarity * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary stats */}
      <div className="mt-4 pt-3 border-t border-primary/10 flex gap-4 text-xs text-muted-foreground">
        <span>
          <strong>{chunks?.length || 0}</strong> matched sections
        </span>
        {isTwoDoc && <span>Comparing 2 documents</span>}
        {!isTwoDoc && <span>Comparing {context.num_documents} documents</span>}
      </div>
    </Card>
  );
}
