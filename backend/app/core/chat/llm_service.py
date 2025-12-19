"""
Chat-specific LLM operations.

This service handles conversation summarization for the free-form chat pipeline.
It depends on the core LLMClient for streaming API calls but contains chat-specific logic.
"""

from typing import List, Dict
import re

from app.core.llm.llm_client import LLMClient
from app.utils.logging import logger


class ChatLLMService:
    """
    Chat-specific LLM service for conversation summarization.

    Handles:
    - Conversation history summarization
    - Fallback heuristic summarization (if LLM fails)

    Uses cheap LLM model for cost efficiency (streaming mode).
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize chat LLM service.

        Args:
            llm_client: Core LLM client with Anthropic API access
        """
        self.llm_client = llm_client

        logger.info(
            "ChatLLMService initialized",
            extra={"model": llm_client.cheap_model}
        )

    async def summarize_conversation(self, messages: List[Dict]) -> str:
        """
        Summarize conversation history into a concise summary.

        Used to compress older conversation messages when context window is filling up.
        Preserves important entities, metrics, decisions, and uncertainties.

        Args:
            messages: List of message dicts with "role" and "content" keys
                     Example: [{"role": "user", "content": "..."}, ...]

        Returns:
            Summary text (or fallback heuristic summary if LLM fails)
        """
        if not messages:
            return ""

        # Format conversation for summarization
        joined = "\n".join([
            f"{m['role'].title()}: {m['content']}"
            for m in messages
        ])

        # Build summarization prompt
        prompt = (
            "You are summarizing a financial analysis chat. "
            "Produce a concise, factual summary of prior messages. "
            "Preserve important entities, metrics, time references, decisions, and uncertainties. "
            "Do NOT invent facts.\n\n"
            f"Conversation:\n{joined}\n\n"
            "Summary:"
        )

        logger.info(
            f"Summarizing {len(messages)} conversation messages",
            extra={"message_count": len(messages), "prompt_length": len(prompt)}
        )

        try:
            # Stream summary from LLM
            summary = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                summary += chunk

            summary = summary.strip()
            logger.info(
                f"Conversation summary generated: {len(summary)} chars",
                extra={"summary_length": len(summary)}
            )
            return summary

        except Exception as e:
            logger.warning(
                f"LLM summarization failed, using heuristic fallback: {e}",
                extra={"error": str(e)}
            )
            # Fallback to heuristic summarization
            return self._heuristic_summarize(messages)

    async def compress_summary(self, summary_text: str) -> str:
        """
        Compress an existing summary to be even shorter.

        Used when a summary is still too long for context window.
        Target: <= 3000 characters.

        Args:
            summary_text: Original summary text to compress

        Returns:
            Compressed summary (or original if compression fails)
        """
        if not summary_text:
            return summary_text

        prompt = (
            "You are a compression assistant. "
            "Rewrite the following conversation summary to be FAR shorter (<= 3000 characters), "
            "preserving only key entities, numeric values, decisions, disagreements, and open questions. "
            "Remove redundancy and narrative filler. Do not add new facts.\n\n"
            f"Original Summary:\n{summary_text}\n\n"
            "Compressed Summary:"
        )

        logger.info(
            f"Compressing summary: {len(summary_text)} chars",
            extra={"original_length": len(summary_text)}
        )

        try:
            # Stream compressed summary from LLM
            compressed = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                compressed += chunk

            compressed = compressed.strip()

            if not compressed:
                logger.warning("Compression returned empty text, using original")
                return summary_text

            logger.info(
                f"Summary compressed: {len(summary_text)} → {len(compressed)} chars",
                extra={
                    "original_length": len(summary_text),
                    "compressed_length": len(compressed)
                }
            )
            return compressed

        except Exception as e:
            logger.warning(
                f"Summary compression failed, using original: {e}",
                extra={"error": str(e)}
            )
            return summary_text

    def _heuristic_summarize(self, messages: List[Dict]) -> str:
        """
        Fallback heuristic summarization when LLM fails.

        Extracts first sentence from each assistant response as a basic summary.

        Args:
            messages: List of message dicts

        Returns:
            Heuristic summary text
        """
        assistant_sentences = []

        for m in messages:
            if m["role"] == "assistant":
                # Split content into sentences
                sentences = re.split(r"(?<=[.!?])\s+", m["content"].strip())
                if sentences:
                    # Take first sentence as summary
                    assistant_sentences.append(sentences[0])

        if assistant_sentences:
            summary = " ".join(assistant_sentences[:10])  # Cap at 10 sentences
            logger.info(
                f"Heuristic summary generated: {len(summary)} chars from {len(assistant_sentences)} sentences"
            )
            return summary
        else:
            logger.warning("No assistant messages found for heuristic summary")
            return "Conversation history summarized."
