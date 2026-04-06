/**
 * Shared citation utilities — canonical format: [Dn:pN]
 *
 * All LLM responses across chat, PE workflows, and RE template fill use the
 * same [Dn:pN] format where n is the 1-based document index and N is the
 * physical PDF page number.
 *
 * The citation context object (sent as a side-channel SSE event or stored with
 * the field mapping) carries the document_index that resolves Dn → document_id.
 */

/** Regex that matches canonical [S1:p5] and legacy [ref:hex:pN] citation tokens. */
export const CITATION_REGEX = /\[S\d+:p\d+\]|\[ref:[a-f0-9]+:p\d+\]/g;

/**
 * Remark plugin that converts [Dn:pN] citation tokens into custom `citation`
 * mdast nodes BEFORE remark-gfm runs its link-reference pass.
 *
 * This prevents remark-gfm from misinterpreting [D2:p6] as a GFM shortcut
 * link reference (which strips the brackets and makes the token undetectable
 * by later string-based citation processing).
 *
 * The plugin visits every `text` node in the mdast tree, finds citation tokens,
 * and replaces them with an inline sequence of plain `text` nodes and `citation`
 * nodes. react-markdown renders `citation` nodes via a custom component.
 *
 * Usage:
 *   import { remarkCitations } from "@/utils/citations";
 *   <ReactMarkdown remarkPlugins={[remarkGfm, remarkCitations]} components={{ citation: CitationNode }} />
 *
 * Note: must be listed AFTER remarkGfm so it runs on the already-parsed tree,
 * but citation nodes are injected before remark-gfm's link-reference resolution
 * happens (remarkGfm only parses, it doesn't resolve references at AST time).
 * Actually: list it BEFORE remarkGfm so citations are extracted first.
 */
export function remarkCitations() {
  return (tree) => {
    // Dynamic import to avoid bundling issues — visit is an ESM-only package
    // We use a synchronous tree walk instead.
    visitTextNodes(tree);
  };
}

function visitTextNodes(node) {
  if (!node) return;

  if (node.type === "text" && node.value) {
    const regex = new RegExp(CITATION_REGEX.source, "g");
    if (!regex.test(node.value)) return; // fast path — no citations

    // Replace this text node with a sequence of text + citation nodes
    // by mutating the parent's children array.
    // We do this by marking it for replacement and returning the new nodes.
    node.__citationExpand = true;
    return;
  }

  if (Array.isArray(node.children)) {
    const newChildren = [];
    for (const child of node.children) {
      visitTextNodes(child);
      if (child.__citationExpand) {
        newChildren.push(...expandTextNode(child));
      } else {
        newChildren.push(child);
      }
    }
    node.children = newChildren;
  }
}

function expandTextNode(textNode) {
  const text = textNode.value;
  const regex = new RegExp(CITATION_REGEX.source, "g");
  const nodes = [];
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push({ type: "text", value: text.slice(lastIndex, match.index) });
    }
    nodes.push({
      type: "citation",
      value: match[0],
      data: { hName: "citation", hProperties: { token: match[0] } },
    });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    nodes.push({ type: "text", value: text.slice(lastIndex) });
  }

  return nodes;
}

/**
 * Parse a single citation token to structured data.
 *
 * Handles:
 *   [S1:p5]              → { sourceIndex: 0, page: 5 }  (canonical, 1-based → 0-based)
 *   [ref:a1b2c3d4:p5]    → { sourceIndex: 0, page: 5 }  (legacy chat format — page only, assume S1)
 *
 * Returns null if the token cannot be parsed.
 *
 * @param {string} token
 * @returns {{ sourceIndex: number, page: number } | null}
 */
export function parseCitation(token) {
  if (!token) return null;

  // Canonical: [S{n}:p{N}]
  const m = token.match(/\[S(\d+):p(\d+)\]/);
  if (m) {
    return { sourceIndex: parseInt(m[1], 10) - 1, page: parseInt(m[2], 10) };
  }

  // Legacy: [ref:{hex8}:p{N}] — old chat format stored in DB before migration
  // We can only recover the page; source is assumed to be S1 (index 0).
  const leg = token.match(/\[ref:[a-f0-9]+:p(\d+)\]/i);
  if (leg) {
    return { sourceIndex: 0, page: parseInt(leg[1], 10) };
  }

  return null;
}

/**
 * Build an O(1) lookup map from a citation context object.
 *
 * citationContext shape (from backend SSE event):
 *   {
 *     citations: [{ source_index, page, chunk_id, document_id, filename, section, bbox }, ...],
 *     document_map: { "doc-uuid": "filename.pdf" }
 *   }
 *
 * Returns a Map keyed by "S{n}:p{N}" → citation metadata object.
 *
 * @param {object} citationContext
 * @returns {Map<string, object>}
 */
export function buildCitationLookup(citationContext) {
  if (!citationContext?.citations) return new Map();

  const map = new Map();
  for (const c of citationContext.citations) {
    const key = `S${c.source_index}:p${c.page}`;
    if (!map.has(key)) {
      map.set(key, c);
    }
  }
  return map;
}

/**
 * Resolve a parsed citation to rich metadata using a citation lookup map.
 *
 * @param {{ sourceIndex: number, page: number }} parsed  - Output of parseCitation()
 * @param {Map<string, object>} lookupMap                - Output of buildCitationLookup()
 * @returns {object | null}  Citation metadata or null if not found
 */
export function resolveCitation(parsed, lookupMap) {
  if (!parsed || !lookupMap) return null;
  const key = `S${parsed.sourceIndex + 1}:p${parsed.page}`;
  return lookupMap.get(key) || null;
}

/**
 * Split text into an array of plain strings and parsed citation objects.
 * Used to render citation tokens as interactive components inside prose.
 *
 * Example:
 *   "Revenue grew 15% [S1:p5] vs prior year [S2:p3]."
 *   → ["Revenue grew 15% ", { token: "[S1:p5]", sourceIndex: 0, page: 5 },
 *       " vs prior year ", { token: "[S2:p3]", sourceIndex: 1, page: 3 }, "."]
 *
 * @param {string} text
 * @returns {Array<string | { token: string, sourceIndex: number, page: number }>}
 */
export function splitTextWithCitations(text) {
  if (!text) return [text];

  const parts = [];
  const regex = new RegExp(CITATION_REGEX.source, 'g');
  let lastIndex = 0;
  let match;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const parsed = parseCitation(match[0]);
    if (parsed) {
      parts.push({ token: match[0], ...parsed });
    } else {
      parts.push(match[0]);
    }
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts.length > 0 ? parts : [text];
}
