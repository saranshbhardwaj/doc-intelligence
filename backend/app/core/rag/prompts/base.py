"""Base class for versioned RAG prompt sets."""

from abc import ABC, abstractmethod


class RagPromptSet(ABC):
    """Interface for a versioned set of RAG prompts.

    Each concrete version (v1, v2, ...) owns the prompt strings for:
      - Regular chat (with and without retrieved chunks)
      - Comparison mode
      - Fact extractor (Map step of Map-Reduce comparison)
    """

    version: str

    @property
    @abstractmethod
    def system_instructions_with_chunks(self) -> str:
        """System prompt for regular chat when relevant chunks were retrieved."""

    @property
    @abstractmethod
    def system_instructions_no_chunks(self) -> str:
        """System prompt for regular chat when no relevant chunks were found."""

    @property
    @abstractmethod
    def comparison_system_instructions(self) -> str:
        """System prompt for comparison mode (raw chunk and fact-based variants)."""

    @abstractmethod
    def build_fact_extractor_system_prompt(
        self,
        document_name: str,
        query: str,
        aspects_str: str,
        chunk_context: str,
    ) -> str:
        """Build the full system prompt for the fact extractor LLM call.

        Args:
            document_name: Filename of the document being processed.
            query: User's original query.
            aspects_str: Comma-joined comparison aspects (or "key information").
            chunk_context: Pre-formatted chunk text blocks with page markers.
        """
