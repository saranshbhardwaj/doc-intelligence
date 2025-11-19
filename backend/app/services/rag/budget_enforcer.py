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
            source_info = f"Source {i}: {c['filename']}"
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
            logger.warning(f"Budget enforcement failed: {e}; skipping trims.")
            return summary_text, recent_messages, relevant_chunks
