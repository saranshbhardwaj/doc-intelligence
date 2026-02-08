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

    async def extract_key_facts(self, messages: List[Dict]) -> List[str]:
        """
        Extract key facts from conversation messages that should never be lost.

        Important facts include:
        - Named entities (companies, people, documents, products)
        - Numeric values (revenue, dates, percentages, metrics)
        - Decisions made or conclusions reached
        - User preferences or requirements expressed

        Args:
            messages: List of message dicts with "role" and "content" keys

        Returns:
            List of key fact strings (max 10 items)
        """
        if not messages:
            return []

        # Format conversation for fact extraction
        joined = "\n".join([
            f"{m['role'].title()}: {m['content']}"
            for m in messages
        ])

        # Build fact extraction prompt
        prompt = (
            "Extract key facts from this conversation that must be preserved:\n"
            "- Named entities (companies, people, documents)\n"
            "- Numeric values (revenue, dates, percentages)\n"
            "- Decisions made or conclusions reached\n"
            "- User preferences expressed\n\n"
            "Return as a bullet list with ONE fact per line. Max 10 items. "
            "Use format: - <fact>\n\n"
            f"Conversation:\n{joined}\n\n"
            "Key Facts:"
        )

        logger.info(
            f"Extracting key facts from {len(messages)} messages",
            extra={"message_count": len(messages)}
        )

        try:
            # Stream key facts from LLM
            facts_text = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                facts_text += chunk

            # Parse bullet points into list
            facts_text = facts_text.strip()
            facts = []
            for line in facts_text.split("\n"):
                line = line.strip()
                # Remove bullet markers (-, *, •, etc.)
                if line.startswith(("- ", "* ", "• ", "· ")):
                    fact = line[2:].strip()
                    if fact:
                        facts.append(fact)

            # Limit to 10 facts
            facts = facts[:10]

            logger.info(
                f"Extracted {len(facts)} key facts",
                extra={"fact_count": len(facts)}
            )
            return facts

        except Exception as e:
            logger.warning(
                f"Key fact extraction failed: {e}",
                extra={"error": str(e)}
            )
            return []

    async def progressive_summarize(
        self,
        previous_summary: str,
        new_messages: List[Dict],
        key_facts: List[str]
    ) -> str:
        """
        Build on existing summary with new messages (progressive/rolling summarization).

        Instead of re-summarizing all history, this updates the previous summary
        with new information, preventing "summary of summary" degradation.

        Args:
            previous_summary: The existing summary text
            new_messages: List of new message dicts since last summary
            key_facts: List of key facts to preserve

        Returns:
            Updated summary text
        """
        if not new_messages:
            return previous_summary

        # Format new messages
        joined_new = "\n".join([
            f"{m['role'].title()}: {m['content']}"
            for m in new_messages
        ])

        # Format key facts
        facts_section = ""
        if key_facts:
            facts_section = "\n\nKEY FACTS TO PRESERVE:\n" + "\n".join([f"- {fact}" for fact in key_facts])

        # Build progressive summarization prompt
        prompt = (
            "You are updating a conversation summary with new messages.\n\n"
            f"PREVIOUS SUMMARY:\n{previous_summary}\n"
            f"{facts_section}\n\n"
            f"NEW MESSAGES:\n{joined_new}\n\n"
            "Create an updated summary that:\n"
            "1. Preserves important context from the previous summary\n"
            "2. Integrates new information from recent messages\n"
            "3. Removes redundant or superseded information\n"
            "4. Stays under 2000 characters\n"
            "5. Preserves all key facts listed above\n\n"
            "Updated Summary:"
        )

        logger.info(
            f"Progressive summarization: {len(new_messages)} new messages",
            extra={
                "new_message_count": len(new_messages),
                "previous_summary_length": len(previous_summary),
                "key_facts_count": len(key_facts)
            }
        )

        try:
            # Stream updated summary from LLM
            updated_summary = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                updated_summary += chunk

            updated_summary = updated_summary.strip()

            if not updated_summary:
                logger.warning("Progressive summarization returned empty, using previous summary")
                return previous_summary

            logger.info(
                f"Summary updated: {len(previous_summary)} → {len(updated_summary)} chars",
                extra={
                    "previous_length": len(previous_summary),
                    "updated_length": len(updated_summary)
                }
            )
            return updated_summary

        except Exception as e:
            logger.warning(
                f"Progressive summarization failed, using previous summary: {e}",
                extra={"error": str(e)}
            )
            return previous_summary

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
