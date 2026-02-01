/**
 * ComparisonCitationLink Component
 *
 * Renders a clickable citation badge that navigates to the correct document and page.
 * Maps [D1:p5] -> Document 1, page 5
 *
 * On click:
 * 1. Switches to the correct PDF document
 * 2. Navigates to the specified page
 * 3. Highlights the page region
 */

import React, { useMemo } from "react";
import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useComparison, useChatActions } from "../../../store";
import { useAuth } from "@clerk/clerk-react";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "../../ui/tooltip";

/**
 * Parse citation token to extract document index and page number
 * [D1:p5] -> { docIndex: 0, page: 5 }
 */
function parseCitation(token) {
  if (!token) return null;
  const match = token.match(/\[D(\d+):p(\d+)\]/);
  if (!match) return null;
  return {
    docIndex: parseInt(match[1], 10) - 1, // D1 -> index 0
    page: parseInt(match[2], 10),
  };
}

export default function ComparisonCitationLink({ token, className, context }) {
  const comparison = useComparison();
  const { highlightChunk, setActivePdfDocument } = useChatActions();
  const { getToken } = useAuth();

  const parsed = parseCitation(token);
  const resolvedContext = context || comparison.context;

  // Fallback if parsing fails or no context
  if (!parsed || !resolvedContext?.documents) {
    return (
      <span
        className={cn(
          "inline-flex items-center mx-0.5 px-1.5 py-0.5 rounded text-xs font-mono",
          "bg-muted text-muted-foreground",
          className
        )}
      >
        {token}
      </span>
    );
  }

  const document = resolvedContext.documents[parsed.docIndex];

  const resolvedChunk = useMemo(() => {
    if (!parsed || !resolvedContext?.documents) return null;

    const pairs = resolvedContext?.paired_chunks || [];
    const clusters = resolvedContext?.clustered_chunks || [];

    // Strategy 1: Exact page match in paired chunks
    for (const pair of pairs) {
      if (parsed.docIndex === 0 && pair.chunk_a?.page === parsed.page) {
        return { bbox: pair.chunk_a?.bbox, text: pair.chunk_a?.text };
      }
      if (parsed.docIndex === 1 && pair.chunk_b?.page === parsed.page) {
        return { bbox: pair.chunk_b?.bbox, text: pair.chunk_b?.text };
      }
    }

    // Strategy 2: Exact page match in clustered chunks
    for (const cluster of clusters) {
      const chunk = cluster.chunks?.[document.id];
      if (chunk?.page === parsed.page) {
        return { bbox: chunk.bbox, text: chunk.text };
      }
    }

    // Strategy 3: Fallback to first chunk for the cited document
    for (const pair of pairs) {
      if (parsed.docIndex === 0 && pair.chunk_a?.bbox) {
        return { bbox: pair.chunk_a?.bbox, text: pair.chunk_a?.text };
      }
      if (parsed.docIndex === 1 && pair.chunk_b?.bbox) {
        return { bbox: pair.chunk_b?.bbox, text: pair.chunk_b?.text };
      }
    }

    return null;
  }, [resolvedContext, parsed, document]);

  // Fallback if document not found
  if (!document) {
    return (
      <span
        className={cn(
          "inline-flex items-center mx-0.5 px-1.5 py-0.5 rounded text-xs font-mono",
          "bg-muted text-muted-foreground",
          className
        )}
      >
        {token}
      </span>
    );
  }

  const handleClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      // First switch to the correct document
      await setActivePdfDocument(document.id, getToken);

      const bbox = resolvedChunk?.bbox || null;

      // Highlight chunk with bbox coordinates (or fall back to full page)
      highlightChunk(
        {
          page: bbox?.page || parsed.page,
          x0: bbox?.x0 ?? 0,
          y0: bbox?.y0 ?? 0,
          x1: bbox?.x1 ?? 1,
          y1: bbox?.y1 ?? 1,
          docId: document.id,
        },
        getToken
      );
    } catch (error) {
      console.error("Failed to navigate to citation:", error);
    }
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={handleClick}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] leading-none",
            "text-muted-foreground bg-background/70 hover:bg-muted/60 hover:text-foreground align-super",
            "transition-colors cursor-pointer animate-chip-fade-in",
            className
          )}
          title={`Page ${parsed.page}`}
        >
          <FileText className="h-3 w-3" />
          <span>p{parsed.page}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" align="start" className="comparison-cite-tooltip">
        <div className="space-y-1">
          <p className="text-xs font-medium text-foreground">
            {document.filename?.split("/").pop() ||
              document.label ||
              `Doc ${parsed.docIndex + 1}`}
          </p>
          <p className="text-[11px] text-muted-foreground">Page {parsed.page}</p>
          {resolvedChunk?.text ? (
            <p className="text-xs text-foreground/90 line-clamp-6">
              {resolvedChunk.text}
            </p>
          ) : (
            <p className="text-xs text-muted-foreground">Click to open.</p>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  );
}
