/**
 * PairedChunksView Component
 *
 * Displays all paired or clustered chunks with:
 * - Topic filter pills
 * - ChunkPairCard or ChunkClusterCard components
 * - Sorted by similarity (highest first)
 */

import { useState, useMemo } from "react";
import { useComparison, useChatActions } from "../../../store";
import ChunkPairCard from "./ChunkPairCard";
import ChunkClusterCard from "./ChunkClusterCard";
import TopicPill from "./TopicPill";
import { ScrollArea } from "../../ui/scroll-area";

export default function PairedChunksView({ context, internalScroll = true }) {
  const { toggleComparisonTopic } = useChatActions();
  const { expandedTopics } = useComparison();

  const isPaired = context.paired_chunks && context.paired_chunks.length > 0;
  const chunks = isPaired ? context.paired_chunks : context.clustered_chunks;

  // Extract unique topics for filtering
  const topics = useMemo(() => {
    if (!chunks) return [];
    const topicSet = new Set(chunks.map((c) => c.topic));
    return Array.from(topicSet).sort();
  }, [chunks]);

  // Filter chunks by topic
  const filteredChunks = useMemo(() => {
    if (expandedTopics.length === 0) return chunks;
    return chunks.filter((chunk) => expandedTopics.includes(chunk.topic));
  }, [chunks, expandedTopics]);

  if (!chunks || chunks.length === 0) {
    return (
      <div className="text-center py-6 text-muted-foreground">
        <p className="text-sm">No matched sections found</p>
      </div>
    );
  }

  const toTopicSlug = (value) =>
    String(value || "")
      .toLowerCase()
      .trim()
      .replace(/\s+/g, "-")
      .replace(/[^a-z0-9-]/g, "");

  return (
    <div className="space-y-4">
      {/* Topic Filter Pills */}
      {topics.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground mb-2 uppercase tracking-wide">
            Filter by Topic
          </p>
          <ScrollArea className="w-full" orientation="horizontal">
            <div className="flex gap-2 pb-2 pr-4 flex-nowrap min-w-max">
              {topics.map((topic) => (
                <TopicPill
                  key={topic}
                  topic={topic}
                  isActive={expandedTopics.includes(topic)}
                  onClick={() => toggleComparisonTopic(topic)}
                />
              ))}
            </div>
          </ScrollArea>
        </div>
      )}

      {/* Chunks List */}
      <div
        className={`space-y-2 ${
          internalScroll ? "max-h-96 overflow-y-auto pr-4" : ""
        }`}
      >
        {filteredChunks && filteredChunks.length > 0 ? (
          filteredChunks.map((chunk, idx) => (
            <div
              key={idx}
              data-comparison-topic={toTopicSlug(chunk.topic)}
            >
              {isPaired ? (
                <ChunkPairCard pair={chunk} docIndex={idx} />
              ) : (
                <ChunkClusterCard cluster={chunk} docIndex={idx} />
              )}
            </div>
          ))
        ) : (
          <div className="text-center py-4 text-muted-foreground">
            <p className="text-sm">
              No sections match the selected topics
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
