"""Tests for _format_chunks() chunk header format."""
import pytest


class TestChunkHeaderFormat:
    def _make_chunk(self, doc_id="doc-abc", page_number=3, text="Some text."):
        return {
            "document_id": doc_id,
            "page_number": page_number,
            "text": text,
            "chunk_metadata": {},
        }

    def _format(self, chunks):
        from app.core.rag.prompt_builder import PromptBuilder
        pb = PromptBuilder()
        return pb._format_chunks(chunks)

    def test_header_contains_citation_hint(self):
        result = self._format([self._make_chunk(page_number=5)])
        assert "[S1:p5]" in result

    def test_header_does_not_contain_source_n_label(self):
        """LLM should never see 'Source N' text — prevents prose leakage."""
        result = self._format([self._make_chunk()])
        assert "Source 1" not in result
        assert "Source 1:" not in result

    def test_multiple_chunks_no_source_n_label(self):
        chunks = [self._make_chunk(page_number=i) for i in range(1, 5)]
        result = self._format(chunks)
        for i in range(1, 5):
            assert f"Source {i}" not in result

    def test_header_contains_doc_id_when_no_filename(self):
        result = self._format([self._make_chunk(doc_id="xyz-123")])
        assert "xyz-123" in result

    def test_chunk_text_included(self):
        result = self._format([self._make_chunk(text="Cap rate is 8.11%")])
        assert "Cap rate is 8.11%" in result
