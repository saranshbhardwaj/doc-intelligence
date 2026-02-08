"""Chat persistence helpers for saving and loading messages."""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from app.repositories.chat_repository import ChatRepository
from app.config import settings
from app.utils.logging import logger
from app.utils.metrics_recorder import record_chat_message
from app.utils.metrics import LLM_TOKEN_USAGE, LLM_CACHE_HITS, LLM_CACHE_MISSES


class ChatPersistence:
    def __init__(self, chat_repo: Optional[ChatRepository] = None):
        self.chat_repo = chat_repo or ChatRepository()

    async def save_chat_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        source_chunks: List[str],
        usage_data: Optional[Dict[str, Any]] = None,
        comparison_metadata: Optional[str] = None,
        citation_context: Optional[Dict[str, Any]] = None,
        org_id: Optional[str] = None
    ):
        """
        Save user message and assistant response to database.

        Args:
            session_id: Chat session ID
            user_message: User's message
            assistant_message: Assistant's response
            source_chunks: List of chunk IDs used for response
            usage_data: Optional token usage data from LLM API
            comparison_metadata: Optional serialized comparison context
            citation_context: Optional citation context for frontend resolution
        """
        import json

        try:
            # Get current message count for ordering
            message_count = self.chat_repo.get_message_count(session_id)

            # Edge case: Validate message_count
            if message_count is None:
                logger.warning(
                    f"get_message_count returned None for session {session_id}, defaulting to 0",
                    extra={"session_id": session_id}
                )
                message_count = 0

            # Save user message
            user_msg_saved = self.chat_repo.save_message(
                session_id=session_id,
                role="user",
                content=user_message,
                message_index=message_count,
                retrieval_query=user_message
            )

            # Record metrics
            record_chat_message(role="user", org_id=org_id)

            # Edge case: Check if user message save succeeded
            if not user_msg_saved:
                logger.error(
                    "Failed to save user message to database",
                    extra={"session_id": session_id}
                )
                raise ValueError("Failed to save user message")

            # Calculate token usage and cost
            tokens_used = None
            cost_usd = None
            model_used = settings.synthesis_llm_model

            # Initialize token variables with defaults (will be overridden if usage_data provided)
            input_tokens = 0
            output_tokens = 0
            cache_read_tokens = 0
            cache_creation_tokens = 0

            if usage_data:
                input_tokens = usage_data.get("input_tokens", 0) or 0
                output_tokens = usage_data.get("output_tokens", 0) or 0
                cache_read_tokens = usage_data.get("cache_read_input_tokens", 0) or 0
                cache_creation_tokens = usage_data.get("cache_creation_input_tokens", 0) or 0

                # Total tokens (input + output)
                tokens_used = input_tokens + output_tokens

                # Get model from usage data if available
                model_used = usage_data.get("model", settings.synthesis_llm_model)

                # Calculate cost based on model pricing (Haiku 3.5 pricing as of 2025)
                # Input: $0.25 per MTok, Output: $1.25 per MTok
                # Cache write: $0.30 per MTok, Cache read: $0.03 per MTok
                input_cost = (input_tokens / 1_000_000) * 0.25
                output_cost = (output_tokens / 1_000_000) * 1.25
                cache_write_cost = (cache_creation_tokens / 1_000_000) * 0.30
                cache_read_cost = (cache_read_tokens / 1_000_000) * 0.03

                cost_usd = input_cost + output_cost + cache_write_cost + cache_read_cost

                logger.info(
                    "Token usage for chat message",
                    extra={
                        "session_id": session_id,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "cache_read_tokens": cache_read_tokens,
                        "cache_creation_tokens": cache_creation_tokens,
                        "total_tokens": tokens_used,
                        "cost_usd": round(cost_usd, 6),
                        "model": model_used
                    }
                )

                # Record Prometheus metrics for token usage
                try:
                    if input_tokens:
                        LLM_TOKEN_USAGE.labels(model=model_used, token_type="input").inc(input_tokens)
                    if output_tokens:
                        LLM_TOKEN_USAGE.labels(model=model_used, token_type="output").inc(output_tokens)
                    if cache_read_tokens:
                        LLM_TOKEN_USAGE.labels(model=model_used, token_type="cache_read").inc(cache_read_tokens)
                        LLM_CACHE_HITS.inc()
                    else:
                        LLM_CACHE_MISSES.inc()
                    if cache_creation_tokens:
                        LLM_TOKEN_USAGE.labels(model=model_used, token_type="cache_write").inc(cache_creation_tokens)
                except Exception as e:
                    logger.warning(f"Failed to record LLM token metrics: {e}", exc_info=True)

            # Serialize citation context if provided
            citation_metadata = json.dumps(citation_context) if citation_context else None

            # Save assistant message
            assistant_msg_saved = self.chat_repo.save_message(
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                message_index=message_count + 1,
                source_chunks=json.dumps(source_chunks),
                num_chunks_retrieved=len(source_chunks),
                model_used=model_used,
                tokens_used=tokens_used,
                cost_usd=cost_usd,
                comparison_metadata=comparison_metadata,
                citation_metadata=citation_metadata,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                cache_write_tokens=cache_creation_tokens
            )

            # Record metrics
            record_chat_message(role="assistant", org_id=org_id)

            # Edge case: Check if assistant message save succeeded
            if not assistant_msg_saved:
                logger.error(
                    "Failed to save assistant message to database",
                    extra={"session_id": session_id}
                )
                raise ValueError("Failed to save assistant message")

            # Update session message count (increment by 2 for user + assistant messages)
            count_updated = self.chat_repo.increment_message_count(session_id, increment=2)

            # Edge case: Check if message count increment succeeded
            if not count_updated:
                logger.warning(
                    "Failed to increment message count for session",
                    extra={"session_id": session_id}
                )
                # Don't raise - messages are saved, count mismatch is recoverable

            logger.info(
                "Saved chat messages",
                extra={
                    "session_id": session_id,
                    "user_msg_length": len(user_message),
                    "assistant_msg_length": len(assistant_message),
                    "chunks_used": len(source_chunks)
                }
            )

        except Exception as save_error:
            # Edge case: Message saving failed - log comprehensive error
            logger.error(
                f"Failed to save chat messages: {save_error}",
                extra={
                    "session_id": session_id,
                    "error_type": type(save_error).__name__,
                    "user_msg_length": len(user_message),
                    "assistant_msg_length": len(assistant_message)
                },
                exc_info=True
            )
            raise

    def get_chat_history(
        self,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get chat history for a session.

        Args:
            session_id: Chat session ID
            limit: Optional limit on number of messages

        Returns:
            List of message dicts (ordered by message_index)
        """
        messages = self.chat_repo.get_messages(session_id, limit=limit)

        return [
            {
                "role": msg.role,
                "content": msg.content,
                "message_index": msg.message_index,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "source_chunks": msg.source_chunks,
                "num_chunks_retrieved": msg.num_chunks_retrieved
            }
            for msg in messages
        ]
