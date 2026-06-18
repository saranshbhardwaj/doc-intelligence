"""Integration tests for the memo Celery task with stubbed LLM and stubbed R2.

These tests exercise the real task code path — repositories, context assembly, DOCX
rendering — while patching out the three heavyweight collaborators:

  - ``_get_llm``      → replaced with ``_FakeLLM`` (no Anthropic API calls)
  - ``_get_retriever`` → replaced with ``_FakeRetriever`` (no pgvector queries)
  - ``_store_in_r2``  → replaced with an in-memory capture dict (no S3 calls)

``JobProgressTracker`` is also patched with a no-op stub so the task does not
require a ``JobState`` row to exist in the test DB.
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from docx import Document

import app.verticals.real_estate.underwriting.memo.tasks as memo_tasks
from app.verticals.real_estate.underwriting.memo.schemas import (
    PROSE_SECTIONS,
    SECTION_RECOMMENDATION,
    SECTION_RISKS,
    ProseSection,
    Recommendation,
    Risk,
    RisksSection,
)


# ---------------------------------------------------------------------------
# Fake collaborators
# ---------------------------------------------------------------------------


class _FakeLLM:
    """Returns deterministic Pydantic objects for every section schema."""

    async def parse(self, system, messages, output_format, max_tokens):
        name = output_format.__name__
        if name == "ProseSection":
            return ProseSection(paragraphs=["Stub para 1.", "Stub para 2."])
        if name == "RisksSection":
            return RisksSection(
                risks=[
                    Risk(title="R1", severity="medium", source="verdict_warning"),
                    Risk(title="R2", severity="low", source="rollover"),
                    Risk(title="R3", severity="medium", source="analyst_note"),
                ]
            )
        if name == "Recommendation":
            return Recommendation(
                classification="Pursue",
                rationale="Stub.",
                driving_metrics=["m1 vs t1"],
                conditions=["c1"],
            )
        raise AssertionError(f"Unknown schema requested from _FakeLLM: {name}")


class _FakeRetriever:
    """Returns an empty chunk list — sufficient for rendering."""

    def retrieve(self, **kwargs):
        return []


class _NoOpTracker:
    """No-op JobProgressTracker that doesn't require a JobState DB row."""

    def __init__(self, *args, **kwargs):
        pass

    def update_progress(self, **kwargs):
        pass

    def mark_completed(self):
        pass

    def mark_error(self, **kwargs):
        pass


class _SessionProxy:
    """Wraps pytest ``db_session`` but ignores ``close()`` calls from task code."""

    def __init__(self, session):
        self._session = session

    def close(self):
        # Keep the session open so the test can refresh fixtures afterwards.
        return None

    def __getattr__(self, item):
        return getattr(self._session, item)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded_memo(db_session, completed_run):
    """Create a pending UnderwritingMemo linked to the completed run."""
    from app.repositories.re_memo_repository import ReMemoRepository

    repo = ReMemoRepository(db_session)
    memo = repo.create(
        run_id=completed_run.id,
        user_id=completed_run.user_id,
        cover_data={
            "deal_name": "Test",
            "prepared_by": "Alice",
            "firm": "Acme",
            "date": "2026-05-20",
            "address": "A",
        },
        sponsor_data={"sponsor_name": "S"},
        market_notes=None,
    )
    return memo


def _run_task(seeded_memo, fake_llm, fake_retriever, captured_r2, monkeypatch, db_session):
    """Helper: wire up all patches and call the task synchronously."""
    proxy = _SessionProxy(db_session)

    def fake_store(key, data, content_type):
        captured_r2["key"] = key
        captured_r2["bytes"] = data
        return f"https://r2.example/{key}"

    monkeypatch.setattr(memo_tasks, "_get_db_session", lambda: proxy)
    monkeypatch.setattr(memo_tasks, "JobProgressTracker", _NoOpTracker)

    with patch.object(memo_tasks, "_get_llm", return_value=fake_llm), \
         patch.object(memo_tasks, "_get_retriever", return_value=fake_retriever), \
         patch.object(memo_tasks, "_store_in_r2", side_effect=fake_store):
        memo_tasks.generate_credit_memo_task.apply(
            args=[seeded_memo.id, seeded_memo.run_id, seeded_memo.user_id]
        ).get()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMemoTask:
    def test_full_task_succeeds_and_marks_complete(
        self, db_session, seeded_memo, monkeypatch
    ):
        """Happy path: task completes, memo is marked complete, DOCX is valid."""
        captured_r2: dict = {}

        _run_task(
            seeded_memo,
            _FakeLLM(),
            _FakeRetriever(),
            captured_r2,
            monkeypatch,
            db_session,
        )

        db_session.refresh(seeded_memo)
        assert seeded_memo.status == "complete"
        assert seeded_memo.r2_key
        assert seeded_memo.file_size_bytes and seeded_memo.file_size_bytes > 1000

        # Validate the DOCX bytes are a real document
        Document(io.BytesIO(captured_r2["bytes"]))

    def test_section_failure_records_warning_but_completes(
        self, db_session, seeded_memo, monkeypatch
    ):
        """When one parallel section fails, the task still completes and logs a warning."""

        class PartialFakeLLM(_FakeLLM):
            async def parse(self, system, messages, output_format, max_tokens):
                if output_format.__name__ == "RisksSection":
                    raise RuntimeError("Risks LLM exploded")
                return await super().parse(system, messages, output_format, max_tokens)

        captured_r2: dict = {}
        _run_task(
            seeded_memo,
            PartialFakeLLM(),
            _FakeRetriever(),
            captured_r2,
            monkeypatch,
            db_session,
        )

        db_session.refresh(seeded_memo)
        assert seeded_memo.status == "complete"
        assert any(
            "risks" in w.lower() for w in (seeded_memo.section_warnings or [])
        )

    def test_priming_failure_marks_failed(
        self, db_session, seeded_memo, monkeypatch
    ):
        """When the priming (Executive Summary) call fails, the task raises and memo is failed."""

        class PrimingFailLLM(_FakeLLM):
            _calls = 0

            async def parse(self, system, messages, output_format, max_tokens):
                PrimingFailLLM._calls += 1
                if PrimingFailLLM._calls == 1:
                    raise RuntimeError("priming bomb")
                return await super().parse(system, messages, output_format, max_tokens)

        proxy = _SessionProxy(db_session)

        def noop_store(key, data, content_type):
            return "ignored"

        monkeypatch.setattr(memo_tasks, "_get_db_session", lambda: proxy)
        monkeypatch.setattr(memo_tasks, "JobProgressTracker", _NoOpTracker)

        with patch.object(memo_tasks, "_get_llm", return_value=PrimingFailLLM()), \
             patch.object(memo_tasks, "_get_retriever", return_value=_FakeRetriever()), \
             patch.object(memo_tasks, "_store_in_r2", side_effect=noop_store):
            with pytest.raises(Exception):
                memo_tasks.generate_credit_memo_task.apply(
                    args=[seeded_memo.id, seeded_memo.run_id, seeded_memo.user_id]
                ).get(propagate=True)

        db_session.refresh(seeded_memo)
        assert seeded_memo.status == "failed"
        assert seeded_memo.error_message
