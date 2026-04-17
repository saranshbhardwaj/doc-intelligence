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

class ScopeMode(str, Enum):
    """Routing scope mode inferred from the query."""

    SINGLE_DOC = "single_doc"
    MULTI_DOC = "multi_doc"
    AMBIGUOUS = "ambiguous"
    GLOBAL = "global"

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
        description="Specific data fields requested (e.g., 'cap rate', 'NOI'). Keep tight — 1-3 items, one per distinct concept the user asked for.",
    )
    data_field_synonyms: List[str] = Field(
        default_factory=list,
        description="Flat list of all synonym/alternative phrasings for data_fields. Used for BM25 keyword recall. E.g. for 'asking price': ['asking price', 'offering price', 'listing price', 'purchase price', 'sale price'].",
    )

    # Incremental scope routing fields (added in small steps for stability testing)
    scope_mode: ScopeMode = Field(
        default=ScopeMode.AMBIGUOUS,
        description="Retrieval scope mode: single_doc, multi_doc, ambiguous, or global",
    )
    target_property_names: List[str] = Field(
        default_factory=list,
        description="Property/deal names explicitly targeted by the query",
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

    # Conversation dependency
    needs_history: bool = Field(
        default=False,
        description="True only if the query references prior conversation context "
                    "(pronouns 'it/that/those/the one', follow-ups 'what about/also/and the', "
                    "or explicit back-references 'you mentioned/earlier/previously'). "
                    "False for self-contained questions that can be answered without prior context."
    )

    # Rewritten query for follow-ups (populated only when needs_history=True)
    rewritten_query: Optional[str] = Field(
        default=None,
        description="Self-contained rewrite of the query using conversation context. "
                    "Populated when needs_history=True and recent_messages are provided. "
                    "Used for retrieval; original query still appears in USER QUESTION."
    )

    # Metadata
    confidence: float = Field(
        ge=0.0, le=1.0, description="Overall confidence in the analysis (0-1)"
    )


def is_narrow_explicit_fact_lookup(query_understanding: Optional["QueryUnderstanding"]) -> bool:
    """Return True for narrow fact lookups that should avoid broad retrieval behaviors."""
    if not query_understanding:
        return False

    if query_understanding.query_type != QueryType.DATA_EXTRACTION:
        return False

    data_fields = [
        field.strip().lower()
        for field in (getattr(query_understanding, "data_fields", []) or [])
        if isinstance(field, str) and field.strip()
    ]
    entities = list(getattr(query_understanding, "entities", []) or [])
    confidence = getattr(query_understanding, "confidence", 0.0) or 0.0

    has_specific_target = any(
        getattr(entity, "name", "").strip()
        and getattr(entity, "entity_type", "") in {
            "document",
            "property",
            "deal",
            "organization",
            "person",
            "other",
        }
        for entity in entities
    )

    if not has_specific_target:
        return False

    metric_like_fields = {
        "price", "asking price", "purchase price", "valuation", "value",
        "noi", "cap rate", "irr", "equity multiple", "rent", "occupancy",
        "yield", "leverage", "loan", "interest rate", "expense", "revenue",
        "cash flow",
    }

    # Strong signal when LLM returns a compact explicit field list.
    if 1 <= len(data_fields) <= 3:
        return True

    # Fallback when data_fields is empty but entities still indicate a narrow metric lookup.
    has_metric_or_date_entity = any(
        getattr(entity, "entity_type", "") in {"metric", "date"}
        for entity in entities
    )
    if len(data_fields) == 0 and has_metric_or_date_entity and confidence >= 0.55:
        return True

    # Medium-confidence fallback for slightly longer metric-centric field lists.
    if 1 <= len(data_fields) <= 5:
        joined_fields = " ".join(data_fields)
        if any(term in joined_fields for term in metric_like_fields) and confidence >= 0.6:
            return True

    return False


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
            max_tokens=500,
            max_input_chars=8000,
            timeout_seconds=8,
            max_retries=0,
        )

    async def understand(
        self,
        query: str,
        document_filenames: Optional[List[str]] = None,
        domain_context: str = "financial documents",
        recent_messages: Optional[List[dict]] = None,
    ) -> QueryUnderstanding:
        """Analyze query and return structured understanding.

        Args:
            query: User's raw query string
            document_filenames: Available document names (for context)
            domain_context: Domain hint (e.g., "real estate", "financial")

        Returns:
            QueryUnderstanding with all fields populated
        """

        # Build dynamic context for the user message (keeps system_prompt fully static → cache hits).
        user_context_parts = [f"Domain context: {domain_context}", f"Query: {query}"]
        if document_filenames:
            user_context_parts.append(f"Available documents: {', '.join(document_filenames)}")
        if recent_messages:
            last_turns = recent_messages[-4:]
            lines = [f"{m['role'].title()}: {m['content'][:300]}" for m in last_turns]
            user_context_parts.append("Recent conversation:\n" + "\n".join(lines))
        user_text = "\n\n".join(user_context_parts)

        # system_prompt is fully static (no session/turn-specific data) → maximum cache hit rate.
        system_prompt = """You are a query analyzer for financial document RAG systems.

Analyze the user's query and provide structured understanding.

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

6. **data_fields**: If data extraction, list the specific fields the user asked for. Keep tight — one
   entry per distinct concept requested, exactly as the user phrased it.
   Example: "what is the asking price?" → ["asking price"]
   Example: "what are the NOI and cap rate?" → ["NOI", "cap rate"]

7. **data_field_synonyms**: Expand each entry in data_fields with all common synonyms and alternative
   phrasings used in financial documents. This improves keyword search recall when the document uses
   different terminology than the user. Include the original terms plus variants.
   Example: data_fields=["asking price"] → data_field_synonyms=["asking price", "offering price", "listing price", "purchase price", "sale price", "offered at"]
   Example: data_fields=["NOI"] → data_field_synonyms=["NOI", "net operating income", "annual NOI"]
   Example: data_fields=["cap rate"] → data_field_synonyms=["cap rate", "capitalization rate", "going-in cap rate", "exit cap rate"]
   Always populate if data_fields is non-empty. More synonyms = better recall.

8. **scope_mode**: Routing scope based on what documents the query targets.
   - `single_doc`: Query explicitly names ONE specific property/deal and asks only about it.
     Example: "What is the asking price for Tulsa Storage?" → single_doc
     Example: "Summarize Lane Prairie's financials" → single_doc
   - `multi_doc`: Query explicitly compares or asks about 2+ named properties simultaneously.
     Example: "Compare cap rates between Tulsa and Lane Prairie" → multi_doc
     (Note: query_type=comparison always implies multi_doc)
   - `ambiguous`: Query is general and doesn't target a specific document.
     Example: "What is the cap rate?" (no property named) → ambiguous
   - `global`: Query asks about all documents collectively.
     Example: "Summarize all the properties" → global
   Use `single_doc` whenever exactly ONE property/deal name appears in target_property_names.

8. **target_property_names**: Exact property/deal names explicitly present in the query text.
   - Extract only names that appear verbatim (or near-verbatim) in the query.
   - For single_doc: exactly 1 name. For multi_doc/comparison: 2+ names.
   - Leave empty for ambiguous/global queries.

9. **table_boost** and **narrative_boost**: Set retrieval boosting (0.5-2.0, default 1.0):
   - Comparison queries about financial metrics (cap rates, NOI, rent, occupancy, etc.): table_boost=1.5, narrative_boost=0.85
   - Data queries (numbers, metrics): table_boost=1.2, narrative_boost=0.9
   - Narrative queries (explanations, summaries): table_boost=1.0, narrative_boost=1.1
   - General queries: both=1.0

10. **needs_history**: Set to true ONLY if the query uses back-references that require
   prior conversation to interpret (e.g., "what about that one?", "also compare the other",
   "you mentioned earlier", "what about for X?"). Self-contained questions → false.

11. **rewritten_query**: If needs_history=true AND recent conversation is provided, rewrite the
   query as a fully self-contained question using context from the conversation.
   Example: "What about for Lane Prairie?" → "What are the cap rates for Lane Prairie Storage?"
   Leave null if needs_history=false.

Be concise and accurate. Focus on extraction, not explanation."""

        try:
            result = await self.llm_client.extract_structured_data_with_schema(
                text=user_text,
                system_prompt=system_prompt,
                pydantic_model=QueryUnderstanding,
                use_cache=True,  # system_prompt is static → cache hits across sessions
                max_retries_override=0,
            )

            understanding = QueryUnderstanding(**result["data"])

            logger.info(
                "Query understanding complete",
                extra={
                    "query": query[:50],
                    "query_type": understanding.query_type.value,
                    "scope_mode": understanding.scope_mode.value,
                    "target_property_names": (understanding.target_property_names or [])[:3],
                    "entities": [e.name for e in understanding.entities],
                    "confidence": understanding.confidence,
                    "needs_history": understanding.needs_history,
                    "has_rewritten_query": bool(understanding.rewritten_query),
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
