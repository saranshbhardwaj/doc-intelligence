"""
Structured retrieval query that separates semantic intent from lexical constraints.

Replaces the raw `query: str` approach in HybridRetriever to fix the BM25 OR-query
dilution bug where synonym-enriched tokens (doc names, stop words) caused every chunk
in a scoped document to match, burying the exact fact the user requested.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.rag.query_understanding import QueryUnderstanding


@dataclass(frozen=True)
class RetrievalQuery:
    """
    Structured representation of a retrieval query.

    semantic_text:    Used verbatim for vector embedding (and HyDE).
    lexical_required: Phrases that MUST appear adjacent in matching chunks.
                      Each entry is passed to phraseto_tsquery and AND'd together
                      as the WHERE filter. Empty → no phrase filter.
                      Reserved for single-fact lookups where all requested evidence
                      should live in the same chunk.
    lexical_optional: Terms that SHOULD appear. OR'd together via plainto_tsquery
                      or phraseto_tsquery and combined with required phrases for
                      ts_rank_cd scoring. Does NOT filter — only influences ranking.
    """

    semantic_text: str
    lexical_required: List[str] = field(default_factory=list)
    lexical_optional: List[str] = field(default_factory=list)

    @classmethod
    def from_query_understanding(
        cls,
        understanding: QueryUnderstanding,
        semantic_text: str,
        doc_filenames: Optional[List[str]] = None,
    ) -> RetrievalQuery:
        """
        Build a structured RetrievalQuery from a QueryUnderstanding object.

        For narrow fact lookups (data_extraction with a specific target):
                    - single-field lookup: lexical_required = data_fields (exact phrases, AND-filtered)
                    - multi-field lookup: lexical_required = [] so fields from different chunks
                        are not filtered out; exact phrases move into lexical_optional instead
          - lexical_optional = filtered synonyms (OR-scored recall boost)

        For broad queries:
          - lexical_required = [] (no phrase filter)
          - lexical_optional = semantic_text tokens excluding doc-name noise
        """
        from app.core.rag.query_understanding import is_narrow_explicit_fact_lookup

        # Build token set to suppress from BM25 — property/doc names appear in
        # headers/footers of every chunk and drown out the actual fact terms.
        excluded: set[str] = set()
        for name in (getattr(understanding, "target_property_names", None) or []):
            excluded.update(_tokenize(name))
        for fname in (doc_filenames or []):
            stem = re.sub(r"\.\w+$", "", fname)
            excluded.update(_tokenize(stem))
        # Keep only substantive tokens (length > 2)
        excluded = {t for t in excluded if len(t) > 2}
        identifier_entities = _identifier_like_entities(understanding)

        if is_narrow_explicit_fact_lookup(understanding):
            required = [f for f in (understanding.data_fields or []) if f.strip()]
            date_terms = [
                getattr(entity, "name", "").strip()
                for entity in (getattr(understanding, "entities", []) or [])
                if getattr(entity, "entity_type", "") == "date"
                and getattr(entity, "name", "").strip()
            ]
            has_date_constraint = bool(date_terms)

            required_lower = {r.lower() for r in required}
            if len(required) <= 1:
                if has_date_constraint:
                    optional_candidates = list(required) + identifier_entities + date_terms + [
                        s for s in (understanding.data_field_synonyms or [])
                        if s.lower() not in required_lower and s.strip()
                    ]
                    optional = list(dict.fromkeys(optional_candidates))
                    lexical_required = []
                else:
                    semantic_lower = semantic_text.lower()
                    optional_candidates = identifier_entities + [
                        s for s in (understanding.data_field_synonyms or [])
                        if s.lower() not in semantic_lower
                        and s.lower() not in required_lower
                        and s.strip()
                    ]
                    optional = list(dict.fromkeys(optional_candidates))
                    lexical_required = required
            else:
                optional_candidates = list(required) + identifier_entities + date_terms + [
                    s for s in (understanding.data_field_synonyms or [])
                    if s.lower() not in required_lower and s.strip()
                ]
                optional = list(dict.fromkeys(optional_candidates))
                lexical_required = []

            return cls(
                semantic_text=semantic_text,
                lexical_required=lexical_required,
                lexical_optional=optional,
            )
        else:
            # Broad query: no required filter. Use semantic_text tokens as optional
            # recall hints, but strip out doc-name tokens to avoid false matches.
            optional = [
                t for t in _tokenize(semantic_text)
                if t not in excluded and len(t) > 2
            ]
            return cls(
                semantic_text=semantic_text,
                lexical_required=[],
                lexical_optional=optional,
            )

    @classmethod
    def from_text(cls, text: str) -> RetrievalQuery:
        """
        Simple factory for callers without a QueryUnderstanding (workflow retriever,
        comparison retriever when QU is unavailable). Produces a basic query with
        no phrase filtering — equivalent to the previous plainto_tsquery behavior.
        """
        return cls(semantic_text=text)


def _tokenize(text: str) -> List[str]:
    """Split text into lowercase alphanumeric tokens."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _identifier_like_entities(understanding: QueryUnderstanding) -> List[str]:
    target_names = {
        name.strip().lower()
        for name in (getattr(understanding, "target_property_names", None) or [])
        if isinstance(name, str) and name.strip()
    }
    data_fields = {
        field.strip().lower()
        for field in (getattr(understanding, "data_fields", None) or [])
        if isinstance(field, str) and field.strip()
    }

    identifiers: List[str] = []
    for entity in (getattr(understanding, "entities", None) or []):
        name = getattr(entity, "name", "")
        normalized = name.strip().lower()
        if not normalized:
            continue
        if normalized in target_names or normalized in data_fields:
            continue
        if any(ch.isdigit() for ch in normalized):
            identifiers.append(name.strip())

    return list(dict.fromkeys(identifiers))
