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

/** Regex that matches canonical [D1:p5] and legacy [ref:hex:pN] citation tokens. */
export const CITATION_REGEX = /\[D\d+:p\d+\]|\[ref:[a-f0-9]+:p\d+\]/g;

/**
 * Parse a single citation token to structured data.
 *
 * Handles:
 *   [D1:p5]              → { docIndex: 0, page: 5 }  (canonical)
 *   [ref:a1b2c3d4:p5]    → { docIndex: 0, page: 5 }  (legacy chat format — page only, assume D1)
 *
 * Returns null if the token cannot be parsed.
 *
 * @param {string} token
 * @returns {{ docIndex: number, page: number } | null}
 */
export function parseCitation(token) {
  if (!token) return null;

  // Canonical: [D{n}:p{N}]
  const m = token.match(/\[D(\d+):p(\d+)\]/);
  if (m) {
    return { docIndex: parseInt(m[1], 10) - 1, page: parseInt(m[2], 10) };
  }

  // Legacy: [ref:{hex8}:p{N}] — old chat format stored in DB before migration
  // We can only recover the page; document is assumed to be D1 (index 0).
  const leg = token.match(/\[ref:[a-f0-9]+:p(\d+)\]/i);
  if (leg) {
    return { docIndex: 0, page: parseInt(leg[1], 10) };
  }

  return null;
}

/**
 * Build an O(1) lookup map from a citation context object.
 *
 * citationContext shape (from backend SSE event):
 *   {
 *     citations: [{ doc_index, page, chunk_id, document_id, filename, section, bbox }, ...],
 *     document_index: { "D1": "doc-uuid-A", "D2": "doc-uuid-B" },
 *     document_map: { "doc-uuid": "filename.pdf" }
 *   }
 *
 * Returns a Map keyed by "D{n}:p{N}" → citation metadata object.
 *
 * @param {object} citationContext
 * @returns {Map<string, object>}
 */
export function buildCitationLookup(citationContext) {
  if (!citationContext?.citations) return new Map();

  const map = new Map();
  for (const c of citationContext.citations) {
    const key = `D${c.doc_index}:p${c.page}`;
    if (!map.has(key)) {
      map.set(key, c);
    }
  }
  return map;
}

/**
 * Resolve a parsed citation to rich metadata using a citation lookup map.
 *
 * @param {{ docIndex: number, page: number }} parsed  - Output of parseCitation()
 * @param {Map<string, object>} lookupMap              - Output of buildCitationLookup()
 * @returns {object | null}  Citation metadata or null if not found
 */
export function resolveCitation(parsed, lookupMap) {
  if (!parsed || !lookupMap) return null;
  const key = `D${parsed.docIndex + 1}:p${parsed.page}`;
  return lookupMap.get(key) || null;
}

/**
 * Split text into an array of plain strings and parsed citation objects.
 * Used to render citation tokens as interactive components inside prose.
 *
 * Example:
 *   "Revenue grew 15% [D1:p5] vs prior year [D2:p3]."
 *   → ["Revenue grew 15% ", { token: "[D1:p5]", docIndex: 0, page: 5 },
 *       " vs prior year ", { token: "[D2:p3]", docIndex: 1, page: 3 }, "."]
 *
 * @param {string} text
 * @returns {Array<string | { token: string, docIndex: number, page: number }>}
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
