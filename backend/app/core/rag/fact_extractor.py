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

    def __init__(self):
        from app.core.llm.llm_client import LLMClient
        from app.config import settings

        self.llm_client: "LLMClient" = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.synthesis_llm_model,  # Haiku for speed
            max_input_chars=15000,
            max_tokens=4000,  # Increased for multi-chunk fact extraction
            timeout_seconds=30  # Increased timeout for longer responses
        )

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
        # Build chunk context with IDs for citation
        chunk_context = ""
        for chunk in chunks:
            chunk_id = chunk.get('id', 'unknown')
            page = chunk.get('page_number', '?')
            text = chunk.get('text', '')
            chunk_context += f"\n[Chunk {chunk_id}, Page {page}]:\n{text}\n"

        aspects_str = (
            ", ".join(comparison_aspects)
            if comparison_aspects
            else "key information"
        )

        system_prompt = f"""You are extracting facts from document chunks for comparison analysis.

DOCUMENT: {document_name}
USER QUERY: {query}
FOCUS ON: {aspects_str}

INSTRUCTIONS:
1. Extract ALL facts relevant to the query and comparison aspects
2. Each fact should be a single, specific statement
3. Include the chunk_id and page number for each fact
4. Focus on numbers, metrics, dates, and specific claims
5. Be concise - bullet points, not paragraphs
6. If a fact appears in multiple chunks, cite the most authoritative source

OUTPUT FORMAT (JSON):
{{
  "document_id": "{document_id}",
  "document_name": "{document_name}",
  "facts": [
    {{"fact": "Cap rate is 6.2%", "source_chunk_id": "chunk_123", "source_page": 5, "confidence": 0.95}},
    {{"fact": "NOI is $1.2M annually", "source_chunk_id": "chunk_124", "source_page": 5, "confidence": 0.9}}
  ]
}}

Extract facts from these chunks:
{chunk_context}"""

        try:
            result = await self.llm_client.extract_structured_data_with_schema(
                text=f"Query: {query}\nAspects: {aspects_str}",
                system_prompt=system_prompt,
                pydantic_model=DocumentFacts,
                use_cache=False  # Don't cache - context specific to this document
            )

            facts = DocumentFacts(
                document_id=document_id,
                document_name=document_name,
                facts=[
                    ExtractedFact(**f)
                    for f in result.get("data", {}).get("facts", [])
                ]
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
