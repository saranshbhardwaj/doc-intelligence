from app.core.rag.query_understanding import should_consult_history_for_query


def test_self_contained_property_question_skips_history():
    assert should_consult_history_for_query(
        "what is the lot size and median income for Tulsa storage unit?"
    ) is False


def test_explicit_property_metric_question_skips_history():
    assert should_consult_history_for_query(
        "What is the cap rate for LANE PRAIRIE STORAGE?"
    ) is False


def test_follow_up_question_uses_history():
    assert should_consult_history_for_query("what about the other property?") is True


def test_pronoun_follow_up_uses_history():
    assert should_consult_history_for_query("and what is its cap rate?") is True