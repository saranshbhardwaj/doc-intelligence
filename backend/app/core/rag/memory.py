"""Conversation Memory component.

Handles:
 - Loading bounded history
 - Estimating token usage (heuristic)
 - Deciding whether to summarize
 - Summary caching lifecycle

LLM operations (summarization, compression) delegated to ChatLLMService.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.core.cache.conversation_summary_cache import ConversationSummaryCache
from app.core.chat.llm_service import ChatLLMService
from app.utils.logging import logger
from app.utils.token_utils import count_tokens

class ConversationMemory:
    def __init__(self, chat_llm_service: ChatLLMService):
        """
        Initialize conversation memory.

        Args:
            chat_llm_service: Chat LLM service for summarization operations
        """
        self.chat_llm_service = chat_llm_service
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
        count_tokens
        return max(1, count_tokens(text))

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

        # Estimate max input tokens from max chars (rough approximation: 1 token ≈ 4 chars)
        # settings.llm_max_input_chars is an integer (max characters), not text to tokenize
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
        """
        Summarize older conversation messages.

        Delegates to ChatLLMService for actual LLM call.
        """
        if not messages:
            return ""

        # Delegate to ChatLLMService
        return await self.chat_llm_service.summarize_conversation(messages)

    # -------- Compression --------
    async def compress_summary(self, summary_text: str) -> str:
        """
        Compress a summary to fit context window.

        Delegates to ChatLLMService for actual LLM call.
        """
        if not summary_text:
            return summary_text

        # Delegate to ChatLLMService
        return await self.chat_llm_service.compress_summary(summary_text)

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
