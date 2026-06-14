"""Unit tests for retrieval query construction."""

from app.core.rag.query_understanding import (
    ExtractedEntity,
    QueryType,
    ScopeMode,
    QueryUnderstanding,
)
from app.core.rag.retrieval_query import RetrievalQuery


def test_single_field_fact_lookup_keeps_required_phrase_filter():
    understanding = QueryUnderstanding(
        query_type=QueryType.DATA_EXTRACTION,
        entities=[
            ExtractedEntity(name="Tulsa Storage", entity_type="deal", confidence=0.99),
            ExtractedEntity(name="asking price", entity_type="metric", confidence=0.98),
        ],
        reformulated_query="asking price for tulsa storage",
        hypothetical_response="The asking price is listed in the investment overview.",
        comparison_aspects=[],
        data_fields=["asking price"],
        data_field_synonyms=["asking price", "purchase price", "offering price"],
        scope_mode=ScopeMode.SINGLE_DOC,
        target_property_names=["Tulsa Storage"],
        needs_history=False,
        confidence=0.95,
    )

    rq = RetrievalQuery.from_query_understanding(
        understanding,
        semantic_text="asking price for tulsa storage",
        doc_filenames=["Tulsa Storage OM.pdf"],
    )

    assert rq.lexical_required == ["asking price"]
    assert "purchase price" in rq.lexical_optional
    assert "offering price" in rq.lexical_optional


def test_multi_field_fact_lookup_uses_phrase_aware_ranking_without_required_filter():
    understanding = QueryUnderstanding(
        query_type=QueryType.DATA_EXTRACTION,
        entities=[
            ExtractedEntity(name="Tulsa Storage", entity_type="deal", confidence=0.98),
            ExtractedEntity(name="lot size", entity_type="metric", confidence=0.97),
            ExtractedEntity(name="median income", entity_type="metric", confidence=0.96),
        ],
        reformulated_query="Tulsa Storage lot size and median income",
        hypothetical_response="The lot size appears in the site description and the median income appears in market demographics.",
        comparison_aspects=[],
        data_fields=["lot size", "median income"],
        data_field_synonyms=[
            "lot size",
            "site area",
            "parcel size",
            "median income",
            "median household income",
        ],
        scope_mode=ScopeMode.SINGLE_DOC,
        target_property_names=["Tulsa Storage"],
        needs_history=False,
        confidence=0.92,
    )

    rq = RetrievalQuery.from_query_understanding(
        understanding,
        semantic_text="Tulsa Storage lot size and median income",
        doc_filenames=["Tulsa Storage OM.pdf"],
    )

    assert rq.lexical_required == []
    assert rq.lexical_optional[:2] == ["lot size", "median income"]
    assert "site area" in rq.lexical_optional
    assert "median household income" in rq.lexical_optional


def test_narrow_fact_lookup_keeps_unit_identifier_in_lexical_optional():
    understanding = QueryUnderstanding(
        query_type=QueryType.DATA_EXTRACTION,
        entities=[
            ExtractedEntity(name="Illinois_Institutional_Rent_Roll", entity_type="document", confidence=0.95),
            ExtractedEntity(name="unit 105", entity_type="property", confidence=0.90),
            ExtractedEntity(name="lease term", entity_type="metric", confidence=0.85),
            ExtractedEntity(name="balance due", entity_type="metric", confidence=0.85),
        ],
        reformulated_query="Illinois Institutional Rent Roll unit 105 lease term balance due",
        hypothetical_response="Unit 105 has a lease term and balance due in the rent roll.",
        comparison_aspects=[],
        data_fields=["lease term", "balance due"],
        data_field_synonyms=["lease term", "lease length", "balance due", "amount due"],
        scope_mode=ScopeMode.SINGLE_DOC,
        target_property_names=["Illinois_Institutional_Rent_Roll"],
        needs_history=False,
        confidence=0.92,
    )

    rq = RetrievalQuery.from_query_understanding(
        understanding,
        semantic_text="Illinois Institutional Rent Roll unit 105 lease term balance due",
        doc_filenames=["Illinois_Institutional_Rent_Roll.xlsx"],
    )

    assert rq.lexical_required == []
    assert "unit 105" in rq.lexical_optional
    assert "lease term" in rq.lexical_optional
    assert "balance due" in rq.lexical_optional