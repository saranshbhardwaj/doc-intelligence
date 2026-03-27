/**
 * ComparisonMessage Component
 *
 * Wrapper component that detects comparison responses and renders them
 * with specialized UI instead of plain markdown.
 *
 * Shows:
 * 1. ComparisonSummaryCard - Always visible (key differences + document badges)
 * 2. Expandable paired/clustered chunks section
 * 3. Main response text with markdown + clickable citations
 */

import { useState, memo } from "react";
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Card } from "../../ui/card";
import { TooltipProvider } from "../../ui/tooltip";
import { useComparison, useChatActions } from "../../../store";
import ComparisonSummaryCard from "./ComparisonSummaryCard";
import PairedChunksView from "./PairedChunksView";
import CitationLink from "../../common/CitationLink";
import { splitTextWithCitations } from "@/utils/citations";

function renderCitationText(text, context) {
  if (!text) return text;
  const parts = splitTextWithCitations(text);
  if (parts.length === 1 && typeof parts[0] === "string") return text;
  return parts.map((part, i) =>
    typeof part === "string" ? part : (
      <CitationLink key={i} token={part.token} comparisonContext={context} variant="inline" />
    )
  );
}

const ComparisonMessage = memo(function ComparisonMessage({ message, onOpenComparisonPanel }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const comparison = useComparison();
  const { setComparisonContext } = useChatActions();

  const messageComparisonContext = message?.comparison_metadata || null;
  const resolvedContext = messageComparisonContext || comparison.context;
  const isComparisonActive = Boolean(resolvedContext);

  // Check if this message has comparison context
  if (!isComparisonActive) {
    return null;
  }

  const context = resolvedContext;
  const numPairs = context?.paired_chunks?.length || 0;
  const numClusters = context?.clustered_chunks?.length || 0;
  const isTwoDoc = context?.num_documents === 2;

  /**
   * Custom markdown components for rendering with citations
   */
  const markdownComponents = {
    p: ({ children, ...props }) => {
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === "string") {
          return renderCitationText(child, resolvedContext);
        }
        return child;
      });
      return <p {...props}>{processedChildren}</p>;
    },
    td: ({ children, ...props }) => {
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === "string") {
          return renderCitationText(child, resolvedContext);
        }
        return child;
      });
      return <td {...props}>{processedChildren}</td>;
    },
    th: ({ children, ...props }) => {
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === "string") {
          return renderCitationText(child, resolvedContext);
        }
        return child;
      });
      return <th {...props}>{processedChildren}</th>;
    },
    li: ({ children, ...props }) => {
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === "string") {
          return renderCitationText(child, resolvedContext);
        }
        return child;
      });
      return <li {...props}>{processedChildren}</li>;
    },
    strong: ({ children, ...props }) => {
      const processedChildren = React.Children.map(children, (child) => {
        if (typeof child === "string") {
          return renderCitationText(child, resolvedContext);
        }
        return child;
      });
      return <strong {...props}>{processedChildren}</strong>;
    },
  };

  return (
    <TooltipProvider delayDuration={200}>
      <div className="space-y-4 w-full">
        {/* Summary Card (always visible) */}
        <ComparisonSummaryCard
          context={context}
          onOpenPanel={() => {
            setComparisonContext(context);
            onOpenComparisonPanel?.();
          }}
        />

        {/* Expandable Paired/Clustered Chunks Section */}
        {(numPairs > 0 || numClusters > 0) && (
          <Card className="p-4 bg-card border border-border">
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="w-full flex items-center justify-between text-left hover:opacity-80 transition-opacity"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  {isTwoDoc ? "Matched Sections" : "Grouped Sections"}
                </span>
                <span className="text-xs bg-primary/10 text-primary px-2 py-1 rounded-full">
                  {numPairs + numClusters}
                </span>
              </div>
              {isExpanded ? (
                <ChevronUp className="w-4 h-4 text-muted-foreground" />
              ) : (
                <ChevronDown className="w-4 h-4 text-muted-foreground" />
              )}
            </button>

            {/* Expanded content */}
            {isExpanded && (
              <div className="mt-4 pt-4 border-t border-border">
                <PairedChunksView context={context} />
              </div>
            )}
          </Card>
        )}

        {/* Main comparison text response with markdown + clickable citations */}
        {message.content && (
          <div className="prose prose-sm md:prose-base max-w-none dark:prose-invert
            prose-table:border-collapse prose-table:w-full
            prose-th:border prose-th:border-border prose-th:bg-muted/50 prose-th:p-2 prose-th:text-left prose-th:font-semibold
            prose-td:border prose-td:border-border prose-td:p-2
            prose-tr:even:bg-muted/30
            prose-p:text-muted-foreground prose-p:leading-relaxed
            prose-strong:text-foreground prose-strong:font-semibold
            prose-ul:text-muted-foreground prose-ul:my-3
            prose-ol:text-muted-foreground prose-ol:my-3
            prose-li:my-1
            prose-a:text-primary prose-a:no-underline hover:prose-a:underline
            prose-blockquote:border-l-primary prose-blockquote:bg-muted/50 prose-blockquote:py-1
            prose-code:text-primary prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-sm prose-code:before:content-none prose-code:after:content-none
            prose-pre:bg-muted prose-pre:border prose-pre:border-border
            prose-h3:text-lg prose-h3:mt-6 prose-h3:mb-3
            prose-h4:text-base prose-h4:mt-4 prose-h4:mb-2
            prose-headings:font-bold prose-headings:text-foreground
          ">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={markdownComponents}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}, (prevProps, nextProps) => {
  // Only re-render if message content changes
  return prevProps.message.content === nextProps.message.content;
});

export default ComparisonMessage;
