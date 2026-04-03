"""
Fact Extractor: Extracts query-relevant facts from document chunks.

This module implements the "Map" step of a Map-Reduce pattern for comparison queries.
Instead of sending raw chunks to the LLM, we extract structured facts per document,
then feed only the facts to the synthesis step.

This approach:
- Reduces noise in LLM input
- Improves accuracy on multi-document comparisons
- Enables better citation tracking
- Handles poorly formatted documents more robustly
"""

import logging
from typing import List, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.core.llm.llm_client import LLMClient

logger = logging.getLogger(__name__)



class ExtractedFact(BaseModel):
    """A fact extracted from document chunks."""

    fact: str = Field(description="The extracted fact statement")
    source_chunk_id: str = Field(description="ID of the chunk this came from")
    source_page: int = Field(description="Page number for citation")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the extraction")
    source_chunk_index: int = Field(default=1, description="Sequential position of source chunk in flattened chunks list (1-based, for [Sn:pN] citations)")


class DocumentFacts(BaseModel):
    """Facts extracted from a single document."""

    document_id: str = Field(description="ID of the document")
    document_name: str = Field(description="Filename of the document")
    facts: List[ExtractedFact] = Field(default_factory=list, description="Extracted facts")


class FactExtractor:
    """
    Extracts query-relevant facts from document chunks using Haiku.

    The extraction process:
    1. Takes top-K retrieved chunks for a document
    2. Asks Haiku to extract facts relevant to the user's query and comparison aspects
    3. Returns structured facts with citations (chunk_id, page_number)

    This reduces the LLM's input from raw, noisy chunks to clean, focused facts.
    """

    def __init__(self, prompt_version: str | None = None):
        from app.core.llm.llm_client import LLMClient
        from app.config import settings
        from app.core.rag.prompts import get_rag_prompt_set

        self.llm_client: "LLMClient" = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.synthesis_llm_model,  # Haiku for speed
            max_input_chars=15000,
            max_tokens=8000,  # Sufficient for full 20-chunk candidate pool
            timeout_seconds=60  # Increased to match larger output budget
        )
        self._prompts = get_rag_prompt_set(prompt_version)

    async def extract_facts(
        self,
        chunks: List[dict],
        query: str,
        comparison_aspects: List[str],
        document_name: str,
        document_id: str
    ) -> DocumentFacts:
        """
        Extract query-relevant facts from chunks.

        Args:
            chunks: Document chunks to extract from (should be ranked)
            query: User's original query
            comparison_aspects: Specific aspects to focus on (from QueryUnderstanding)
                               Empty list means extract "key information"
            document_name: Document filename for context
            document_id: Document ID for citation

        Returns:
            DocumentFacts with extracted facts and citations
        """
        # Build a mapping of chunk_id → source_chunk_index (1-based position in chunks list)
        # This will be used to augment extracted facts with citation indices.
        chunk_id_to_index = {}
        chunk_context = ""
        for idx, chunk in enumerate(chunks, 1):
            chunk_id = chunk.get('id', 'unknown')
            chunk_id_to_index[chunk_id] = idx

            metadata = chunk.get('chunk_metadata') or {}
            paragraph_pages = metadata.get('paragraph_pages')
            if paragraph_pages:
                first_page = paragraph_pages[0].get('page')
                last_page = paragraph_pages[-1].get('page')
                page = f"{first_page}-{last_page}" if last_page != first_page else first_page
            else:
                bbox = metadata.get('bbox', {})
                page = (bbox.get('page') if isinstance(bbox, dict) and bbox else None) or chunk.get('page_number', '?')
            text = chunk.get('text', '')
            chunk_context += f"\n[Chunk {chunk_id}, Page {page}]:\n{text}\n"

        aspects_str = (
            ", ".join(comparison_aspects)
            if comparison_aspects
            else "key information"
        )

        system_prompt = self._prompts.build_fact_extractor_system_prompt(
            document_name=document_name,
            query=query,
            aspects_str=aspects_str,
            chunk_context=chunk_context,
        )

        try:
            result = await self.llm_client.extract_structured_data_with_schema(
                text=f"Query: {query}\nAspects: {aspects_str}",
                system_prompt=system_prompt,
                pydantic_model=DocumentFacts,
                use_cache=False  # Don't cache - context specific to this document
            )

            # Augment extracted facts with source_chunk_index
            extracted_fact_dicts = result.get("data", {}).get("facts", [])
            augmented_facts = []
            for f in extracted_fact_dicts:
                # Look up the source_chunk_id in our mapping to get the 1-based index
                source_chunk_id = f.get("source_chunk_id", "unknown")
                source_chunk_index = chunk_id_to_index.get(source_chunk_id, 1)
                # Add source_chunk_index to the fact data
                f["source_chunk_index"] = source_chunk_index
                augmented_facts.append(ExtractedFact(**f))

            facts = DocumentFacts(
                document_id=document_id,
                document_name=document_name,
                facts=augmented_facts
            )

            logger.info(
                f"Fact extraction complete for {document_name}",
                extra={
                    "document_id": document_id,
                    "fact_count": len(facts.facts),
                    "query_length": len(query),
                    "aspects": len(comparison_aspects)
                }
            )

            return facts

        except Exception as e:
            logger.warning(
                f"Fact extraction failed for {document_name}: {e}",
                extra={"document_id": document_id}
            )
            # Fallback: return empty facts (caller will use raw chunks)
            return DocumentFacts(
                document_id=document_id,
                document_name=document_name,
                facts=[]
            )
