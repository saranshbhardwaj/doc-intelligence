"""
Extraction-specific LLM operations.

This service handles summarization tasks for the full extraction pipeline.
It depends on the core LLMClient for API calls but contains extraction-specific logic.
"""

import asyncio
import re
from typing import List, Dict

from app.services.llm_client import LLMClient
from app.services.extractions.prompts import (
    SUMMARY_SYSTEM_PROMPT,
    create_summary_prompt,
    create_batch_summary_prompt,
)
from app.utils.logging import logger


class ExtractionLLMService:
    """
    Extraction-specific LLM service for chunk summarization.

    Handles:
    - Single chunk summarization
    - Batch chunk summarization
    - Batch output parsing

    Uses cheap LLM model for cost efficiency.
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize extraction LLM service.

        Args:
            llm_client: Core LLM client with Anthropic API access
        """
        self.llm_client = llm_client
        self.client = llm_client.client  # Access to Anthropic client
        self.cheap_model = llm_client.cheap_model
        self.cheap_max_tokens = llm_client.cheap_max_tokens
        self.cheap_timeout_seconds = llm_client.cheap_timeout_seconds

        logger.info(
            f"ExtractionLLMService initialized with model: {self.cheap_model}",
            extra={"model": self.cheap_model, "max_tokens": self.cheap_max_tokens}
        )

    async def summarize_chunk(self, chunk_text: str) -> str:
        """
        Async wrapper to summarize a single chunk using thread offload.

        Args:
            chunk_text: Text content of the chunk

        Returns:
            Summary text (or original chunk if summarization fails)
        """
        return await asyncio.to_thread(self._summarize_chunk_sync, chunk_text)

    def _summarize_chunk_sync(self, chunk_text: str) -> str:
        """
        Synchronous chunk summarization.

        Args:
            chunk_text: Text content of the chunk

        Returns:
            Summary text (or original chunk if summarization fails)
        """
        prompt = create_summary_prompt(chunk_text)
        logger.info(
            f"Calling cheap LLM ({self.cheap_model}) for chunk summary",
            extra={"prompt_length": len(prompt)}
        )

        try:
            message = self.client.messages.create(
                model=self.cheap_model,
                max_tokens=self.cheap_max_tokens,
                temperature=0.0,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            summary = message.content[0].text.strip()
            logger.debug(f"Chunk summary generated: {len(summary)} chars")
            return summary

        except Exception as e:
            logger.error(f"Chunk summarization failed: {e}")
            logger.warning("Falling back to original chunk text")
            return chunk_text

    async def summarize_chunks_batch(self, chunks: List[Dict]) -> List[str]:
        """
        Async wrapper for batch summarization using thread offload.

        Args:
            chunks: List of chunk dicts with "text" field

        Returns:
            List of summary strings (one per chunk)
        """
        return await asyncio.to_thread(self._summarize_chunks_batch_sync, chunks)

    def _summarize_chunks_batch_sync(self, chunks: List[Dict]) -> List[str]:
        """
        Synchronous batch summarization.

        Sends multiple chunks in a single API call for efficiency.

        Args:
            chunks: List of chunk dicts with "text" field

        Returns:
            List of summary strings (one per chunk, or original text on failure)
        """
        if not chunks:
            return []

        prompt = create_batch_summary_prompt(chunks)
        logger.info(
            f"Calling cheap LLM ({self.cheap_model}) for batch summary of {len(chunks)} chunks",
            extra={"prompt_length": len(prompt), "chunk_count": len(chunks)}
        )

        try:
            message = self.client.messages.create(
                model=self.cheap_model,
                max_tokens=self.cheap_max_tokens,
                temperature=0.0,
                system=SUMMARY_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            batch_summary = message.content[0].text.strip()
            logger.info(f"Batch summary received: {len(batch_summary)} chars")

            # Parse individual summaries from batch output
            return self._parse_batch_summaries(batch_summary, len(chunks))

        except Exception as e:
            logger.error(f"Batch summarization failed: {e}")
            logger.warning("Falling back to original chunk texts")
            return [chunk["text"] for chunk in chunks]

    def _parse_batch_summaries(self, batch_output: str, expected_count: int) -> List[str]:
        """
        Parse individual summaries from batch output.

        Expected format (from semantic chunking):
            Chunk 1: [summary]
            Key Numbers: [numbers]

            Chunk 2: [summary]
            Key Numbers: [numbers]

        Args:
            batch_output: Raw batch summary output from LLM
            expected_count: Number of chunks that were summarized

        Returns:
            List of parsed summaries (padded with empty strings if parsing fails)
        """
        summaries = []

        # Split by "Chunk N:" pattern
        chunk_pattern = r"Chunk \d+:\s*(.+?)(?=Chunk \d+:|$)"
        matches = re.findall(chunk_pattern, batch_output, re.DOTALL)

        if len(matches) >= expected_count:
            summaries = [match.strip() for match in matches[:expected_count]]
        else:
            # Parsing failed, use fallback parsing
            logger.warning(
                f"Failed to parse {expected_count} summaries, got {len(matches)}. Using fallback parsing."
            )
            parts = batch_output.split("\n\n")
            summaries = parts[:expected_count]

            # Pad with empty strings if needed
            while len(summaries) < expected_count:
                summaries.append("")

        return summaries
