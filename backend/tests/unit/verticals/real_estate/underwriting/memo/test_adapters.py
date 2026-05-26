"""Unit tests for the memo adapter classes (LLM + RAG)."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _fake_response(input_tokens: int, output_tokens: int, cache_creation=0, cache_read=0, parsed_output=None):
    """Build a fake Anthropic ``messages.parse`` response."""
    if parsed_output is None:
        parsed_output = SimpleNamespace(model_dump=lambda: {"ok": True})
    return SimpleNamespace(
        parsed_output=parsed_output,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_creation_input_tokens=cache_creation,
            cache_read_input_tokens=cache_read,
        ),
        stop_reason="end_turn",
    )


class TestAnthropicMemoLLMUsageAccumulator:
    """The adapter must accumulate token usage across calls so the Celery task
    can record Prometheus metrics + persist to DB after narration."""

    def test_get_usage_totals_initial_state(self):
        from app.verticals.real_estate.underwriting.memo.adapters import AnthropicMemoLLM
        with patch.object(AnthropicMemoLLM, "__init__", lambda self: None):
            llm = AnthropicMemoLLM()
        llm.model = "claude-haiku-4-5"
        llm._client = MagicMock()
        llm._usage_total = {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            "calls": 0,
        }
        totals = llm.get_usage_totals()
        assert totals["calls"] == 0
        assert totals["input_tokens"] == 0
        assert totals["model"] == "claude-haiku-4-5"

    def test_parse_accumulates_per_call_usage(self):
        from app.verticals.real_estate.underwriting.memo.adapters import AnthropicMemoLLM
        with patch.object(AnthropicMemoLLM, "__init__", lambda self: None):
            llm = AnthropicMemoLLM()
        llm.model = "claude-haiku-4-5"
        llm._client = MagicMock()
        llm._usage_total = {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            "calls": 0,
        }
        # First call writes cache, second hits cache.
        responses = [
            _fake_response(input_tokens=2000, output_tokens=500, cache_creation=1800),
            _fake_response(input_tokens=200, output_tokens=400, cache_read=1800),
        ]
        llm._client.messages.parse = MagicMock(side_effect=responses)

        async def _go():
            r1 = await llm.parse(system="", messages=[{"role": "user", "content": "x"}],
                                 output_format=type("S", (), {}), max_tokens=100)
            r2 = await llm.parse(system="", messages=[{"role": "user", "content": "y"}],
                                 output_format=type("S", (), {}), max_tokens=100)
            return r1, r2

        asyncio.run(_go())
        totals = llm.get_usage_totals()
        assert totals["calls"] == 2
        assert totals["input_tokens"] == 2200
        assert totals["output_tokens"] == 900
        assert totals["cache_creation_input_tokens"] == 1800
        assert totals["cache_read_input_tokens"] == 1800

    def test_parse_still_accumulates_usage_when_parsed_output_missing(self):
        """Even when the response has no parsed_output (e.g., max_tokens hit),
        the cost was incurred — usage must still accumulate before raising."""
        from app.verticals.real_estate.underwriting.memo.adapters import AnthropicMemoLLM
        with patch.object(AnthropicMemoLLM, "__init__", lambda self: None):
            llm = AnthropicMemoLLM()
        llm.model = "claude-haiku-4-5"
        llm._client = MagicMock()
        llm._usage_total = {
            "input_tokens": 0, "output_tokens": 0,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0,
            "calls": 0,
        }
        bad_response = _fake_response(input_tokens=500, output_tokens=0)
        bad_response.parsed_output = None
        bad_response.stop_reason = "max_tokens"
        llm._client.messages.parse = MagicMock(return_value=bad_response)

        import pytest
        async def _go():
            await llm.parse(system="", messages=[{"role": "user", "content": "x"}],
                            output_format=type("S", (), {}), max_tokens=10)

        with pytest.raises(RuntimeError):
            asyncio.run(_go())
        # Usage was still recorded.
        totals = llm.get_usage_totals()
        assert totals["calls"] == 1
        assert totals["input_tokens"] == 500
