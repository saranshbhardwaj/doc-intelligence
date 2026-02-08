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

    # -------- Summarization Decision --------
    async def maybe_summarize(
        self,
        session_id: str,
        history_messages: List[Dict[str, Any]],
        user_message: str
    ) -> Tuple[Optional[str], List[Dict[str, Any]], List[str]]:
        """
        Return (summary_text, recent_messages, key_facts) based on history & budgeting thresholds.

        Uses progressive summarization: instead of re-summarizing all history,
        only summarizes new messages since last summary.
        """
        if not history_messages:
            return None, [], []

        history_text = "\n".join([f"{m['role'].title()}: {m['content']}" for m in history_messages])
        est_history_tokens = self.estimate_tokens(history_text)
        est_user_tokens = self.estimate_tokens(user_message)

        # Estimate max input tokens from max chars (rough approximation: 1 token ≈ 4 chars)
        max_input_tokens = settings.llm_max_input_chars // 4 if settings.llm_max_input_chars else 0
        usage_ratio = (est_history_tokens + est_user_tokens) / max_input_tokens if max_input_tokens else 0

        summary_text: Optional[str] = None
        key_facts: List[str] = []
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
                    # Exact cache hit - use cached summary and facts
                    summary_text = cached.get("compressed") or cached.get("summary")
                    key_facts = cached.get("key_facts", [])
                    logger.info("Using cached conversation summary", extra={"session_id": session_id})
                elif not cached:
                    # Cache miss - try loading from database (persistent storage)
                    db_summary = self.session_repo.get_summary(session_id)
                    if db_summary:
                        logger.info(
                            "Loaded summary from database (cache miss)",
                            extra={"session_id": session_id}
                        )
                        # Warm the cache with DB data
                        self.cache.set(
                            session_id=session_id,
                            message_count=current_message_count,
                            summary=db_summary["summary"],
                            key_facts=db_summary["key_facts"],
                            last_summarized_index=db_summary["last_summarized_index"]
                        )
                        summary_text = db_summary["summary"]
                        key_facts = db_summary["key_facts"]
                    else:
                        # No summary in DB either - proceed to generate new one
                        pass
                else:
                    # Need to summarize
                    if cached:
                        # Progressive summarization: update existing summary with new messages
                        last_idx = cached.get("last_summarized_index", 0)
                        new_messages = older_messages[last_idx:]

                        if new_messages:
                            logger.info(
                                "Progressive summarization triggered",
                                extra={
                                    "session_id": session_id,
                                    "last_index": last_idx,
                                    "new_message_count": len(new_messages)
                                }
                            )
                            # Extract key facts from new messages
                            new_facts = await self.chat_llm_service.extract_key_facts(new_messages)

                            # Merge with existing facts (keep unique, limit to 10)
                            existing_facts = cached.get("key_facts", [])
                            key_facts = self._merge_key_facts(existing_facts, new_facts)

                            # Progressive summarization
                            previous_summary = cached.get("summary", "")
                            summary_text = await self.chat_llm_service.progressive_summarize(
                                previous_summary=previous_summary,
                                new_messages=new_messages,
                                key_facts=key_facts
                            )
                        else:
                            # No new messages to summarize
                            summary_text = cached.get("summary", "")
                            key_facts = cached.get("key_facts", [])
                    else:
                        # First summarization - summarize all older messages
                        logger.info(
                            "First summarization triggered",
                            extra={"session_id": session_id, "message_count": len(older_messages)}
                        )
                        summary_text = await self._summarize_messages(older_messages)
                        key_facts = await self.chat_llm_service.extract_key_facts(older_messages)

        return summary_text, recent_messages, key_facts

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
