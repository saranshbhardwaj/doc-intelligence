/**
 * Unified citation link component — canonical format: [Dn:pN]
 *
 * Replaces:
 *   - ChatCitationLink       (general chat inline citations)
 *   - ComparisonCitationLink (PE comparison inline citations)
 *   - CitationBadge          (RE template fill field badges)
 *
 * Props:
 *   token             {string}   Citation token e.g. "[D1:p5]"
 *   citationContext   {object}   General chat citation context (SSE event payload)
 *   comparisonContext {object}   PE comparison context (comparison_context store value)
 *   onCitationClick   {function} RE template fill: called with bbox object or page number
 *   bbox              {object}   Optional bbox for RE fill: { page, x0, y0, x1, y1 }
 *   variant           {string}   "inline" (default) | "badge"
 *   className         {string}
 */

import React, { useMemo } from "react";
import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAppAuth } from "@/hooks/useAppAuth";
import { useChatActions } from "@/store";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";
import {
  parseCitation,
  buildCitationLookup,
  resolveCitation,
} from "@/utils/citations";

// ---------------------------------------------------------------------------
// Comparison chunk resolution (mirrors ComparisonCitationLink chunk lookup)
// ---------------------------------------------------------------------------
function resolveComparisonChunk(resolvedContext, parsed, document) {
  if (!parsed || !resolvedContext) return null;
  const pairs = resolvedContext.paired_chunks || [];
  const clusters = resolvedContext.clustered_chunks || [];

  for (const pair of pairs) {
    if (parsed.docIndex === 0 && pair.chunk_a?.page === parsed.page)
      return { bbox: pair.chunk_a?.bbox, text: pair.chunk_a?.text };
    if (parsed.docIndex === 1 && pair.chunk_b?.page === parsed.page)
      return { bbox: pair.chunk_b?.bbox, text: pair.chunk_b?.text };
  }
  for (const cluster of clusters) {
    const chunk = cluster.chunks?.[document?.id];
    if (chunk?.page === parsed.page) return { bbox: chunk.bbox, text: chunk.text };
  }
  for (const pair of pairs) {
    if (parsed.docIndex === 0 && pair.chunk_a?.bbox)
      return { bbox: pair.chunk_a?.bbox, text: pair.chunk_a?.text };
    if (parsed.docIndex === 1 && pair.chunk_b?.bbox)
      return { bbox: pair.chunk_b?.bbox, text: pair.chunk_b?.text };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------
export default function CitationLink({
  token,
  citationContext,
  comparisonContext,
  onCitationClick,
  bbox: externalBbox = null,
  variant = "inline",
  className,
}) {
  const { getToken } = useAppAuth();
  const { setActivePdfDocument, highlightChunk } = useChatActions();

  const parsed = useMemo(() => parseCitation(token), [token]);

  // General chat resolution
  const citationLookup = useMemo(
    () => buildCitationLookup(citationContext),
    [citationContext]
  );
  const chatCitation = useMemo(
    () => (citationContext ? resolveCitation(parsed, citationLookup) : null),
    [parsed, citationContext, citationLookup]
  );

  // Comparison resolution
  const comparisonDocument = useMemo(() => {
    if (!comparisonContext?.documents || !parsed) return null;
    return comparisonContext.documents[parsed.docIndex] || null;
  }, [comparisonContext, parsed]);

  const comparisonChunk = useMemo(
    () => resolveComparisonChunk(comparisonContext, parsed, comparisonDocument),
    [comparisonContext, parsed, comparisonDocument]
  );

  const canNavigate =
    parsed !== null &&
    (chatCitation !== null ||
      comparisonDocument !== null ||
      onCitationClick !== undefined);

  // Unresolvable inline token — plain monospace fallback
  if (!parsed || (!canNavigate && variant === "inline")) {
    return (
      <span className="font-mono text-xs text-muted-foreground">{token}</span>
    );
  }

  // -------------------------------------------------------------------
  // Click handler
  // -------------------------------------------------------------------
  const handleClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();

    // RE template fill: parent owns navigation
    if (onCitationClick && !chatCitation && !comparisonDocument) {
      if (externalBbox?.page) {
        onCitationClick({ ...externalBbox, page: Number(externalBbox.page) });
      } else {
        onCitationClick(parsed.page);
      }
      return;
    }

    try {
      if (comparisonDocument) {
        await setActivePdfDocument(comparisonDocument.id, getToken);
        const bbox = comparisonChunk?.bbox || null;
        highlightChunk(
          {
            page: bbox?.page || parsed.page,
            x0: bbox?.x0 ?? 0,
            y0: bbox?.y0 ?? 0,
            x1: bbox?.x1 ?? 1,
            y1: bbox?.y1 ?? 1,
            docId: comparisonDocument.id,
          },
          getToken
        );
        return;
      }

      if (chatCitation) {
        await setActivePdfDocument(chatCitation.document_id, getToken);
        const bbox = chatCitation.bbox || {
          page: chatCitation.page,
          x0: 0, y0: 0, x1: 1, y1: 1,
        };
        highlightChunk(
          { ...bbox, page: chatCitation.page, docId: chatCitation.document_id },
          getToken
        );
      }
    } catch (err) {
      console.error("CitationLink navigation failed:", err);
    }
  };

  // -------------------------------------------------------------------
  // Display values
  // -------------------------------------------------------------------
  const filename =
    chatCitation?.filename ||
    comparisonDocument?.filename?.split("/").pop() ||
    comparisonDocument?.label ||
    `Doc ${(parsed.docIndex || 0) + 1}`;

  const section = chatCitation?.section || null;
  const snippetText = comparisonChunk?.text || null;
  const page = parsed.page;

  const tooltipBody = (
    <div className="space-y-1">
      <p className="text-xs font-medium text-foreground">{filename}</p>
      <p className="text-[11px] text-muted-foreground">
        Page {page}
        {section ? ` • ${section}` : ""}
      </p>
      {snippetText && (
        <p className="text-xs text-foreground/90 line-clamp-6">{snippetText}</p>
      )}
    </div>
  );

  // -------------------------------------------------------------------
  // Badge variant (RE template fill field cards)
  // -------------------------------------------------------------------
  if (variant === "badge") {
    const effectivePage = externalBbox?.page ? Number(externalBbox.page) : page;

    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={canNavigate ? handleClick : undefined}
              disabled={!canNavigate}
              className={cn(
                "inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium",
                "bg-muted text-muted-foreground border border-border",
                "transition-all duration-200 animate-chip-fade-in",
                canNavigate &&
                  "hover:bg-accent hover:text-accent-foreground cursor-pointer",
                !canNavigate && "cursor-default",
                className
              )}
            >
              <FileText className="h-3 w-3" />
              <span>Page {effectivePage}</span>
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            {tooltipBody}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // -------------------------------------------------------------------
  // Inline variant (chat / comparison text)
  // -------------------------------------------------------------------
  const displayName =
    filename.length > 15 ? filename.slice(0, 12) + "..." : filename;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={handleClick}
            className={cn(
              "inline-flex items-center gap-1 mx-0.5 rounded-full border px-1.5 py-0.5",
              "text-[10px] font-bold leading-none align-super",
              "text-primary bg-primary/10 border-primary/20",
              "hover:bg-primary hover:text-primary-foreground",
              "transition-colors cursor-pointer animate-chip-fade-in",
              className
            )}
          >
            <FileText className="h-3 w-3" />
            <span>
              {displayName}:p{page}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          {tooltipBody}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
