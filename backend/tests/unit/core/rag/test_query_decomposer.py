"""Unit tests for QueryDecomposer."""
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock


class TestIsMultiAspect:
    def test_multiple_question_marks(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        assert is_multi_aspect("What is the cap rate? What is the NOI?") is True

    def test_numbered_list(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        assert is_multi_aspect("1. Cap rate 2. Occupancy 3. Expansion potential") is True

    def test_conjunction_phrase(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        assert is_multi_aspect("What is the cap rate and also the occupancy rate?") is True

    def test_long_data_extraction(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        from app.core.rag.query_understanding import QueryType
        long_query = "x" * 301
        qu = MagicMock()
        qu.query_type = QueryType.DATA_EXTRACTION
        assert is_multi_aspect(long_query, query_understanding=qu) is True

    def test_simple_query_not_multi_aspect(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        assert is_multi_aspect("What is the cap rate?") is False

    def test_short_query_not_multi_aspect(self):
        from app.core.rag.query_decomposer import is_multi_aspect
        assert is_multi_aspect("Tell me about the property") is False


class TestMergeEmbeddings:
    def test_single_embedding_returned_as_is(self):
        from app.core.rag.query_decomposer import merge_embeddings
        v = [0.1, 0.2, 0.3]
        assert merge_embeddings([v]) == pytest.approx(v)

    def test_two_embeddings_averaged(self):
        from app.core.rag.query_decomposer import merge_embeddings
        assert merge_embeddings([[1.0, 0.0], [0.0, 1.0]]) == pytest.approx([0.5, 0.5])

    def test_three_embeddings_averaged(self):
        from app.core.rag.query_decomposer import merge_embeddings
        assert merge_embeddings([[3.0, 0.0], [0.0, 3.0], [0.0, 0.0]]) == pytest.approx([1.0, 1.0])


@pytest.mark.asyncio
class TestDecomposeAndEmbed:
    async def test_passthrough_for_simple_query(self):
        from app.core.rag.query_decomposer import decompose_and_embed
        embedder = MagicMock()
        embedder.embed_text.return_value = [0.1, 0.2, 0.3]
        llm_client = MagicMock()

        result = await decompose_and_embed(
            query="What is the cap rate?",
            query_understanding=None,
            embedding_provider=embedder,
            llm_client=llm_client,
        )

        assert result.was_decomposed is False
        assert result.sub_queries == ["What is the cap rate?"]
        assert result.merged_embedding == []  # passthrough skips embed to avoid wasted round-trip
        llm_client.stream_chat.assert_not_called()

    async def test_decomposition_averages_embeddings(self):
        from app.core.rag.query_decomposer import decompose_and_embed
        embedder = MagicMock()
        embedder.embed_text.side_effect = [[1.0, 0.0], [0.0, 1.0]]

        async def _fake_stream(*args, **kwargs):
            yield {"type": "chunk", "text": '["cap rate", "occupancy rate"]'}

        llm_client = MagicMock()
        llm_client.stream_chat = _fake_stream

        result = await decompose_and_embed(
            query="What is the cap rate? And the occupancy rate?",
            query_understanding=None,
            embedding_provider=embedder,
            llm_client=llm_client,
        )

        assert result.was_decomposed is True
        assert result.sub_queries == ["cap rate", "occupancy rate"]
        assert result.merged_embedding == pytest.approx([0.5, 0.5])

    async def test_llm_single_item_array_treated_as_passthrough(self):
        from app.core.rag.query_decomposer import decompose_and_embed
        embedder = MagicMock()
        embedder.embed_text.return_value = [0.5, 0.5]

        async def _fake_stream(*args, **kwargs):
            yield {"type": "chunk", "text": '["What is the cap rate?"]'}

        llm_client = MagicMock()
        llm_client.stream_chat = _fake_stream

        result = await decompose_and_embed(
            query="What is the cap rate? And the occupancy rate?",
            query_understanding=None,
            embedding_provider=embedder,
            llm_client=llm_client,
        )

        assert result.was_decomposed is False
        assert len(result.sub_queries) == 1

    async def test_llm_exception_falls_back_to_original_query(self):
        from app.core.rag.query_decomposer import decompose_and_embed
        embedder = MagicMock()
        embedder.embed_text.return_value = [0.1, 0.2, 0.3]

        async def _raising_stream(*args, **kwargs):
            raise RuntimeError("LLM unavailable")
            yield  # yield is required to make this an async generator; raise fires at first __anext__

        llm_client = MagicMock()
        llm_client.stream_chat = _raising_stream
        llm_client.cheap_model = "claude-haiku-4-5"

        query = "What is the cap rate? And the occupancy rate?"
        result = await decompose_and_embed(
            query=query,
            query_understanding=None,
            embedding_provider=embedder,
            llm_client=llm_client,
        )

        assert result.was_decomposed is False
        assert result.sub_queries == [query]
        assert result.merged_embedding == []  # fallback skips embed to avoid wasted round-trip
        embedder.embed_text.assert_not_called()
