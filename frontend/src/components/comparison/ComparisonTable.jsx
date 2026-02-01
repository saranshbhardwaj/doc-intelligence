/**
 * ComparisonTable Component
 *
 * Displays comparison data in a compact table format with:
 * - Document columns (Doc A, Doc B, Doc C)
 * - Topic/Section rows
 * - Similarity scores
 * - Clickable page citations
 * - Sortable by similarity
 */

import { useState, useMemo } from "react";
import { ArrowUpDown, FileText } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "../ui/tooltip";
import { useChatActions } from "../../store";

const DOC_COLORS = {
  A: "border-doc-a/20 bg-doc-a/10 text-doc-a",
  B: "border-doc-b/20 bg-doc-b/10 text-doc-b",
  C: "border-doc-c/20 bg-doc-c/10 text-doc-c",
};

export default function ComparisonTable({ context }) {
  const { highlightChunk } = useChatActions();
  const [sortBy, setSortBy] = useState("similarity"); // 'similarity' | 'topic'
  const [sortOrder, setSortOrder] = useState("desc"); // 'asc' | 'desc'

  const { documents, paired_chunks, clustered_chunks } = context;
  const isPaired = paired_chunks && paired_chunks.length > 0;
  const chunks = isPaired ? paired_chunks : clustered_chunks;

  const documentLabels = ["A", "B", "C"];
  const documentsById = useMemo(() => {
    const map = new Map();
    (documents || []).forEach((doc) => map.set(doc.id, doc));
    return map;
  }, [documents]);

  const toTopicSlug = (value) =>
    String(value || "")
      .toLowerCase()
      .trim()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "");

  // Sort chunks
  const sortedChunks = useMemo(() => {
    if (!chunks) return [];

    const sorted = [...chunks].sort((a, b) => {
      if (sortBy === "similarity") {
        const simA = a.similarity || a.avg_similarity || 0;
        const simB = b.similarity || b.avg_similarity || 0;
        return sortOrder === "desc" ? simB - simA : simA - simB;
      } else {
        // Sort by topic
        return sortOrder === "desc"
          ? b.topic.localeCompare(a.topic)
          : a.topic.localeCompare(b.topic);
      }
    });

    return sorted;
  }, [chunks, sortBy, sortOrder]);

  const avgSimilarity = useMemo(() => {
    if (!sortedChunks.length) return 0;
    const total = sortedChunks.reduce((sum, chunk) => {
      const sim = chunk.similarity || chunk.avg_similarity || 0;
      return sum + sim;
    }, 0);
    return total / sortedChunks.length;
  }, [sortedChunks]);

  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortOrder("desc");
    }
  };

  const handleCitationClick = (chunk, docLabel) => {
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
    });
  };

  const getSimilarityColor = (sim) => {
    if (sim >= 0.8) return "text-similarity-high";
    if (sim >= 0.6) return "text-similarity-mid";
    return "text-similarity-low";
  };

  if (!chunks || chunks.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground">
        <p className="text-sm">No data to display</p>
      </div>
    );
  }

  return (
    <TooltipProvider delayDuration={200}>
      <div className="w-full">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="comparison-stat">
            {sortedChunks.length} rows
          </Badge>
          <Badge variant="secondary" className="comparison-stat">
            Avg. similarity {(avgSimilarity * 100).toFixed(0)}%
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          Sorted by <span className="font-medium text-foreground">{sortBy}</span>
          <span className="text-muted-foreground/60">•</span>
          {sortOrder.toUpperCase()}
        </div>
        </div>

        <Table className="comparison-table">
          <TableHeader className="comparison-table-head">
            <TableRow>
              <TableHead className="w-[200px]">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleSort("topic")}
                  className="h-8 px-2 text-xs"
                >
                  Topic
                  <ArrowUpDown className="ml-2 h-3 w-3" />
                </Button>
              </TableHead>
              {documents.map((doc, idx) => (
                <TableHead key={doc.id} className="min-w-[260px]">
                  <Badge
                    variant="outline"
                    className={`comparison-doc-pill ${DOC_COLORS[documentLabels[idx]]}`}
                  >
                    <FileText className="w-3 h-3" />
                    {doc.label}
                  </Badge>
                </TableHead>
              ))}
              <TableHead className="w-[140px]">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleSort("similarity")}
                  className="h-8 px-2 text-xs"
                >
                  Similarity
                  <ArrowUpDown className="ml-2 h-3 w-3" />
                </Button>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedChunks.map((chunk, idx) => {
              const sim = chunk.similarity || chunk.avg_similarity || 0;

              return (
                <TableRow
                  key={idx}
                  className="comparison-row"
                  data-comparison-topic={toTopicSlug(chunk.topic)}
                >
                  <TableCell className="font-medium text-xs align-top text-foreground/90">
                    <div className="line-clamp-3">{chunk.topic}</div>
                  </TableCell>

                {isPaired ? (
                  // 2-document comparison (paired chunks)
                  <>
                    <TableCell className="text-xs align-top">
                      <p className="line-clamp-3 mb-2 text-foreground/90">
                        {chunk.chunk_a.text}
                      </p>
                      {chunk.chunk_a.page && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="comparison-cite"
                              onClick={() =>
                                handleCitationClick(
                                  chunk.chunk_a,
                                  documentLabels[0]
                                )
                              }
                            >
                              <FileText className="h-3 w-3" />
                              <span>p.{chunk.chunk_a.page}</span>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent
                            side="top"
                            align="start"
                            className="comparison-cite-tooltip"
                          >
                            <div className="space-y-1">
                              <p className="text-xs font-medium text-foreground">
                                {documents[0]?.filename?.split("/").pop() ||
                                  documents[0]?.label ||
                                  "Document A"}
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                Page {chunk.chunk_a.page}
                              </p>
                              <p className="text-xs text-foreground/90 line-clamp-6">
                                {chunk.chunk_a.text}
                              </p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                    <TableCell className="text-xs align-top">
                      <p className="line-clamp-3 mb-2 text-foreground/90">
                        {chunk.chunk_b.text}
                      </p>
                      {chunk.chunk_b.page && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="comparison-cite"
                              onClick={() =>
                                handleCitationClick(
                                  chunk.chunk_b,
                                  documentLabels[1]
                                )
                              }
                            >
                              <FileText className="h-3 w-3" />
                              <span>p.{chunk.chunk_b.page}</span>
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent
                            side="top"
                            align="start"
                            className="comparison-cite-tooltip"
                          >
                            <div className="space-y-1">
                              <p className="text-xs font-medium text-foreground">
                                {documents[1]?.filename?.split("/").pop() ||
                                  documents[1]?.label ||
                                  "Document B"}
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                Page {chunk.chunk_b.page}
                              </p>
                              <p className="text-xs text-foreground/90 line-clamp-6">
                                {chunk.chunk_b.text}
                              </p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      )}
                    </TableCell>
                  </>
                ) : (
                  // 3-document comparison (clustered chunks)
                  Object.entries(chunk.chunks).map(([docId, chunkData], docIdx) => {
                    const doc = documentsById.get(docId);
                    return (
                      <TableCell key={docId} className="text-xs align-top">
                        <p className="line-clamp-3 mb-2 text-foreground/90">
                          {chunkData.text}
                        </p>
                        {chunkData.page && (
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="comparison-cite"
                                onClick={() =>
                                  handleCitationClick(
                                    chunkData,
                                    documentLabels[docIdx]
                                  )
                                }
                              >
                                <FileText className="h-3 w-3" />
                                <span>p.{chunkData.page}</span>
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent
                              side="top"
                              align="start"
                              className="comparison-cite-tooltip"
                            >
                              <div className="space-y-1">
                                <p className="text-xs font-medium text-foreground">
                                  {doc?.filename?.split("/").pop() ||
                                    doc?.label ||
                                    "Document"}
                                </p>
                                <p className="text-[11px] text-muted-foreground">
                                  Page {chunkData.page}
                                </p>
                                <p className="text-xs text-foreground/90 line-clamp-6">
                                  {chunkData.text}
                                </p>
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </TableCell>
                    );
                  })
                )}

                <TableCell className="text-center align-top">
                  <span className={`text-sm font-semibold ${getSimilarityColor(sim)}`}>
                    {(sim * 100).toFixed(0)}%
                  </span>
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </TooltipProvider>
  );
}
