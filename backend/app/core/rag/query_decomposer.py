"""Query Decomposer for RAG.

Detects multi-aspect queries and decomposes them into sub-queries via LLM.
Embeddings for sub-queries are averaged (mean pooling) into a single merged
vector used for one retrieval pass — cheaper than per-sub-query retrieval.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from app.core.rag.query_understanding import QueryUnderstanding
    from app.core.embeddings.base import EmbeddingProvider
    from app.core.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)

_CONJUNCTION_PHRASES = (
    "and also",
    "as well as",
    "additionally",
    "furthermore",
    "in addition",
)

_DECOMPOSITION_SYSTEM_PROMPT = (
    "You are a query decomposer for a financial document retrieval system. "
    "Break the user's query into 2-3 focused retrieval sub-queries. "
    "Each sub-query should be short and target one specific aspect. "
    "Return ONLY a JSON array of strings. No explanation. "
    "If the query is already focused on one thing, return a single-item array."
)


@dataclass
class DecompositionResult:
    sub_queries: List[str]
    merged_embedding: List[float]
    was_decomposed: bool


def is_multi_aspect(
    query: str,
    query_understanding: Optional["QueryUnderstanding"] = None,
) -> bool:
    """Return True if the query is likely multi-aspect and should be decomposed."""
    if query.count("?") > 1:
        return True

    if re.search(r"\b[1-9]\s*[.)]\s*\w", query):
        return True

    query_lower = query.lower()
    if any(phrase in query_lower for phrase in _CONJUNCTION_PHRASES):
        return True

    if len(query) > 300 and query_understanding is not None:
        from app.core.rag.query_understanding import QueryType
        if query_understanding.query_type in (
            QueryType.DATA_EXTRACTION,
            QueryType.COMPARISON,
        ):
            return True

    return False


def merge_embeddings(embeddings: List[List[float]]) -> List[float]:
    """Average a list of embedding vectors (mean pooling)."""
    if len(embeddings) == 1:
        return embeddings[0]
    arr = np.array(embeddings, dtype=float)
    return arr.mean(axis=0).tolist()


async def decompose_and_embed(
    query: str,
    query_understanding: Optional["QueryUnderstanding"],
    embedding_provider: "EmbeddingProvider",
    llm_client: "LLMClient",
) -> DecompositionResult:
    """Decompose query into sub-queries and return merged embedding.

    If query is not multi-aspect, returns a passthrough result with a single
    embedding of the original query and was_decomposed=False.
    """
    if not is_multi_aspect(query, query_understanding):
        # merged_embedding is not consumed by the caller today (retriever takes a query string);
        # skip the embed round-trip to avoid unnecessary latency.
        return DecompositionResult(
            sub_queries=[query],
            merged_embedding=[],
            was_decomposed=False,
        )

    # Attempt LLM decomposition via stream_chat
    try:
        chunks = []
        async for event in llm_client.stream_chat(
            prompt=query,
            system_prompt=_DECOMPOSITION_SYSTEM_PROMPT,
            model_override=llm_client.cheap_model,
        ):
            if isinstance(event, dict) and event.get("type") == "chunk":
                chunks.append(event["text"])
        raw = "".join(chunks)
        sub_queries = json.loads(raw)
        if not isinstance(sub_queries, list) or not sub_queries:
            raise ValueError("LLM returned non-list or empty list")
        sub_queries = [str(q).strip() for q in sub_queries if str(q).strip()]
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse LLM decomposition response: {e}", exc_info=True)
        return DecompositionResult(sub_queries=[query], merged_embedding=[], was_decomposed=False)
    except Exception as e:
        logger.warning(f"LLM decomposition call failed: {e}")
        return DecompositionResult(sub_queries=[query], merged_embedding=[], was_decomposed=False)

    # Single sub-query → passthrough (LLM said the query is already focused)
    if len(sub_queries) == 1:
        return DecompositionResult(
            sub_queries=sub_queries,
            merged_embedding=[],
            was_decomposed=False,
        )

    # Multiple sub-queries → embed each concurrently and average
    embeddings = await asyncio.gather(
        *[asyncio.to_thread(embedding_provider.embed_text, q) for q in sub_queries]
    )
    merged = merge_embeddings(list(embeddings))

    logger.info(
        "Query decomposed",
        extra={"sub_queries": sub_queries, "original": query[:80]},
    )

    return DecompositionResult(
        sub_queries=sub_queries,
        merged_embedding=merged,
        was_decomposed=True,
    )
