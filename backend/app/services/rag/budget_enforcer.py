"""Budget Enforcer for Chat Context.

Applies character budget limits and trims context components in priority order:
  1. Retrieval chunks
  2. Summary compression
  3. Summary truncation
  4. Recent verbatim messages window

Pure logic except for calling memory.compress_summary (LLM). Easy to unit test with a fake memory object.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.utils.logging import logger


class BudgetEnforcer:
    def __init__(self):
        self.prompt_overhead_chars = 1200

    def _messages_to_str(self, msgs: List[Dict[str, Any]]) -> str:
        return "\n".join([f"{m['role'].title()}: {m['content']}" for m in msgs])

    def _chunks_to_str(self, chunks: List[Dict[str, Any]]) -> str:
        texts = []
        for i, c in enumerate(chunks, 1):
            # Extract filename from chunk_metadata (JSONB field) or fallback to document_id
            filename = "Unknown"
            if c.get('chunk_metadata'):
                metadata = c['chunk_metadata']
                # Handle both dict and string formats
                if isinstance(metadata, dict):
                    filename = metadata.get('document_filename', c.get('document_id', 'Unknown'))
                elif isinstance(metadata, str):
                    # If metadata came as JSON string, try to parse it
                    try:
                        import json
                        parsed = json.loads(metadata)
                        filename = parsed.get('document_filename', c.get('document_id', 'Unknown'))
                    except:
                        filename = c.get('document_id', 'Unknown')
            else:
                filename = c.get('document_id', 'Unknown')

            source_info = f"Source {i}: {filename}"
            if c.get('page_number'):
                source_info += f" (Page {c['page_number']})"
            texts.append(source_info + "\n" + c['text'])
        return "\n".join(texts)

    async def enforce(
        self,
        memory,
        user_message: str,
        summary_text: Optional[str],
        recent_messages: List[Dict[str, Any]],
        relevant_chunks: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Enforce budget limits with graceful degradation.

        Priority-based trimming:
        1. Trim retrieval chunks (keep minimum 2)
        2. Compress summary via LLM
        3. Hard truncate summary to 3000 chars
        4. Reduce recent messages window (keep minimum 2)

        If smart trimming fails, falls back to simple truncation.
        """
        try:
            effective_budget = min(settings.chat_max_input_chars, settings.llm_max_input_chars) - settings.chat_answer_reserve_chars
            if effective_budget <= 0:
                logger.warning("Effective budget <=0; skipping trims.")
                return summary_text, recent_messages, relevant_chunks

            user_chars = len(user_message)
            recent_chars = len(self._messages_to_str(recent_messages))
            summary_chars = len(summary_text) if summary_text else 0
            chunks_chars = len(self._chunks_to_str(relevant_chunks))
            total_chars = self.prompt_overhead_chars + user_chars + recent_chars + summary_chars + chunks_chars

            if total_chars <= effective_budget:
                logger.info("Budget within limits", extra={"total_chars": total_chars, "budget": effective_budget})
                return summary_text, recent_messages, relevant_chunks

            original = {
                "chunks": len(relevant_chunks),
                "recent_messages": len(recent_messages),
                "summary_chars": summary_chars,
                "total_chars": total_chars,
                "budget": effective_budget
            }

            # 1. Trim chunks
            min_chunks = 2
            while len(relevant_chunks) > min_chunks and total_chars > effective_budget:
                removed = relevant_chunks.pop()
                chunks_chars = len(self._chunks_to_str(relevant_chunks))
                total_chars = self.prompt_overhead_chars + user_chars + recent_chars + summary_chars + chunks_chars
                logger.debug("Trimmed chunk", extra={"removed_chunk_id": removed["id"], "total_chars": total_chars})

            # 2. Compress summary
            if total_chars > effective_budget and summary_text:
                summary_text = await memory.compress_summary(summary_text)
                summary_chars = len(summary_text)
                total_chars = self.prompt_overhead_chars + user_chars + recent_chars + summary_chars + chunks_chars
                logger.debug("Compressed summary", extra={"summary_chars": summary_chars, "total_chars": total_chars})

            # 3. Hard truncate summary
            if total_chars > effective_budget and summary_text:
                max_summary_chars = 3000
                if summary_chars > max_summary_chars:
                    summary_text = summary_text[:max_summary_chars] + "..."
                    summary_chars = len(summary_text)
                    total_chars = self.prompt_overhead_chars + user_chars + recent_chars + summary_chars + chunks_chars
                    logger.debug("Truncated summary", extra={"summary_chars": summary_chars, "total_chars": total_chars})

            # 4. Reduce recent window
            while total_chars > effective_budget and len(recent_messages) > 2:
                recent_messages = recent_messages[1:]
                recent_chars = len(self._messages_to_str(recent_messages))
                total_chars = self.prompt_overhead_chars + user_chars + recent_chars + summary_chars + chunks_chars
                logger.debug("Dropped recent message", extra={"recent_messages": len(recent_messages), "total_chars": total_chars})

            logger.info(
                "Applied budget trimming",
                extra={"before": original, "after": {"chunks": len(relevant_chunks), "recent_messages": len(recent_messages), "summary_chars": summary_chars, "total_chars": total_chars}}
            )
            return summary_text, recent_messages, relevant_chunks

        except Exception as e:
            logger.warning(
                f"Smart budget enforcement failed: {e}; applying fallback truncation",
                extra={"error_type": type(e).__name__},
                exc_info=True
            )

            # Graceful degradation: Simple truncation fallback
            try:
                return self._fallback_truncation(
                    user_message=user_message,
                    summary_text=summary_text,
                    recent_messages=recent_messages,
                    relevant_chunks=relevant_chunks,
                    effective_budget=effective_budget
                )
            except Exception as fallback_error:
                logger.error(
                    f"Fallback truncation also failed: {fallback_error}; returning original data",
                    exc_info=True
                )
                # Last resort: return original data (may exceed budget, but chat won't crash)
                return summary_text, recent_messages, relevant_chunks

    def _fallback_truncation(
        self,
        user_message: str,
        summary_text: Optional[str],
        recent_messages: List[Dict[str, Any]],
        relevant_chunks: List[Dict[str, Any]],
        effective_budget: int
    ) -> Tuple[Optional[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Simple fallback truncation when smart trimming fails.

        Strategy:
        - Keep 2 chunks (or 0 if user message + overhead exceeds budget)
        - Remove summary entirely
        - Keep last 2 messages
        - If still too large, truncate chunks to fit
        """
        logger.info("Applying fallback truncation strategy")

        user_chars = len(user_message)
        available = effective_budget - self.prompt_overhead_chars - user_chars

        if available <= 0:
            logger.warning("Budget too small even for fallback; returning minimal context")
            return None, [], []

        # Keep last 2 messages (prioritize recent context)
        fallback_messages = recent_messages[-2:] if len(recent_messages) >= 2 else recent_messages
        message_chars = len(self._messages_to_str(fallback_messages))
        available -= message_chars

        # Remove summary (simplest cut)
        fallback_summary = None

        # Keep top 2 chunks if space allows
        fallback_chunks = relevant_chunks[:2] if len(relevant_chunks) >= 2 else relevant_chunks
        chunks_text = self._chunks_to_str(fallback_chunks)
        chunks_chars = len(chunks_text)

        # If chunks don't fit, truncate chunk text
        if chunks_chars > available and fallback_chunks:
            max_chunk_chars = max(100, available // len(fallback_chunks))  # At least 100 chars per chunk
            for chunk in fallback_chunks:
                if len(chunk["text"]) > max_chunk_chars:
                    chunk["text"] = chunk["text"][:max_chunk_chars] + "...[truncated]"
                    logger.debug(f"Truncated chunk {chunk['id']} to {max_chunk_chars} chars")

        logger.info(
            "Fallback truncation applied",
            extra={
                "chunks": len(fallback_chunks),
                "messages": len(fallback_messages),
                "summary": "removed"
            }
        )

        return fallback_summary, fallback_messages, fallback_chunks
