/**
 * Clickable citation link for general chat messages.
 * Parses [ref:chunk_id:page] and navigates to source with highlighting.
 */
import { FileText } from "lucide-react";
import { useMemo } from "react";
import { useStore } from "../../store";
import { useAuth } from "@clerk/clerk-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "../ui/tooltip";

export default function ChatCitationLink({ token, citationContext }) {
  const { setActivePdfDocument, highlightChunk } = useStore();
  const { getToken } = useAuth();

  // Parse [ref:a1b2c3d4:p5] -> { ref: "a1b2c3d4", page: 5 }
  const parsed = useMemo(() => parseCitation(token), [token]);

  // Build citation map for O(1) lookup (instead of O(n) linear search)
  const citationMap = useMemo(() => {
    if (!citationContext?.citations) return new Map();
    return new Map(citationContext.citations.map((c) => [c.ref, c]));
  }, [citationContext]);

  // Find citation by ref prefix - O(1) lookup
  const citation = useMemo(() => {
    if (!parsed) return null;
    return citationMap.get(parsed.ref) || null;
  }, [parsed, citationMap]);

  if (!parsed || !citation) {
    // Fallback: render as plain text
    return (
      <span className="font-mono text-xs text-muted-foreground">{token}</span>
    );
  }

  const handleClick = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      // Switch to PDF document
      await setActivePdfDocument(citation.document_id, getToken);

      // citation.page is already the physical PDF page (from bbox metadata)
      // Highlight bbox if available, otherwise highlight full page
      const bbox = citation.bbox || {
        page: citation.page,
        x0: 0,
        y0: 0,
        x1: 1,
        y1: 1, // Full page fallback
      };
      highlightChunk(
        {
          ...bbox,
          page: citation.page, // Physical PDF page number from bbox
          docId: citation.document_id,
        },
        getToken
      );
    } catch (error) {
      console.error("Failed to navigate to citation:", error);
    }
  };

  // Truncate filename for inline display
  const displayName =
    citation.filename.length > 15
      ? citation.filename.slice(0, 12) + "..."
      : citation.filename;

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={handleClick}
            className="inline-flex items-center gap-1 mx-0.5 px-1.5 py-0.5
              rounded-full border text-[10px] font-medium
              bg-muted/50 hover:bg-muted text-muted-foreground
              transition-colors cursor-pointer"
          >
            <FileText className="h-3 w-3" />
            <span>
              {displayName}:p{citation.page}
            </span>
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <p className="text-xs font-medium">{citation.filename}</p>
          <p className="text-xs text-muted-foreground">
            Page {citation.page}
            {citation.section && ` • ${citation.section}`}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function parseCitation(token) {
  if (!token) return null;
  // Match [ref:a1b2c3d4:p5]
  const match = token.match(/\[ref:([a-f0-9]+):p(\d+)\]/i);
  if (!match) return null;
  return {
    ref: match[1],
    page: parseInt(match[2], 10),
  };
}
