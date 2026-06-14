from app.core.rag.query_understanding import (
    QueryType,
    ScopeMode,
    QueryUnderstanding,
    is_narrow_explicit_fact_lookup,
    _apply_deterministic_fallbacks,
)


def _make_sparse_understanding() -> QueryUnderstanding:
    return QueryUnderstanding(
        query_type=QueryType.GENERAL_QA,
        entities=[],
        reformulated_query="",
        hypothetical_response="",
        comparison_aspects=[],
        data_fields=[],
        data_field_synonyms=[],
        scope_mode=ScopeMode.AMBIGUOUS,
        target_property_names=[],
        table_boost=1.0,
        narrative_boost=1.0,
        needs_history=False,
        rewritten_query=None,
        confidence=0.3,
    )


def test_fallback_promotes_address_metric_query_to_single_doc_data_extraction():
    understanding = _make_sparse_understanding()

    updated = _apply_deterministic_fallbacks(
        "what are the lot size and approximate year built for 3103-3107 Sacramento Street?",
        understanding,
    )

    assert updated.query_type == QueryType.DATA_EXTRACTION
    assert updated.scope_mode == ScopeMode.SINGLE_DOC
    assert updated.target_property_names == ["3103-3107 Sacramento Street"]
    assert updated.data_fields == ["approximate year built", "lot size"]
    assert "acreage" in updated.data_field_synonyms
    assert "year built" in updated.data_field_synonyms
    assert is_narrow_explicit_fact_lookup(updated) is True
    assert any(entity.entity_type == "property" for entity in updated.entities)
    assert {entity.name for entity in updated.entities if entity.entity_type == "metric"} == {
        "approximate year built",
        "lot size",
    }


def test_fallback_captures_multi_metric_pricing_query():
    understanding = _make_sparse_understanding()

    updated = _apply_deterministic_fallbacks(
        "what are the price per unit and price per square foot for 3103-3107 Sacramento Street?",
        understanding,
    )

    assert updated.query_type == QueryType.DATA_EXTRACTION
    assert updated.scope_mode == ScopeMode.SINGLE_DOC
    assert updated.target_property_names == ["3103-3107 Sacramento Street"]
    assert updated.data_fields == ["price per square foot", "price per unit"]
    assert "psf" in updated.data_field_synonyms
    assert "ppu" in updated.data_field_synonyms
    assert is_narrow_explicit_fact_lookup(updated) is True