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
from app.repositories.session_repository import SessionRepository

class ConversationMemory:
    def __init__(self, chat_llm_service: ChatLLMService):
        """
        Initialize conversation memory.

        Args:
            chat_llm_service: Chat LLM service for summarization operations
        """
        self.chat_llm_service = chat_llm_service
        self.cache = ConversationSummaryCache()
        self.session_repo = SessionRepository()

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

    # -------- Conversation Budget Check --------
    def _exceeds_conversation_budget(
        self,
        history_messages: List[Dict[str, Any]],
        cached: Optional[Dict[str, Any]]
    ) -> bool:
        """
        Check if the conversation portion we'd send to the LLM exceeds the char budget.

        When a summary exists: measures (summary + last N verbatim messages).
        When no summary yet: measures all history messages combined.
        """
        verbatim_count = settings.chat_verbatim_message_count
        verbatim = (
            history_messages[-verbatim_count:]
            if verbatim_count < len(history_messages)
            else history_messages
        )

        if cached and cached.get("summary"):
            summary_chars = len(cached["summary"])
            recent_chars = sum(len(m["content"]) for m in verbatim)
            convo_chars = summary_chars + recent_chars
        else:
            # No summary yet — full history is what we'd send
            convo_chars = sum(len(m["content"]) for m in history_messages)

        return convo_chars > settings.chat_conversation_char_budget

    # -------- Summarization Pre-check --------
    def will_summarize(
        self,
        session_id: str,
        history_messages: List[Dict[str, Any]]
    ) -> bool:
        """Quick pre-check: will maybe_summarize() trigger compaction?

        Checks whether the conversation portion we'd send exceeds chat_conversation_char_budget.
        Used to emit a 'Compacting conversation history...' thinking event before
        the expensive maybe_summarize() call. Cache lookup only — no LLM/DB writes.
        """
        if not history_messages or len(history_messages) < settings.chat_summary_min_messages:
            return False
        cached = self.cache.get(session_id)
        return self._exceeds_conversation_budget(history_messages, cached)

    # -------- Summarization Decision --------
    async def maybe_summarize(
        self,
        session_id: str,
        history_messages: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
        """
        Return (summary_text, recent_messages, key_facts).

        Uses Claude-style compaction: compact when (summary + recent messages) exceeds
        chat_conversation_char_budget. Between compaction points, reuse cached summary
        with no LLM call. Only compact when the conversation portion actually overflows.
        """
        if not history_messages:
            return None, [], []

        verbatim_count = settings.chat_verbatim_message_count
        verbatim_msgs = (
            history_messages[-verbatim_count:]
            if verbatim_count < len(history_messages)
            else history_messages
        )

        cached = self.cache.get(session_id)

        # Decide whether compaction is needed
        should_compact = (
            len(history_messages) >= settings.chat_summary_min_messages
            and self._exceeds_conversation_budget(history_messages, cached)
        )

        if not should_compact:
            # Under budget — return cached summary (if any) with verbatim messages
            if cached and cached.get("summary"):
                logger.info("Using cached conversation summary", extra={"session_id": session_id})
                return cached["summary"], verbatim_msgs, cached.get("key_facts", [])
            else:
                # No summary yet and under budget — return full history verbatim
                return None, history_messages, []

        # --- Compaction needed ---
        older_messages = (
            history_messages[:-verbatim_count]
            if verbatim_count < len(history_messages)
            else []
        )
        if not older_messages:
            return None, history_messages, []

        summary_text: Optional[str] = None
        key_facts: List[str] = []

        if cached and cached.get("summary"):
            # Progressive compaction: fold new messages into existing summary
            last_idx = cached.get("last_summarized_index", 0)

            # Guard: clamp to valid range to catch DB drift / message deletion
            if last_idx < 0 or last_idx > len(older_messages):
                logger.warning(
                    "last_summarized_index out of bounds — clamping",
                    extra={
                        "session_id": session_id,
                        "last_idx": last_idx,
                        "older_messages_len": len(older_messages),
                    }
                )
                last_idx = len(older_messages)

            new_messages = older_messages[last_idx:]

            if new_messages:
                logger.info(
                    "Progressive summarization triggered",
                    extra={
                        "session_id": session_id,
                        "last_index": last_idx,
                        "new_message_count": len(new_messages),
                    }
                )
                new_facts = await self.chat_llm_service.extract_key_facts(new_messages)
                key_facts = self._merge_key_facts(cached.get("key_facts", []), new_facts)
                summary_text = await self.chat_llm_service.progressive_summarize(
                    previous_summary=cached["summary"],
                    new_messages=new_messages,
                    key_facts=key_facts,
                )
            else:
                # Nothing new to fold — reuse existing summary
                logger.info(
                    "Progressive summarization skipped — no new messages since last summary",
                    extra={"session_id": session_id, "last_idx": last_idx},
                )
                summary_text = cached["summary"]
                key_facts = cached.get("key_facts", [])
        else:
            # Cache miss — check DB before generating a fresh summary
            db_summary = self.session_repo.get_summary(session_id)
            if db_summary:
                logger.info(
                    "Loaded summary from database (cache miss)",
                    extra={"session_id": session_id}
                )
                self.cache.set(
                    session_id=session_id,
                    message_count=len(history_messages),
                    summary=db_summary["summary"],
                    key_facts=db_summary["key_facts"],
                    last_summarized_index=db_summary["last_summarized_index"]
                )
                summary_text = db_summary["summary"]
                key_facts = db_summary["key_facts"]
            else:
                # First compaction — summarize all older messages
                logger.info(
                    "First summarization triggered",
                    extra={"session_id": session_id, "message_count": len(older_messages)}
                )
                summary_text = await self._summarize_messages(older_messages)
                key_facts = await self.chat_llm_service.extract_key_facts(older_messages)

        return summary_text, verbatim_msgs, key_facts

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
    def cache_summary(
        self,
        session_id: str,
        message_count: int,
        summary_text: str,
        key_facts: Optional[List[str]] = None,
        last_summarized_index: Optional[int] = None
    ):
        """
        Persist conversation summary to database and cache.

        Database is source of truth (survives restarts), cache is fast read layer.

        Args:
            session_id: Chat session ID
            message_count: Total message count when this summary was created
            summary_text: The summary text
            key_facts: List of important facts to preserve
            last_summarized_index: Index up to which we've summarized
        """
        cached = self.cache.get(session_id)
        if not summary_text:
            return
        if cached and cached.get("message_count") == message_count:
            return

        # Calculate last summarized index if not provided
        if last_summarized_index is None:
            # Default: summarized up to (total - verbatim)
            verbatim_count = settings.chat_verbatim_message_count
            last_summarized_index = max(0, message_count - verbatim_count)

        # Save to DATABASE first (source of truth)
        self.session_repo.update_summary(
            session_id=session_id,
            summary_text=summary_text,
            key_facts=key_facts or [],
            last_summarized_index=last_summarized_index
        )

        # Then cache in REDIS (fast reads)
        self.cache.set(
            session_id=session_id,
            message_count=message_count,
            summary=summary_text,
            compressed=summary_text,
            key_facts=key_facts or [],
            last_summarized_index=last_summarized_index
        )
        logger.info(
            "Persisted conversation summary (DB + cache)",
            extra={
                "session_id": session_id,
                "message_count": message_count,
                "key_facts_count": len(key_facts or []),
                "last_summarized_index": last_summarized_index
            }
        )

    # -------- Key Facts Merge --------
    def _merge_key_facts(self, existing_facts: List[str], new_facts: List[str]) -> List[str]:
        """
        Merge existing key facts with new ones, keeping unique facts and limiting to 10.

        Args:
            existing_facts: Previous key facts list
            new_facts: Newly extracted key facts

        Returns:
            Merged list of unique facts (max 10 items)
        """
        # Keep unique facts (case-insensitive comparison)
        seen = set()
        merged = []

        for fact in existing_facts + new_facts:
            fact_lower = fact.lower().strip()
            if fact_lower and fact_lower not in seen:
                seen.add(fact_lower)
                merged.append(fact)

        # Limit to 10 most recent facts (prioritize new facts)
        return merged[:10]
