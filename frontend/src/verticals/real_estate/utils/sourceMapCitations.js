function parseCitationPage(citation) {
  if (!citation) return null;
  const match = String(citation).match(/\[(?:S|D)\d+:p(\d+)\]/i);
  if (!match?.[1]) return null;
  const page = Number.parseInt(match[1], 10);
  return Number.isFinite(page) && page > 0 ? page : null;
}

export function groupSourceMapCitationsByPage(citations = []) {
  const grouped = new Map();

  for (const citation of Array.isArray(citations) ? citations : [citations]) {
    const page = parseCitationPage(citation);
    const key = page ?? String(citation);

    if (!grouped.has(key)) {
      grouped.set(key, {
        page,
        citations: [],
      });
    }

    grouped.get(key).citations.push(citation);
  }

  return Array.from(grouped.values()).map(({ page, citations: pageCitations }) => ({
    page,
    citations: pageCitations,
    primaryCitation: pageCitations[0],
    label: page != null && pageCitations.length > 1
      ? `Page ${page} · ${pageCitations.length} citations`
      : page != null
        ? `Page ${page}`
        : String(pageCitations[0]),
  }));
}
