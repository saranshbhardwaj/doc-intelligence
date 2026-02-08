"""Conversation Summary Cache

Provides simple get/set operations for cached conversation summaries to avoid
re-summarizing older chat history every turn. Uses Redis if available and
configured; falls back to in-memory ephemeral dictionary if Redis is not available.

Key design:
    cache key: chat:summary:<session_id>
    value JSON: {
        "message_count": int,
        "summary": str,
        "compressed": str,
        "key_facts": List[str],  # Preserved important facts
        "last_summarized_index": int,  # Index up to which we've summarized
        "created_at": iso
    }

Invalidation:
    - If current message_count (total messages so far) differs from cached message_count,
      older messages changed -> recompute summary.
    - TTL-based expiration from settings.chat_summary_cache_ttl_seconds.

Note: This cache intentionally does not persist across process restarts if Redis is disabled.
"""
from __future__ import annotations

from typing import Optional, Dict, Any, List
from datetime import datetime
from app.config import settings
from app.utils.logging import logger

try:
    import redis  # type: ignore
except Exception:
    redis = None

_IN_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}


class ConversationSummaryCache:
    def __init__(self):
        self.enabled = settings.chat_summary_cache_ttl_seconds > 0
        self.ttl = settings.chat_summary_cache_ttl_seconds
        if redis is not None and settings.use_redis_cache:
            try:
                self.client = redis.Redis.from_url(settings.redis_url)
            except Exception as e:
                logger.warning(f"Failed to init Redis for summary cache: {e}; using in-memory fallback")
                self.client = None
        else:
            self.client = None

    def _redis_key(self, session_id: str) -> str:
        return f"chat:summary:{session_id}"

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        if self.client:
            try:
                raw = self.client.get(self._redis_key(session_id))
                if not raw:
                    return None
                import json
                return json.loads(raw)
            except Exception as e:
                logger.debug(f"Redis summary cache get failed: {e}")
                return None
        # In-memory fallback
        entry = _IN_MEMORY_CACHE.get(session_id)
        if not entry:
            return None
        # TTL check
        created_at = datetime.fromisoformat(entry.get("created_at"))
        age = (datetime.utcnow() - created_at).total_seconds()
        if age > self.ttl:
            _IN_MEMORY_CACHE.pop(session_id, None)
            return None
        return entry

    def set(
        self,
        session_id: str,
        message_count: int,
        summary: str,
        compressed: Optional[str] = None,
        key_facts: Optional[List[str]] = None,
        last_summarized_index: Optional[int] = None
    ):
        """
        Cache a conversation summary with key facts.

        Args:
            session_id: Chat session ID
            message_count: Total message count when this summary was created
            summary: The summary text
            compressed: Optional compressed version of summary
            key_facts: List of important facts to preserve across summarizations
            last_summarized_index: Message index up to which we've summarized
        """
        if not self.enabled:
            return
        data = {
            "message_count": message_count,
            "summary": summary,
            "compressed": compressed or summary,
            "key_facts": key_facts or [],
            "last_summarized_index": last_summarized_index or 0,
            "created_at": datetime.utcnow().isoformat()
        }
        if self.client:
            try:
                import json
                self.client.setex(self._redis_key(session_id), self.ttl, json.dumps(data, ensure_ascii=False))
            except Exception as e:
                logger.debug(f"Redis summary cache set failed: {e}")
                # fall through to in-memory
        _IN_MEMORY_CACHE[session_id] = data

    def invalidate(self, session_id: str):
        if self.client:
            try:
                self.client.delete(self._redis_key(session_id))
            except Exception:
                pass
        _IN_MEMORY_CACHE.pop(session_id, None)
