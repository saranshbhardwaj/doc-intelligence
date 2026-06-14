from app.core.rag.document_matching import DocumentMatcher


def test_score_document_match_normalizes_address_suffixes_in_scope_text():
    matcher = DocumentMatcher(None)
    document = {
        "id": "doc-sac",
        "filename": "OM-Sacramento-St.pdf",
        "aliases": [],
        "scope_text": "Offering Memorandum 3103-3107 Sacramento St San Francisco, CA 94115",
    }

    score = matcher._score_document_match("3103-3107 Sacramento Street", document)

    assert score >= 0.8


def test_fuzzy_match_document_uses_normalized_scope_text_for_address_query():
    matcher = DocumentMatcher(None)
    documents = [
        {
            "id": "doc-sac",
            "filename": "OM-Sacramento-St.pdf",
            "aliases": [],
            "scope_text": "Offering Memorandum 3103-3107 Sacramento St San Francisco, CA 94115",
        },
        {
            "id": "doc-other",
            "filename": "OM-Mobi_building.pdf",
            "aliases": [],
            "scope_text": "Offering Memorandum 123 Main Ave San Francisco, CA 94115",
        },
    ]

    match = matcher.fuzzy_match_document("3103-3107 Sacramento Street", documents, threshold=0.7)

    assert match is not None
    assert match["id"] == "doc-sac"