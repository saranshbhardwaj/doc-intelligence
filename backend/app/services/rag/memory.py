"""Conversation Memory component.

Handles:
 - Loading bounded history
 - Estimating token usage (heuristic)
 - Deciding whether to summarize
 - Generating summaries & compressed summaries
 - Summary caching lifecycle

External dependencies injected: llm_client (streaming interface) and optional DB repository via ChatRepository.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.services.cache.conversation_summary_cache import ConversationSummaryCache
from app.utils.logging import logger

class ConversationMemory:
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.cache = ConversationSummaryCache()

    # -------- History Loading --------
    def load_history(self, session_id: str) -> List[Dict[str, Any]]:
        from app.repositories.chat_repository import ChatRepository
        repo = ChatRepository()
        max_msgs = settings.chat_max_history_messages
        msgs = repo.get_messages(session_id, limit=max_msgs)
        return [
            {"role": m.role, "content": m.content, "message_index": m.message_index}
            for m in msgs
            if m.role in ("user", "assistant")
        ]

    # -------- Token Estimation --------
    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // 4)

    # -------- Summarization Decision --------
    async def maybe_summarize(
        self,
        session_id: str,
        history_messages: List[Dict[str, Any]],
        user_message: str
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Return (summary_text, recent_messages) based on history & budgeting thresholds."""
        if not history_messages:
            return None, []
        history_text = "\n".join([f"{m['role'].title()}: {m['content']}" for m in history_messages])
        est_history_tokens = self.estimate_tokens(history_text)
        est_user_tokens = self.estimate_tokens(user_message)
        max_input_tokens = settings.llm_max_input_chars // 4 if settings.llm_max_input_chars else 0
        usage_ratio = (est_history_tokens + est_user_tokens) / max_input_tokens if max_input_tokens else 0

        summary_text: Optional[str] = None
        recent_messages = history_messages[-settings.chat_verbatim_message_count:] if settings.chat_verbatim_message_count > 0 else []

        should_summarize = (
            len(history_messages) >= settings.chat_summary_min_messages and
            usage_ratio >= settings.chat_summary_trigger_ratio
        )
        if should_summarize:
            older_messages = history_messages[:-settings.chat_verbatim_message_count] if settings.chat_verbatim_message_count < len(history_messages) else []
            if older_messages:
                cached = self.cache.get(session_id)
                current_message_count = len(history_messages)
                if cached and cached.get("message_count") == current_message_count:
                    summary_text = cached.get("compressed") or cached.get("summary")
                    logger.info("Using cached conversation summary", extra={"session_id": session_id})
                else:
                    summary_text = await self._summarize_messages(older_messages)
        return summary_text, recent_messages

    # -------- Summarization --------
    async def _summarize_messages(self, messages: List[Dict[str, Any]]) -> str:
        if not messages:
            return ""
        joined = "\n".join([f"{m['role'].title()}: {m['content']}" for m in messages])
        prompt = (
            "You are summarizing a financial analysis chat. Produce a concise, factual summary of prior messages. "
            "Preserve important entities, metrics, time references, decisions, and uncertainties. Do NOT invent facts.\n\n"
            f"Conversation:\n{joined}\n\nSummary:" )
        try:
            summary = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                summary += chunk
            return summary.strip()
        except Exception as e:
            logger.warning(f"Summarization failed, falling back to heuristic: {e}")
            import re
            assistant_sentences = []
            for m in messages:
                if m["role"] == "assistant":
                    sentences = re.split(r"(?<=[.!?])\s+", m["content"].strip())
                    if sentences:
                        assistant_sentences.append(sentences[0])
            fallback = "Previous discussion summary: " + "; ".join(assistant_sentences[:8])
            return fallback[:1000]

    # -------- Compression --------
    async def compress_summary(self, summary_text: str) -> str:
        if not summary_text:
            return summary_text
        prompt = (
            "You are a compression assistant. Rewrite the following conversation summary to be FAR shorter (<= 3000 characters), "
            "preserving only key entities, numeric values, decisions, disagreements, and open questions. Remove redundancy and narrative filler. "
            "Do not add new facts.\n\nOriginal Summary:\n" + summary_text + "\n\nCompressed Summary:" )
        try:
            compressed = ""
            async for chunk in self.llm_client.stream_chat(prompt):
                compressed += chunk
            compressed = compressed.strip()
            if not compressed:
                return summary_text
            return compressed
        except Exception as e:
            logger.warning(f"Summary compression failed: {e}; returning original summary.")
            return summary_text

    # -------- Cache Write --------
    def cache_summary(self, session_id: str, message_count: int, summary_text: str):
        cached = self.cache.get(session_id)
        if not summary_text:
            return
        if cached and cached.get("message_count") == message_count:
            return
        self.cache.set(
            session_id=session_id,
            message_count=message_count,
            summary=summary_text,
            compressed=summary_text
        )
        logger.info("Cached new conversation summary", extra={"session_id": session_id, "message_count": message_count})
