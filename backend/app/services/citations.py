"""Citation normalization utilities.

Canonical citation format: [D{n}:p{N}]
  - D{n}: document number (1-based), determined by context (session order, workflow array position, etc.)
  - p{N}: physical PDF page number from Azure DI

All LLM outputs should be normalized to this format via normalize_citation_token()
before being stored or returned to the frontend.

Citation resolution (token → bbox/filename/page metadata) is handled in
rag_service._build_citation_context(), which operates on already-retrieved chunks
in memory with a single batch query for document filenames.
"""
from typing import List, Optional
import re


def normalize_citation_token(raw: str, default_doc_index: int = 1) -> Optional[str]:
    """
    Normalize a single LLM-generated citation token to canonical [D{n}:p{N}] format.

    Handles known LLM variants:
      [D1:p15]           → pass through (already canonical)
      [S1:p15]           → [D1:p15]  (source index format used in prompts)
      [p15:table_block]  → [D1:p15]  (page at start, source type at end)
      [Table 7:p15]      → [D1:p15]  (table label with page at end)
      [Source:p15]       → [D1:p15]  (any label with :pN at end)

    Returns None if no page number can be extracted.
    """
    if not raw:
        return None

    # Already canonical: [D{n}:p{N}]
    if re.fullmatch(r'\[D\d+:p\d+\]', raw):
        return raw

    # Source index format used in prompts: [S{n}:p{N}]
    m = re.fullmatch(r'\[S(\d+):p(\d+)\]', raw)
    if m:
        return f'[D{m.group(1)}:p{m.group(2)}]'

    # Page at start: [p15:anything] — e.g. [p15:table_block]
    m = re.match(r'\[p(\d+):', raw)
    if m:
        return f'[D{default_doc_index}:p{m.group(1)}]'

    # Page at end after colon: [anything:p15] — e.g. [Table 7:p15], [Source:p15]
    m = re.search(r':\s*p(\d+)\]', raw)
    if m:
        return f'[D{default_doc_index}:p{m.group(1)}]'

    return None


def normalize_citations(citations: List[str], default_doc_index: int = 1) -> List[str]:
    """
    Normalize a list of LLM-generated citation tokens to canonical [D{n}:p{N}] format.
    Tokens that cannot be parsed are silently dropped.
    """
    result = []
    for c in citations:
        normalized = normalize_citation_token(c, default_doc_index)
        if normalized:
            result.append(normalized)
    return result
