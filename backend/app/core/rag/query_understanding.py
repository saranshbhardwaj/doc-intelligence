"""Query Understanding & Enhancement for RAG.

Provides LLM-powered query analysis that:
1. Classifies query intent (comparison, data extraction, general QA, etc.)
2. Extracts entities (documents, metrics, properties, dates, etc.)
3. Reformulates query for better keyword search
4. Generates hypothetical response for HyDE semantic search enhancement
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Primary intent of the user's query."""

    GENERAL_QA = "general_qa"
    COMPARISON = "comparison"
    DATA_EXTRACTION = "data_extraction"
    SUMMARIZATION = "summarization"
    ENTITY_LOOKUP = "entity_lookup"


class ExtractedEntity(BaseModel):
    """An entity extracted from the query."""

    name: str = Field(description="The entity name/identifier")
    entity_type: str = Field(
        description="Type: 'document', 'metric', 'property', 'deal', 'date', 'person', 'organization', 'other'"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence score for this extraction"
    )


class QueryUnderstanding(BaseModel):
    """Comprehensive structured understanding of a user's query."""

    # Core classification
    query_type: QueryType = Field(description="Primary intent of the query")

    # Entity extraction (works across any domain)
    entities: List[ExtractedEntity] = Field(
        default_factory=list,
        description="Extracted entities: documents, metrics, properties, dates, etc.",
    )

    # Query enhancement
    reformulated_query: str = Field(
        description="Cleaned, expanded query optimized for keyword search"
    )

    # HyDE - Hypothetical Document Embeddings
    hypothetical_response: str = Field(
        description="A 2-3 sentence hypothetical answer. Used to enhance semantic search via embeddings."
    )

    # Comparison-specific (populated if query_type == COMPARISON)
    comparison_aspects: List[str] = Field(
        default_factory=list,
        description="Aspects to compare (e.g., 'revenue', 'risks', 'growth')",
    )

    # Data extraction specific (populated if query_type == DATA_EXTRACTION)
    data_fields: List[str] = Field(
        default_factory=list,
        description="Specific data fields requested (e.g., 'cap rate', 'NOI')",
    )

    # Metadata boosting (for retrieval optimization)
    table_boost: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Boost factor for table/structured chunks (0.5-2.0, default 1.0)",
    )
    narrative_boost: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="Boost factor for narrative chunks (0.5-2.0, default 1.0)",
    )

    # Metadata
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in the analysis (0-1)"
    )


class QueryUnderstandingService:
    """LLM-powered query understanding for RAG enhancement.

    Uses cheap/fast model (Haiku) for low latency.
    Results are used to:
    1. Enhance semantic search via HyDE
    2. Improve keyword search via query reformulation
    3. Filter documents via entity extraction
    4. Route to appropriate handler via query type classification
    """

    def __init__(self):
        """Initialize query understanding service."""
        from app.core.llm.llm_client import LLMClient
        from app.config import settings

        self.llm_client = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.synthesis_llm_model,  # Haiku 4.5 - supports structured outputs in beta
            max_tokens=1000,
            max_input_chars=8000,
            timeout_seconds=15,
        )

    async def understand(
        self,
        query: str,
        document_filenames: Optional[List[str]] = None,
        domain_context: str = "financial documents",
    ) -> QueryUnderstanding:
        """Analyze query and return structured understanding.

        Args:
            query: User's raw query string
            document_filenames: Available document names (for context)
            domain_context: Domain hint (e.g., "real estate", "financial")

        Returns:
            QueryUnderstanding with all fields populated
        """

        docs_context = ""
        if document_filenames:
            docs_context = f"\n\nAvailable documents: {', '.join(document_filenames)}"

        system_prompt = f"""You are a query analyzer for {domain_context} RAG system.

Analyze the user's query and provide structured understanding.{docs_context}

INSTRUCTIONS:

1. **query_type**: Classify the primary intent:
   - general_qa: Standard Q&A about document content
   - comparison: Compare/contrast multiple documents or entities
   - data_extraction: Get specific numbers, metrics, data points
   - summarization: Summarize a document or section
   - entity_lookup: Find information about a specific entity

2. **entities**: Extract ALL meaningful entities:
   - Documents (e.g., "Q3 report", "2024 financials")
   - Metrics (e.g., "revenue", "cap rate", "NOI")
   - Properties/Deals (e.g., "Property A", "Deal 123")
   - Dates/Periods (e.g., "Q3 2024", "fiscal year")
   - Organizations (e.g., "NVIDIA", "Acme Corp")
   - Use SHORT identifiers that could match filenames

3. **reformulated_query**: Rewrite for better keyword matching:
   - Expand abbreviations
   - Add synonyms
   - Remove filler words
   - Keep domain-specific terms

4. **hypothetical_response**: Write 2-3 sentences that WOULD answer this query.
   This is used for semantic search - imagine what a good answer looks like.
   Include specific terms and concepts that would appear in relevant documents.

5. **comparison_aspects**: If comparison, list what to compare

6. **data_fields**: If data extraction, list specific fields requested

7. **table_boost** and **narrative_boost**: Set retrieval boosting (0.5-2.0, default 1.0):
   - Data queries (numbers, metrics): table_boost=1.2, narrative_boost=0.9
   - Narrative queries (explanations, summaries): table_boost=1.0, narrative_boost=1.1
   - General queries: both=1.0

Be concise and accurate. Focus on extraction, not explanation."""

        try:
            result = await self.llm_client.extract_structured_data_with_schema(
                text=query,
                system_prompt=system_prompt,
                pydantic_model=QueryUnderstanding,
                use_cache=True,
            )

            understanding = QueryUnderstanding(**result["data"])

            logger.info(
                "Query understanding complete",
                extra={
                    "query": query[:50],
                    "query_type": understanding.query_type.value,
                    "entities": [e.name for e in understanding.entities],
                    "confidence": understanding.confidence,
                },
            )

            return understanding

        except Exception as e:
            logger.warning(f"Query understanding failed, using fallback: {e}")
            # Return minimal fallback
            return QueryUnderstanding(
                query_type=QueryType.GENERAL_QA,
                entities=[],
                reformulated_query=query,
                hypothetical_response=f"The answer to '{query}' would include relevant information from the documents.",
                confidence=0.3,
            )
