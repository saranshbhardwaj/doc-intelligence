"""Unit tests for RAG eval contract helpers."""

from app.core.rag.eval_contract import serialize_query_understanding
from app.core.rag.query_understanding import QueryType, ScopeMode, QueryUnderstanding


class TestSerializeQueryUnderstanding:
    def test_serializes_data_field_synonyms(self):
        understanding = QueryUnderstanding(
            query_type=QueryType.DATA_EXTRACTION,
            entities=[],
            reformulated_query="asking price tulsa storage",
            hypothetical_response="The asking price appears in the OM investment highlights.",
            comparison_aspects=[],
            data_fields=["asking price"],
            data_field_synonyms=["asking price", "offering price", "purchase price"],
            scope_mode=ScopeMode.SINGLE_DOC,
            target_property_names=["Tulsa Storage"],
            table_boost=1.2,
            narrative_boost=0.9,
            needs_history=False,
            rewritten_query=None,
            confidence=0.9,
        )

        serialized = serialize_query_understanding(understanding)

        assert serialized["data_fields"] == ["asking price"]
        assert serialized["data_field_synonyms"] == [
            "asking price",
            "offering price",
            "purchase price",
        ]