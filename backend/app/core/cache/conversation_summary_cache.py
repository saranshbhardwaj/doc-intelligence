"""Conversation Summary Cache

Provides simple get/set operations for cached conversation summaries to avoid
re-summarizing older chat history every turn. Uses Redis if available and
configured; falls back to database (source of truth) if Redis is not available.

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

Note: The database (chat_sessions table) is the source of truth. Redis is an optimization layer.
"""
from __future__ import annotations

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.config import settings
from app.utils.logging import logger
from app.utils.metrics import SUMMARY_CACHE_HITS, SUMMARY_CACHE_MISSES

try:
    import redis
except Exception:
    redis = None

# Import centralized Redis connection pool
from app.core.redis_client import get_redis_pool


class ConversationSummaryCache:
    def __init__(self):
        self.enabled = settings.chat_summary_cache_ttl_seconds > 0
        self.ttl = settings.chat_summary_cache_ttl_seconds
        self.client = None

        if redis is not None and settings.use_redis_cache:
            try:
                # Use centralized connection pool with decode_responses=False for binary data
                pool = get_redis_pool(settings.redis_url, decode_responses=False)
                self.client = redis.Redis(connection_pool=pool)
            except Exception as e:
                logger.warning(f"Failed to init Redis for summary cache: {e}; using DB fallback")

    def _redis_key(self, session_id: str) -> str:
        return f"chat:summary:{session_id}"

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None

        # Try Redis first (fast path)
        if self.client:
            try:
                raw = self.client.get(self._redis_key(session_id))
                if raw:
                    SUMMARY_CACHE_HITS.inc()
                    return json.loads(raw)
            except Exception as e:
                logger.debug(f"Redis summary cache get failed: {e}")

        # Fallback: Load from DB (source of truth)
        result = self._get_from_db(session_id)
        if result:
            SUMMARY_CACHE_HITS.inc()  # Still a "hit" from DB
        else:
            SUMMARY_CACHE_MISSES.inc()
        return result

    def _get_from_db(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load summary from chat_sessions table (source of truth)."""
        from app.database import SessionLocal
        from app.db_models_chat import ChatSession

        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id
            ).first()

            if session and session.last_summary_text:
                return {
                    "message_count": session.message_count or 0,
                    "summary": session.last_summary_text,
                    "compressed": session.last_summary_text,  # Use same as summary
                    "key_facts": session.last_summary_key_facts or [],
                    "last_summarized_index": session.last_summarized_index or 0,
                    "created_at": session.last_summary_updated_at.isoformat() if session.last_summary_updated_at else None
                }
            return None
        except Exception as e:
            logger.warning(f"Failed to load summary from DB: {e}")
            return None
        finally:
            db.close()

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

        Always persists to DB (source of truth) and optionally caches in Redis.

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

        # Always persist to DB (source of truth)
        self._persist_to_db(
            session_id=session_id,
            summary=summary,
            key_facts=key_facts,
            last_summarized_index=last_summarized_index
        )

        # Also cache in Redis if available (optimization)
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
                self.client.setex(
                    self._redis_key(session_id),
                    self.ttl,
                    json.dumps(data, ensure_ascii=False)
                )
            except Exception as e:
                logger.debug(f"Redis summary cache set failed: {e}")
                # Redis is optimization, DB is source of truth - no need to fail

    def _persist_to_db(
        self,
        session_id: str,
        summary: str,
        key_facts: Optional[List[str]] = None,
        last_summarized_index: Optional[int] = None
    ):
        """Persist summary to chat_sessions table."""
        from app.database import SessionLocal
        from app.db_models_chat import ChatSession

        db = SessionLocal()
        try:
            session = db.query(ChatSession).filter(
                ChatSession.id == session_id
            ).first()

            if session:
                session.last_summary_text = summary
                session.last_summary_key_facts = key_facts or []
                session.last_summarized_index = last_summarized_index or 0
                session.last_summary_updated_at = datetime.utcnow()
                db.commit()
        except Exception as e:
            logger.warning(f"Failed to persist summary to DB: {e}")
            db.rollback()
        finally:
            db.close()

    def invalidate(self, session_id: str):
        """Invalidate cached summary (Redis only - DB remains as source of truth)."""
        if self.client:
            try:
                self.client.delete(self._redis_key(session_id))
            except Exception:
                pass
        # Note: We don't clear DB summary - it's the source of truth
        # If you need to clear DB summary, do it directly via session update
