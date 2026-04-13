"""Unit tests for ambient prompt mode."""

import pytest

from app.core.rag.prompts.v1 import V1RagPromptSet
from app.core.rag.prompt_builder import PromptBuilder


class TestAmbientSystemInstructions:
    def test_returns_non_empty_string(self):
        instructions = V1RagPromptSet().ambient_system_instructions
        assert isinstance(instructions, str)
        assert len(instructions) > 0

    def test_contains_per_document(self):
        instructions = V1RagPromptSet().ambient_system_instructions
        assert "per document" in instructions
        assert "**[Document name]**" in instructions
        assert "one-sentence synthesis" in instructions
        assert "Omit documents" in instructions


class TestBuildAmbientSplit:
    def _make_chunk(self, doc_id: str = "doc-1", text: str = "Some text.", page: int = 1):
        return {
            "document_id": doc_id,
            "text": text,
            "page_number": page,
            "chunk_metadata": {},
            "section_heading": None,
        }

    def test_returns_two_non_empty_strings(self):
        builder = PromptBuilder()
        system_prompt, user_content = builder.build_ambient_split(
            user_message="What is the cap rate?",
            relevant_chunks=[self._make_chunk()],
            recent_messages=[],
        )
        assert isinstance(system_prompt, str) and len(system_prompt) > 0
        assert isinstance(user_content, str) and len(user_content) > 0

    def test_system_prompt_contains_ambient_instructions(self):
        builder = PromptBuilder()
        system_prompt, _ = builder.build_ambient_split(
            user_message="What is the cap rate?",
            relevant_chunks=[self._make_chunk()],
            recent_messages=[],
        )
        assert "per document" in system_prompt

    def test_no_chunks_falls_back_to_no_chunks_instructions(self):
        builder = PromptBuilder()
        system_prompt, user_content = builder.build_ambient_split(
            user_message="What is the cap rate?",
            relevant_chunks=[],
            recent_messages=[],
        )
        assert isinstance(system_prompt, str) and len(system_prompt) > 0
        assert isinstance(user_content, str) and len(user_content) > 0
        assert "No relevant document excerpts" in user_content
        assert "per document" not in system_prompt
