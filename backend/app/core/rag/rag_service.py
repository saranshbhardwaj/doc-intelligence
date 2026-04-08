# backend/app/services/rag/rag_service.py
"""RAGService orchestrates chat flow using modular components.

Responsibilities limited to orchestration:
 1. Load & maybe summarize history via ConversationMemory
 2. Perform hybrid retrieval (semantic + keyword search)
 3. Enforce budget trims
 4. Build final prompt
 5. Stream LLM response
 6. Persist messages

Other concerns (prompt construction, memory management, budget logic) are delegated.
"""
from typing import List, Dict, Any, Optional, AsyncIterator, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db_models_chat import DocumentChunk, CollectionDocument
from app.repositories.document_repository import DocumentRepository
from app.core.embeddings import get_embedding_provider
from app.core.llm.llm_client import LLMClient
from app.core.chat.llm_service import ChatLLMService
from app.config import settings
from app.utils.logging import logger
from app.utils.metrics import CHAT_LATENCY_SECONDS
from app.core.rag.prompt_builder import PromptBuilder
from app.core.rag.memory import ConversationMemory
from app.core.rag.budget_enforcer import BudgetEnforcer
from app.core.rag.hybrid_retriever import HybridRetriever
from app.core.rag.reranker import Reranker
from app.core.rag.comparison_retriever import ComparisonRetriever
from app.core.rag.query_understanding import (
    QueryUnderstandingService,
    QueryType,
    ScopeMode,
    is_narrow_explicit_fact_lookup,
)
from app.core.rag.fact_extractor import FactExtractor
from app.core.rag.context_expander import ContextExpander
from app.utils.chunk_metadata import validate_and_normalize_chunks
from app.core.rag.chat_persistence import ChatPersistence
from app.core.rag.comparison_flow import ComparisonChatHandler
from app.core.rag.document_matching import DocumentMatcher
from app.core.rag.low_signal import is_low_signal_message, low_signal_response
from app.core.rag.eval_contract import (
    RAG_EVAL_CONTRACT_VERSION,
    serialize_chunk_for_eval,
    serialize_query_understanding,
)
from app.repositories.chat_repository import ChatRepository

# Adaptive retrieval sizing by query type: (min_candidates, max_candidates, min_top_k, max_top_k)
# Defaults: 15 candidates, 8 final (reduced from 18/12 for better quality per research)
# 6-9 chunks is the quality sweet spot; chunks 9-12 add noise without improving relevance
_RETRIEVAL_SIZING = {
    QueryType.DATA_EXTRACTION: (20, None, 8, None),    # financial tables need retrieval breadth, but 8 final chunks is optimal per research
    QueryType.SUMMARIZATION:   (12, 18, 6, 8),         # breadth but fewer final
    QueryType.ENTITY_LOOKUP:   (10, 15, 5, 7),         # narrow lookups
    # GENERAL_QA and COMPARISON use defaults (15 → 8)
}
_DOC_SCOPE_MATCH_THRESHOLD = 0.70
_DATA_EXTRACTION_SCOPE_CONFIDENCE_THRESHOLD = 0.65
_SCOPE_GUARDRAIL_MIN_CONFIDENCE = 0.55
import asyncio  # noqa: E402
import functools  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from app.services.service_locator import get_reranker  # noqa: E402


class RAGService:
    """
    RAG service for real-time chat responses.

    Workflow:
    1. Hybrid retrieval: Semantic (vector) + Keyword (FTS) search → 20 candidates
    2. Re-ranking: Cross-encoder re-ranking with optional compression → Top 10
    3. Budget enforcement: Trim context to fit within LLM limits
    4. Build prompt: Assemble context + history + user message
    5. Stream response: Generate answer from Claude
    6. Save history: Persist messages to database
    """

    def __init__(self, db: Session, reranker: Reranker | None = None, capture_io_log: bool = False):
        """
        Initialize RAG service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.embedder = get_embedding_provider()
        self.llm_client = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.synthesis_llm_model,
            max_tokens=settings.synthesis_llm_max_tokens,
            max_input_chars=settings.llm_max_input_chars,
            timeout_seconds=settings.synthesis_llm_timeout_seconds,
        )

        # Initialize chat LLM service for conversation operations
        self.chat_llm_service = ChatLLMService(self.llm_client)

        # Inject modular components
        self.prompt_builder = PromptBuilder(prompt_version=settings.rag_prompt_version)
        self.memory = ConversationMemory(self.chat_llm_service)
        self.budget = BudgetEnforcer()
        self.hybrid_retriever = HybridRetriever(db)  # Hybrid retrieval (semantic + keyword)
        self.query_understanding = QueryUnderstandingService()  # Query understanding & enhancement

        # Re-ranker (cross-encoder based, optional via config)
        self.reranker = reranker if reranker is not None else (get_reranker() if settings.rag_use_reranker else None)

        # Comparison retriever (for multi-document comparison)
        self.comparison_retriever = ComparisonRetriever(
            db=db,
            hybrid_retriever=self.hybrid_retriever,
            reranker=self.reranker
        )

        # Fact extractor (for Map-Reduce comparison flow)
        self.fact_extractor = FactExtractor(prompt_version=settings.rag_prompt_version)

        # Context expander (for expanding chunks with related context)
        self.context_expander = ContextExpander()

        # Persistence helper
        self.persistence = ChatPersistence()
        self.chat_repo = ChatRepository()

        self.capture_io_log = capture_io_log
        if capture_io_log:
            from app.repositories.io_log_repository import IOLogRepository
            self._io_log_repo = IOLogRepository()
        else:
            self._io_log_repo = None

        # Comparison context for SSE emission (set during comparison queries)
        self.last_comparison_context = None

        # Citation context for SSE emission (set during general chat queries)
        self.last_citation_context = None

        # Saved message IDs from last persistence call — emitted in done event
        self.last_saved_message_ids = (None, None)  # (user_msg_id, assistant_msg_id)

        # Document matching helper
        self.document_matcher = DocumentMatcher(db)
        self.document_repo = DocumentRepository()

        # Comparison handler
        self.comparison_handler = ComparisonChatHandler(
            db=db,
            comparison_retriever=self.comparison_retriever,
            fact_extractor=self.fact_extractor,
            prompt_builder=self.prompt_builder,
            llm_client=self.llm_client,
            save_messages=self.persistence.save_chat_messages,
            on_comparison_context=self._set_comparison_context,
            on_citation_context=self._set_citation_context_from_chunks,
            capture_io_log=capture_io_log,
            io_log_repo=self._io_log_repo,
        )

    def _set_comparison_context(self, comparison_data: Dict):
        self.last_comparison_context = comparison_data

    def _set_citation_context_from_chunks(self, chunks: List[Dict]) -> Dict:
        """Build and store citation context from comparison chunks for SSE emission.

        Returns the built context so callers (e.g. comparison_flow) can persist it.
        """
        self.last_citation_context = self._build_citation_context(chunks)
        return self.last_citation_context

    async def chat(
        self,
        session_id: str,
        collection_id: Optional[str],
        user_message: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        force_comparison: Optional[bool] = None  # NEW: Skip detection if set (True=force comparison, False=skip comparison)
    ) -> AsyncIterator[str]:
        """
        Generate streaming chat response using RAG with hybrid retrieval + re-ranking.

        Pipeline:
        1. Hybrid retrieval: Semantic + Keyword search (20 candidates)
        2. Re-ranking: Cross-encoder with optional compression (top 10)
        3. Budget enforcement: Trim to fit context window
        4. Build prompt and stream response

        Args:
            session_id: Chat session ID
            collection_id: Optional collection ID to search within (if None, uses document_ids filter)
            user_message: User's question/message
            user_id: Optional user ID for logging
            document_ids: Optional filter by specific documents (required if collection_id is None)
            force_comparison: Skip detection if set (True=force comparison, False=skip comparison, None=auto-detect)

        Yields:
            Streaming response chunks from Claude
        """
        # Edge case: Validate user_message is not empty
        if not user_message or not user_message.strip():
            logger.warning(
                "Empty user message received",
                extra={"session_id": session_id}
            )
            raise ValueError("User message cannot be empty")

        # STEP 1: History & optional summarization via memory component
        start_time = time.monotonic()
        stage_timings_ms: Dict[str, float] = {}
        history_messages = self.memory.load_history(session_id)

        # Summarization happens silently — don't surface internal detail to users
        if self.memory.will_summarize(session_id, history_messages):
            pass

        summary_text, recent_messages, key_facts = await self.memory.maybe_summarize(session_id, history_messages)

        # STEP 2: Short-circuit low-signal messages (skip retrieval/rerank)
        if is_low_signal_message(user_message):
            assistant_message = low_signal_response(user_message)
            yield ("chunk", assistant_message)
            saved_ids = await self.persistence.save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=assistant_message,
                source_chunks=[],
                usage_data=None,
                org_id=org_id
            )
            self.last_saved_message_ids = saved_ids
            self.last_comparison_context = None
            return

        # STEP 3: Query Understanding (LLM-powered analysis)
        yield ("thinking", "Understanding your question...")

        # Load document metadata for query understanding context
        doc_info = []
        if document_ids:
            doc_info = self.document_repo.get_doc_info_by_ids(document_ids)

        doc_filenames = [d["filename"] for d in doc_info]

        # Analyze query with LLM (cheap Haiku call)
        # Pass recent_messages so the model can detect follow-ups and rewrite queries
        query_understanding_start = time.monotonic()
        understanding = await self.query_understanding.understand(
            query=user_message,
            document_filenames=doc_filenames,
            recent_messages=recent_messages if recent_messages else None,
        )
        query_understanding_ms = round((time.monotonic() - query_understanding_start) * 1000, 2)
        stage_timings_ms["query_understanding"] = query_understanding_ms
        logger.info(
            "Query understanding latency",
            extra={
                "session_id": session_id,
                "query_understanding_ms": query_understanding_ms,
                "query_type": understanding.query_type.value
            }
        )

        # Decide whether to include conversation history in the prompt.
        # Standalone questions (needs_history=False) don't benefit from history —
        # omitting it improves cache hit rate and removes irrelevant context.
        # Always include history for the first 2 turns (session may not have warmed up yet).
        include_history = (
            understanding.needs_history
            or len(history_messages) <= 2
        )

        # Use rewritten query for retrieval when the model produced one (follow-up rewrites).
        # Keep original user_message for the USER QUESTION section of the prompt.
        retrieval_query = (
            understanding.rewritten_query
            if understanding.needs_history and understanding.rewritten_query
            else understanding.reformulated_query
        )
        narrow_explicit_fact_lookup = is_narrow_explicit_fact_lookup(understanding)

        logger.info(
            "History and retrieval query decision",
            extra={
                "session_id": session_id,
                "include_history": include_history,
                "needs_history": understanding.needs_history,
                "has_rewritten_query": bool(understanding.rewritten_query),
                "history_messages_count": len(history_messages),
                "query_type": understanding.query_type.value if understanding.query_type else None,
                "scope_mode": getattr(getattr(understanding, "scope_mode", None), "value", None),
                "scope_confidence": getattr(understanding, "scope_confidence", None),
                "target_property_names": (getattr(understanding, "target_property_names", []) or [])[:3],
                "target_geo_city": getattr(understanding, "target_geo_city", None),
                "target_geo_state": getattr(understanding, "target_geo_state", None),
                "confidence": understanding.confidence,
                "data_fields_count": len(understanding.data_fields or []),
                "data_fields": (understanding.data_fields or [])[:5],
                "entity_types": [e.entity_type for e in (understanding.entities or [])],
                "narrow_explicit_fact_lookup": narrow_explicit_fact_lookup,
            }
        )

        # STEP 4: Adaptive retrieval sizing based on query intent
        retrieval_candidates = settings.rag_retrieval_candidates
        final_top_k = settings.rag_final_top_k
        if understanding.confidence is None or understanding.confidence >= 0.4:
            sizing = _RETRIEVAL_SIZING.get(understanding.query_type)
            if sizing:
                min_c, max_c, min_k, max_k = sizing
                retrieval_candidates = max(min_c, retrieval_candidates) if max_c is None else max(min_c, min(retrieval_candidates, max_c))
                final_top_k = max(min_k, final_top_k) if max_k is None else max(min_k, min(final_top_k, max_k))

        logger.info(
            "Adaptive retrieval sizing",
            extra={
                "session_id": session_id,
                "query_type": understanding.query_type.value,
                "confidence": understanding.confidence,
                "retrieval_candidates": retrieval_candidates,
                "final_top_k": final_top_k
            }
        )

        # STEP 5: Branch to comparison flow if detected (or forced) and multiple documents available
        should_compare = (
            (force_comparison is True) or
            (force_comparison is None and understanding.query_type == QueryType.COMPARISON)
        )

        if should_compare and document_ids and len(document_ids) >= 2 and getattr(settings, 'comparison_enabled', True) and force_comparison is not False:
            # ≤3 docs in session: proceed automatically
            if len(document_ids) <= 3:
                final_doc_ids = document_ids
                logger.debug(
                    "Auto-proceeding with comparison (≤3 documents)",
                    extra={
                        "session_id": session_id,
                        "num_docs": len(document_ids)
                    }
                )

            else:
                # >3 docs: check if user mentioned specific documents
                matched_ids = self.document_matcher.match_entities_to_documents(understanding.entities, doc_info)

                # User mentioned 2-3 specific docs: use them directly
                if matched_ids and len(matched_ids) >= 2 and len(matched_ids) <= 3:
                    final_doc_ids = matched_ids
                    logger.debug(
                        "Auto-proceeding with user-mentioned documents (2-3 docs)",
                        extra={
                            "session_id": session_id,
                            "num_docs": len(matched_ids)
                        }
                    )

                # User mentioned >3 specific docs: ask user to select up to 3
                elif matched_ids and len(matched_ids) > 3:
                    logger.debug(
                        f"User mentioned {len(matched_ids)} documents, requesting selection",
                        extra={
                            "session_id": session_id,
                            "mentioned_count": len(matched_ids)
                        }
                    )

                    # Build document list from matched IDs
                    selection_docs = [
                        {"id": d["id"], "name": d["filename"]}
                        for d in doc_info if d["id"] in matched_ids
                    ]

                    selection_event = {
                        "type": "selection_needed",
                        "documents": selection_docs,
                        "pre_selected": matched_ids[:3],  # Pre-select first 3
                        "original_query": user_message,
                        "message": f"You mentioned {len(matched_ids)} documents. Please select up to 3 to compare:"
                    }
                    yield ("comparison_selection", selection_event)
                    return  # Wait for user selection

                # No specific docs mentioned: ask user to select from all session docs
                else:
                    logger.debug(
                        f"No specific documents mentioned, requesting selection from all {len(document_ids)} docs",
                        extra={
                            "session_id": session_id,
                            "total_docs": len(document_ids)
                        }
                    )

                    # Build document list from all session docs
                    selection_docs = [
                        {"id": d["id"], "name": d["filename"]}
                        for d in doc_info
                    ]

                    selection_event = {
                        "type": "selection_needed",
                        "documents": selection_docs,
                        "pre_selected": [],  # No pre-selection
                        "original_query": user_message,
                        "message": "Select 2-3 documents to compare:"
                    }
                    yield ("comparison_selection", selection_event)
                    return  # Wait for user selection

            logger.debug(
                f"Comparison query proceeding with {len(final_doc_ids)} documents",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "num_docs": len(final_doc_ids),
                    "understanding_type": understanding.query_type.value if understanding.query_type else "forced"
                }
            )

            yield ("thinking", "Finding relevant context...")
            
            async for event in self.comparison_handler.handle(
                session_id=session_id,
                collection_id=collection_id,
                user_message=user_message,
                user_id=user_id,
                document_ids=final_doc_ids,
                summary_text=summary_text,
                recent_messages=recent_messages,
                query_understanding=understanding,
                include_history=include_history,
            ):
                yield event  # Already a (event_type, data) tuple
            self.last_comparison_context = None
            return  # Exit after comparison flow

        # ------------------------------------------------------------------
        # STEP 5b: Document-scoped retrieval for entity-targeted queries.
        # When the user asks about a specific named document (SUMMARIZATION /
        # ENTITY_LOOKUP) and exactly one document matches with high confidence,
        # restrict retrieval to that document so short/sparse docs aren't
        # outranked by denser documents in the reranker.
        scope_mode = getattr(getattr(understanding, "scope_mode", None), "value", None) or ScopeMode.AMBIGUOUS.value
        scope_confidence = getattr(understanding, "scope_confidence", 0.0) or 0.0
        scope_target_ids = self._match_scope_targets_to_documents(understanding, doc_info)

        # If scope is ambiguous for non-comparison queries across multiple docs,
        # ask the user to select intended documents.
        if (
            document_ids
            and len(document_ids) > 1
            and understanding.query_type != QueryType.COMPARISON
            and scope_mode == ScopeMode.AMBIGUOUS.value
            and scope_confidence >= 0.45
        ):
            selection_docs = [{"id": d["id"], "name": d["filename"]} for d in doc_info]
            pre_selected = [doc_id for doc_id in scope_target_ids if doc_id in {d["id"] for d in doc_info}][:3]
            selection_event = {
                "type": "selection_needed",
                "documents": selection_docs,
                "pre_selected": pre_selected,
                "original_query": user_message,
                "message": "Your query could refer to multiple documents. Select one or more documents to continue:",
            }
            yield ("comparison_selection", selection_event)
            return

        scoped_doc_ids = document_ids
        did_scope_to_single_doc = False
        allow_data_extraction_scope = (
            understanding.query_type == QueryType.DATA_EXTRACTION
            and narrow_explicit_fact_lookup
            and scope_mode not in {ScopeMode.MULTI_DOC.value, ScopeMode.GLOBAL.value}
            and (
                understanding.confidence is None
                or understanding.confidence >= _DATA_EXTRACTION_SCOPE_CONFIDENCE_THRESHOLD
            )
        )
        if (
            document_ids
            and len(document_ids) > 1
            and understanding.entities
            and (
                understanding.query_type in (QueryType.SUMMARIZATION, QueryType.ENTITY_LOOKUP)
                or allow_data_extraction_scope
            )
        ):
            # Scope-mode single_doc has priority when we have exactly one target match.
            if scope_mode == ScopeMode.SINGLE_DOC.value and len(scope_target_ids) == 1:
                scoped_doc_ids = [scope_target_ids[0]]
                did_scope_to_single_doc = True
                matched_filename = next((d["filename"] for d in doc_info if d["id"] == scope_target_ids[0]), None)
                logger.info(
                    "Document-scoped retrieval activated (scope_mode=single_doc)",
                    extra={
                        "session_id": session_id,
                        "matched_doc": matched_filename,
                        "query_type": understanding.query_type.value,
                        "scope_confidence": scope_confidence,
                        "narrow_explicit_fact_lookup": narrow_explicit_fact_lookup,
                    }
                )
            else:
                matches = self.document_matcher.match_entities_with_scores(
                    understanding.entities, doc_info
                )
                high_conf = [m for m in matches if m["score"] >= _DOC_SCOPE_MATCH_THRESHOLD]
                if len(high_conf) == 1:
                    scoped_doc_ids = [high_conf[0]["id"]]
                    did_scope_to_single_doc = True
                    logger.info(
                        "Document-scoped retrieval activated",
                        extra={
                            "session_id": session_id,
                            "matched_doc": high_conf[0]["filename"],
                            "score": high_conf[0]["score"],
                            "query_type": understanding.query_type.value,
                            "narrow_explicit_fact_lookup": narrow_explicit_fact_lookup,
                        }
                    )

        already_single_doc_scope = bool(document_ids and len(document_ids) == 1)

        if (did_scope_to_single_doc or already_single_doc_scope) and narrow_explicit_fact_lookup:
            retrieval_candidates = max(
                1,
                min(retrieval_candidates, settings.rag_scoped_retrieval_candidates)
            )
            final_top_k = max(
                1,
                min(final_top_k, settings.rag_scoped_final_top_k)
            )
            logger.info(
                "Scoped retrieval budget applied",
                extra={
                    "session_id": session_id,
                    "retrieval_candidates": retrieval_candidates,
                    "final_top_k": final_top_k,
                    "scope_source": "matcher" if did_scope_to_single_doc else "session_single_doc",
                }
            )

        # ------------------------------------------------------------------
        # STEP 1: Hybrid retrieval (semantic + keyword search) - STANDARD FLOW
        yield ("thinking", "Finding relevant context...")

        logger.info(
            "Starting hybrid retrieval for user query",
            extra={"user_id": user_id, "session_id": session_id}
        )
        retrieval_start = time.monotonic()

        # Use hybrid retriever (combines semantic + keyword search)
        # Use reformulated query for better keyword matching, but pass understanding for HyDE
        # Retrieve more candidates for potential re-ranking
        hybrid_results = self.hybrid_retriever.retrieve(
            query=retrieval_query,  # rewritten (follow-up) or reformulated query
            collection_id=collection_id,
            top_k=retrieval_candidates,
            document_ids=scoped_doc_ids,  # May be narrowed to a single matched document
            query_understanding=understanding,  # For HyDE enhancement
            min_semantic_similarity=settings.rag_chat_semantic_similarity_floor
        )

        doc_profiles = self._build_document_profiles(doc_info)
        self._annotate_scope_match_features(
            chunks=hybrid_results,
            query_understanding=understanding,
            doc_profiles=doc_profiles,
            collection_id=collection_id,
            requested_doc_ids=set(scoped_doc_ids or []),
        )
        self._apply_scope_score_adjustment(
            chunks=hybrid_results,
            score_field="hybrid_score",
            requested_doc_ids=set(scoped_doc_ids or []),
        )

        retrieval_ms = round((time.monotonic() - retrieval_start) * 1000, 2)
        stage_timings_ms["retrieval"] = retrieval_ms

        logger.info(
            f"Hybrid retrieval complete: {len(hybrid_results)} candidates retrieved",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "document_count": len(document_ids) if document_ids else 0,
                "retrieval_candidates": retrieval_candidates,
                "query_type": understanding.query_type.value,
                "retrieval_ms": retrieval_ms
            }
        )

        # ------------------------------------------------------------------
        # STEP 2: Re-ranking (optional, cross-encoder based)
        rerank_min_candidates = max(1, settings.rag_reranker_min_candidates_chat)
        should_rerank = (
            bool(self.reranker)
            and settings.rag_use_reranker_chat
            and len(hybrid_results) >= rerank_min_candidates
        )
        if should_rerank:
            logger.info(
                f"Starting re-ranking of {len(hybrid_results)} candidates",
                extra={"session_id": session_id}
            )
            rerank_start = time.monotonic()

            # Re-rank with compression and metadata boosting.
            # Run in thread pool to avoid blocking the asyncio event loop during CPU-bound inference.
            relevant_chunks = await asyncio.get_running_loop().run_in_executor(
                None,
                functools.partial(
                    self.reranker.rerank,
                    query=user_message,
                    chunks=hybrid_results,
                    query_understanding=understanding,
                    top_k=final_top_k,
                )
            )
            rerank_ms = round((time.monotonic() - rerank_start) * 1000, 2)
            stage_timings_ms["rerank"] = rerank_ms

            logger.info(
                f"Re-ranking complete: {len(relevant_chunks)} final chunks selected",
                extra={
                    "session_id": session_id,
                    "top_rerank_score": relevant_chunks[0]["rerank_score"] if relevant_chunks else 0,
                    "rerank_ms": rerank_ms
                }
            )
        else:
            # No re-ranker: use hybrid results directly
            relevant_chunks = hybrid_results[:final_top_k]
            stage_timings_ms["rerank"] = 0.0
            if self.reranker and hybrid_results:
                logger.info(
                    "Skipping re-ranking for tiny candidate pool",
                    extra={
                        "session_id": session_id,
                        "candidate_count": len(hybrid_results),
                        "min_candidates_for_rerank": rerank_min_candidates,
                        "selected_chunks": len(relevant_chunks)
                    }
                )
            else:
                logger.info(
                    f"Re-ranker disabled, using top {len(relevant_chunks)} hybrid results",
                    extra={"session_id": session_id}
                )

        # Scope features already annotated on hybrid_results (pre-rerank); surviving chunks
        # carry those annotations. Only re-apply score adjustment for the rerank_score field.
        self._apply_scope_score_adjustment(
            chunks=relevant_chunks,
            score_field="rerank_score" if should_rerank else "hybrid_score",
            requested_doc_ids=set(scoped_doc_ids or []),
        )
        relevant_chunks = sorted(
            relevant_chunks,
            key=lambda x: x.get("rerank_score", x.get("hybrid_score", 0.0)),
            reverse=True,
        )[:final_top_k]

        # Edge case: no relevant chunks found — short-circuit without calling the LLM.
        # An LLM call here is wasteful: the answer is always the same shape ("nothing found"),
        # and we'd be spending tokens just to produce a canned response.
        if not relevant_chunks:
            import random
            _NO_RESULTS_RESPONSES = [
                "I couldn't find relevant content in your documents for that question. "
                "Try rephrasing, or ask about a specific metric, section, or topic you know is covered.",
                "Nothing relevant came up in the documents for that query. "
                "You could try asking in a different way, or focus on a specific term or section.",
                "I didn't find matching content in your documents. "
                "If you know roughly where the information lives, try mentioning the section or page — it helps me narrow the search.",
                "That query didn't match anything in the documents. "
                "Try breaking it into a more specific question, or ask about a particular metric or time period.",
            ]
            logger.warning(
                "No relevant chunks found for user query — returning short-circuit response",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "document_count": len(document_ids) if document_ids else 0,
                    "query_length": len(user_message)
                }
            )
            no_results_response = random.choice(_NO_RESULTS_RESPONSES)
            yield ("chunk", no_results_response)
            saved_ids = await self.persistence.save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=no_results_response,
                source_chunks=[],
                usage_data=None,
                comparison_metadata=None,
                citation_context=None,
                org_id=org_id
            )
            self.last_saved_message_ids = saved_ids
            return

        # ------------------------------------------------------------------
        # STEP 3: Validate and normalize chunk metadata
        if relevant_chunks:
            validation_start = time.monotonic()
            logger.debug(
                f"Validating {len(relevant_chunks)} chunks before budget enforcement",
                extra={"session_id": session_id}
            )
            relevant_chunks = validate_and_normalize_chunks(relevant_chunks)
            stage_timings_ms["validation"] = round((time.monotonic() - validation_start) * 1000, 2)
            logger.debug(
                f"Chunk validation complete: {len(relevant_chunks)} valid chunks",
                extra={"session_id": session_id}
            )

        # ------------------------------------------------------------------
        # STEP 4: Context Expansion (all query types)
        if relevant_chunks and settings.rag_expansion_enabled:
            expansion_start = time.monotonic()

            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as async_session:
                # Quality gate: Only expand chunks above rerank score threshold.
                # Fall back to hybrid_score when reranker is disabled (no rerank_score on chunks).
                rerank_floor = settings.rag_expansion_rerank_floor
                chunks_to_expand = [
                    c for c in relevant_chunks
                    if c.get('rerank_score', c.get('hybrid_score', 0)) >= rerank_floor
                ]
                chunks_below_floor = [
                    c for c in relevant_chunks
                    if c.get('rerank_score', c.get('hybrid_score', 0)) < rerank_floor
                ]

                max_expansion = self._get_max_expansion(understanding.query_type)

                expanded_chunks = await self.context_expander.expand_with_batch(
                    chunks=chunks_to_expand,  # Only expand high-quality chunks
                    session=async_session,
                    max_expansion_per_chunk=max_expansion,
                    query_type=understanding.query_type
                )

                # Merge: expanded high-quality + original low-quality (no expansion)
                relevant_chunks = expanded_chunks + chunks_below_floor

                # Re-sort by score (expanded chunks have derived scores)
                relevant_chunks = sorted(
                    relevant_chunks,
                    key=lambda x: x.get('rerank_score', x.get('hybrid_score', 0)),
                    reverse=True
                )

                # Apply hard limit before budget
                max_total = self._get_max_expanded_chunks(understanding.query_type)
                relevant_chunks = relevant_chunks[:max_total]

                expanded_count = len([c for c in relevant_chunks if c.get('_is_expanded')])
                stage_timings_ms["expansion"] = round((time.monotonic() - expansion_start) * 1000, 2)
                logger.info(
                    "Context expansion complete",
                    extra={
                        "session_id": session_id,
                        "expanded_count": expanded_count,
                        "total_chunks": len(relevant_chunks),
                        "expansion_ms": stage_timings_ms["expansion"]
                    }
                )

        yield ("thinking", "Preparing context...")

        # ------------------------------------------------------------------
        # STEP 5: Budget enforcement
        budget_start = time.monotonic()
        summary_text, recent_messages, relevant_chunks = await self.budget.enforce(
            memory=self.memory,
            user_message=user_message,
            summary_text=summary_text,
            recent_messages=recent_messages,
            relevant_chunks=relevant_chunks
        )
        stage_timings_ms["budget"] = round((time.monotonic() - budget_start) * 1000, 2)
        logger.info(
            "Budget enforcement complete",
            extra={
                "session_id": session_id,
                "remaining_chunks": len(relevant_chunks),
                "budget_ms": stage_timings_ms["budget"]
            }
        )

        # Cache summary if produced
        if summary_text:
            # Calculate last_summarized_index (total - verbatim)
            verbatim_count = settings.chat_verbatim_message_count
            last_summarized_index = max(0, len(history_messages) - verbatim_count)

            self.memory.cache_summary(
                session_id,
                len(history_messages),
                summary_text,
                key_facts=key_facts,
                last_summarized_index=last_summarized_index
            )

        # ------------------------------------------------------------------
        # STEP 3.5: Build citation context (general chat mode)
        # Citations use sequential [Sn:pN] format where n is the chunk position.
        if relevant_chunks:
            citation_start = time.monotonic()
            self.last_citation_context = self._build_citation_context(relevant_chunks)
            stage_timings_ms["citations"] = round((time.monotonic() - citation_start) * 1000, 2)
            logger.info(
                "Citation context built",
                extra={
                    "session_id": session_id,
                    "citation_count": len(self.last_citation_context.get("citations", [])),
                    "citation_ms": stage_timings_ms["citations"]
                }
            )
        else:
            self.last_citation_context = None

        # ------------------------------------------------------------------
        # STEP 4: Build prompt (split for Anthropic prompt caching)
        prompt_start = time.monotonic()
        system_prompt, user_content = self.prompt_builder.build_split(
            user_message=user_message,
            relevant_chunks=relevant_chunks,
            recent_messages=recent_messages,
            summary_text=summary_text,
            include_history=include_history,
        )
        stage_timings_ms["prompt_build"] = round((time.monotonic() - prompt_start) * 1000, 2)
        logger.info(
            "Prompt built",
            extra={
                "session_id": session_id,
                "system_prompt_length": len(system_prompt),
                "user_content_length": len(user_content),
                "prompt_ms": stage_timings_ms["prompt_build"]
            }
        )

        # ------------------------------------------------------------------
        # STEP 5: Stream response from Claude with error handling
        yield ("thinking", "Composing response...")

        full_response = ""
        usage_data = None
        llm_start = time.monotonic()
        use_scope_guardrail = (
            settings.rag_scope_guardrail_regenerate_enabled
            and bool(document_ids and len(document_ids) > 1)
            and bool(scope_target_ids or scoped_doc_ids)
            and scope_confidence >= _SCOPE_GUARDRAIL_MIN_CONFIDENCE
            and scope_mode in {ScopeMode.SINGLE_DOC.value, ScopeMode.AMBIGUOUS.value}
        )
        requested_doc_set = set(scope_target_ids or scoped_doc_ids or [])
        guardrail_regenerated = False
        requested_entity_mismatch = False
        try:
            async for item in self.llm_client.stream_chat(user_content, system_prompt=system_prompt):
                # Handle different stream item types
                if item["type"] == "chunk":
                    text_chunk = item["text"]
                    full_response += text_chunk
                    if not use_scope_guardrail:
                        yield ("chunk", text_chunk)
                elif item["type"] == "usage":
                    # Capture usage data for persistence
                    usage_data = item["data"]
                    logger.debug(
                        "Captured token usage from stream",
                        extra={
                            "session_id": session_id,
                            "input_tokens": usage_data.get("input_tokens"),
                            "output_tokens": usage_data.get("output_tokens")
                        }
                    )

            if use_scope_guardrail and full_response:
                cited_doc_ids = self._extract_cited_document_ids(full_response, self.last_citation_context)
                requested_entity_mismatch = self._has_requested_entity_mismatch(
                    cited_doc_ids=cited_doc_ids,
                    requested_doc_ids=requested_doc_set,
                )

                if requested_entity_mismatch:
                    logger.warning(
                        "Requested entity mismatch detected; regenerating response with stricter scope",
                        extra={
                            "session_id": session_id,
                            "requested_doc_ids": list(requested_doc_set),
                            "cited_doc_ids": list(cited_doc_ids),
                        },
                    )
                    scoped_chunks = [
                        chunk for chunk in relevant_chunks
                        if chunk.get("document_id") in requested_doc_set
                    ]
                    if scoped_chunks:
                        scoped_system_prompt, scoped_user_content = self.prompt_builder.build_split(
                            user_message=user_message,
                            relevant_chunks=scoped_chunks,
                            recent_messages=recent_messages,
                            summary_text=summary_text,
                            include_history=include_history,
                        )
                        full_response, usage_data = await self._collect_full_response(
                            user_content=scoped_user_content,
                            system_prompt=scoped_system_prompt,
                        )
                        self.last_citation_context = self._build_citation_context(scoped_chunks)
                        guardrail_regenerated = True
                    else:
                        logger.warning(
                            "Scope guardrail could not regenerate because scoped chunk set was empty",
                            extra={"session_id": session_id, "requested_doc_ids": list(requested_doc_set)},
                        )

                yield ("chunk", full_response)

            # Persist chat messages only after successful streaming
            saved_ids = await self.persistence.save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=full_response,
                source_chunks=[chunk["id"] for chunk in relevant_chunks],
                usage_data=usage_data,
                comparison_metadata=json.dumps(self.last_comparison_context) if self.last_comparison_context else None,
                citation_context=self.last_citation_context,
                org_id=org_id
            )
            self.last_saved_message_ids = saved_ids
            _, assistant_msg_id = saved_ids if saved_ids else (None, None)

            if self.capture_io_log and self._io_log_repo and assistant_msg_id:
                llm_duration_ms = int((time.monotonic() - llm_start) * 1000)
                self._io_log_repo.save_io_log(
                    source_type="rag_chat",
                    source_id=assistant_msg_id,
                    stage="rag_chat",
                    system_prompt=system_prompt,
                    user_message=user_content,
                    output=full_response,
                    metadata={
                        "rag_eval_contract_version": RAG_EVAL_CONTRACT_VERSION,
                        "session_id": session_id,
                        "user_question": user_message,
                        "document_ids": document_ids or [],
                        "collection_id": collection_id,
                        "chunk_ids": [c["id"] for c in relevant_chunks],
                        "chunk_count": len(relevant_chunks),
                        # Retrieval quality signals (for eval export)
                        "chunk_scores": [serialize_chunk_for_eval(c) for c in relevant_chunks],
                        # Chunk text snippets for context var in generation eval
                        "chunk_texts": [c.get("text", "")[:500] for c in relevant_chunks],
                        # Query understanding output
                        "query_understanding": serialize_query_understanding(understanding),
                        "requested_entity_mismatch": requested_entity_mismatch,
                        "guardrail_regenerated": guardrail_regenerated,
                    },
                    input_tokens=usage_data.get("input_tokens", 0) if usage_data else 0,
                    output_tokens=usage_data.get("output_tokens", 0) if usage_data else 0,
                    cache_creation_tokens=usage_data.get("cache_creation_input_tokens", 0) if usage_data else 0,
                    cache_read_tokens=usage_data.get("cache_read_input_tokens", 0) if usage_data else 0,
                    duration_ms=llm_duration_ms,
                    prompt_version=settings.rag_prompt_version,
                )

            total_latency = time.monotonic() - start_time
            stage_timings_ms["llm_stream"] = round((time.monotonic() - llm_start) * 1000, 2)
            logger.info(
                "Chat response complete",
                extra={
                    "session_id": session_id,
                    "response_length": len(full_response),
                    "llm_ms": stage_timings_ms["llm_stream"],
                    "total_ms": round(total_latency * 1000, 2),
                    "stage_timings_ms": stage_timings_ms
                }
            )

            # Record chat latency metric
            try:
                CHAT_LATENCY_SECONDS.observe(total_latency)
            except Exception as e:
                logger.warning(f"Failed to record chat latency metric: {e}", exc_info=True)

            # Clear comparison and citation context after saving to prevent leaking to next request
            self.last_comparison_context = None
            self.last_citation_context = None
        except Exception as stream_error:
            logger.error(
                f"LLM streaming failed: {stream_error}",
                extra={
                    "session_id": session_id,
                    "document_count": len(document_ids) if document_ids else 0,
                    "partial_response_length": len(full_response),
                    "error_type": type(stream_error).__name__
                },
                exc_info=True
            )
            # Save partial response if any
            if full_response:
                try:
                    await self.persistence.save_chat_messages(
                        session_id=session_id,
                        user_message=user_message,
                        assistant_message=f"{full_response}\n\n[Error: Response was interrupted due to technical issues]",
                        source_chunks=[chunk["id"] for chunk in relevant_chunks],
                        usage_data=usage_data,  # Include usage data if captured before error
                        comparison_metadata=json.dumps(self.last_comparison_context) if self.last_comparison_context else None,
                        citation_context=self.last_citation_context,
                        org_id=org_id
                    )
                except Exception as save_error:
                    logger.error(
                        f"Failed to save partial chat response: {save_error}",
                        extra={"session_id": session_id}
                    )
            raise

    async def _vector_search(
        self,
        query_embedding: List[float],
        collection_id: str,
        limit: int = 5,
        similarity_threshold: float = 0.3,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search for relevant document chunks.

        Args:
            query_embedding: Embedding vector of the user's query
            collection_id: Collection to search within
            limit: Maximum number of chunks to return
            similarity_threshold: Minimum similarity score (0-1)
            document_ids: Optional list of specific document IDs to search

        Returns:
            List of relevant chunk dictionaries with metadata
        """
        # Build distance expression using cosine distance
        distance_expr = DocumentChunk.embedding.cosine_distance(query_embedding).label("distance")

        # Base query
        stmt = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                DocumentChunk.page_number,
                DocumentChunk.chunk_index,
                DocumentChunk.text,
                DocumentChunk.is_tabular,
                distance_expr,
            )
            .join(CollectionDocument, DocumentChunk.document_id == CollectionDocument.document_id)
            .where(CollectionDocument.collection_id == collection_id)
        )

        # Filter by specific documents if provided
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        # Filter by similarity threshold (cosine distance < threshold means more similar)
        # Note: cosine distance of 0 = identical, 1 = orthogonal, 2 = opposite
        stmt = stmt.where(distance_expr < (1.0 - similarity_threshold))

        # Order by similarity (lowest distance first) and limit results
        stmt = stmt.order_by(distance_expr).limit(limit)

        # Execute query
        results = self.db.execute(stmt).fetchall()

        # Convert to list of dictionaries
        chunks = []
        for row in results:
            chunks.append({
                "id": row.id,
                "document_id": row.document_id,
                "page_number": row.page_number,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "is_tabular": row.is_tabular,
                "distance": float(row.distance),
                "similarity": 1.0 - float(row.distance),  # Convert distance to similarity score
            })

        return chunks

    def _match_scope_targets_to_documents(self, query_understanding, documents: List[Dict[str, Any]]) -> List[str]:
        """Resolve scope targets (property/deal/doc names + geo hints) to document IDs."""
        if not documents or not query_understanding:
            return []

        targets: List[str] = []
        targets.extend([name for name in (getattr(query_understanding, "target_property_names", []) or []) if isinstance(name, str)])

        for entity in (getattr(query_understanding, "entities", []) or []):
            entity_type = getattr(entity, "entity_type", "")
            if entity_type in {"document", "property", "deal", "organization", "other"}:
                name = getattr(entity, "name", "")
                if name:
                    targets.append(name)

        # Geo hints can map to filename tokens in many OM naming conventions.
        city = getattr(query_understanding, "target_geo_city", None)
        state = getattr(query_understanding, "target_geo_state", None)
        if city:
            targets.append(city)
        if state:
            targets.append(state)

        deduped_targets = []
        seen = set()
        for target in targets:
            norm = re.sub(r"\s+", " ", (target or "").strip().lower())
            if len(norm) < 3 or norm in seen:
                continue
            seen.add(norm)
            deduped_targets.append(target)

        matched_ids: List[str] = []
        for target in deduped_targets[:12]:
            match = self.document_matcher.fuzzy_match_document(target, documents, threshold=0.5)
            if match and match["id"] not in matched_ids:
                matched_ids.append(match["id"])

        return matched_ids

    async def _collect_full_response(self, user_content: str, system_prompt: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Collect full LLM response without streaming to caller."""
        full_response = ""
        usage_data: Optional[Dict[str, Any]] = None
        async for item in self.llm_client.stream_chat(user_content, system_prompt=system_prompt):
            if item["type"] == "chunk":
                full_response += item["text"]
            elif item["type"] == "usage":
                usage_data = item["data"]
        return full_response, usage_data

    def _build_document_profiles(self, documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Build lightweight per-document profile from filenames for scope matching."""
        profiles: Dict[str, Dict[str, Any]] = {}
        for doc in documents or []:
            doc_id = doc.get("id")
            filename = doc.get("filename", "")
            if not doc_id:
                continue
            stem = re.sub(r"\.[A-Za-z0-9]+$", "", filename)
            normalized_stem = self._normalize_scope_text(stem)
            alias_tokens = {normalized_stem}
            for token in re.split(r"[_\-\s]+", stem):
                norm_token = self._normalize_scope_text(token)
                if len(norm_token) >= 3:
                    alias_tokens.add(norm_token)
            profiles[doc_id] = {
                "filename": filename,
                "normalized_stem": normalized_stem,
                "aliases": alias_tokens,
            }
        return profiles

    def _annotate_scope_match_features(
        self,
        chunks: List[Dict[str, Any]],
        query_understanding,
        doc_profiles: Dict[str, Dict[str, Any]],
        collection_id: Optional[str],
        requested_doc_ids: Set[str],
    ) -> None:
        """Attach chunk-level scope features used by ranking and guardrails."""
        target_names = [
            self._normalize_scope_text(name)
            for name in (getattr(query_understanding, "target_property_names", []) or [])
            if isinstance(name, str) and name.strip()
        ]
        target_city = self._normalize_scope_text(getattr(query_understanding, "target_geo_city", "") or "")
        target_state = self._normalize_scope_text(getattr(query_understanding, "target_geo_state", "") or "")

        for chunk in chunks or []:
            doc_id = chunk.get("document_id")
            profile = doc_profiles.get(doc_id, {})
            aliases = profile.get("aliases", set())

            property_exact_match = any(
                target and (
                    target == profile.get("normalized_stem")
                    or target in aliases
                    or target in profile.get("normalized_stem", "")
                )
                for target in target_names
            )
            geo_match = bool(
                (target_city and target_city in profile.get("normalized_stem", ""))
                or (target_state and target_state in profile.get("normalized_stem", ""))
            )
            requested_scope_match = bool(doc_id and requested_doc_ids and doc_id in requested_doc_ids)

            entity_doc_match_score = 0.0
            if property_exact_match:
                entity_doc_match_score += 0.55
            if geo_match:
                entity_doc_match_score += 0.25
            if requested_scope_match:
                entity_doc_match_score += 0.35
            entity_doc_match_score = min(entity_doc_match_score, 1.0)

            chunk["collection_id"] = collection_id
            chunk["canonical_document_key"] = f"{collection_id}:{doc_id}" if collection_id and doc_id else str(doc_id or "")
            chunk["property_name_exact_match"] = property_exact_match
            chunk["geo_match"] = geo_match
            chunk["requested_scope_match"] = requested_scope_match
            chunk["entity_doc_match_score"] = round(entity_doc_match_score, 4)

    def _apply_scope_score_adjustment(
        self,
        chunks: List[Dict[str, Any]],
        score_field: str,
        requested_doc_ids: Set[str],
    ) -> None:
        """Apply lightweight scope-aware boost/penalty to retrieval or rerank score."""
        if not settings.rag_scope_match_reweight_enabled:
            return
        boost_weight = max(0.0, settings.rag_scope_match_boost_weight)
        mismatch_penalty = max(0.0, min(settings.rag_scope_mismatch_penalty_weight, 0.9))

        for chunk in chunks or []:
            base_score = float(chunk.get(score_field, 0.0) or 0.0)
            match_score = float(chunk.get("entity_doc_match_score", 0.0) or 0.0)
            adjusted = base_score * (1.0 + (boost_weight * match_score))

            if requested_doc_ids and chunk.get("document_id") not in requested_doc_ids:
                adjusted *= (1.0 - mismatch_penalty)

            chunk[f"{score_field}_scope_adjusted"] = round(adjusted, 6)
            chunk[score_field] = adjusted

    def _extract_cited_document_ids(self, response_text: str, citation_context: Optional[Dict[str, Any]]) -> Set[str]:
        """Resolve cited [Sn:pN] references in model output into concrete document IDs."""
        if not response_text or not citation_context:
            return set()
        refs = re.findall(r"\[S(\d+):p(\d+)\]", response_text)
        if not refs:
            return set()

        citations = citation_context.get("citations", []) or []
        cited_doc_ids: Set[str] = set()
        for src_idx, page in refs:
            src_int = int(src_idx)
            page_int = int(page)
            exact = next(
                (c for c in citations if c.get("source_index") == src_int and c.get("page") == page_int),
                None,
            )
            fallback = exact or next((c for c in citations if c.get("source_index") == src_int), None)
            if fallback and fallback.get("document_id"):
                cited_doc_ids.add(str(fallback["document_id"]))
        return cited_doc_ids

    def _has_requested_entity_mismatch(self, cited_doc_ids: Set[str], requested_doc_ids: Set[str]) -> bool:
        """Detect when cited docs do not align with requested scope docs."""
        if not requested_doc_ids:
            return False
        if not cited_doc_ids:
            return bool(settings.rag_scope_guardrail_require_citations)
        return not cited_doc_ids.issubset(requested_doc_ids)

    @staticmethod
    def _normalize_scope_text(value: str) -> str:
        if not value:
            return ""
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", value.lower())).strip()

    def _get_max_expansion(self, query_type: QueryType) -> int:
        """
        Get max expansions per chunk by query type.

        Args:
            query_type: Query type for adaptive expansion

        Returns:
            Max expansions per chunk
        """
        return {
            QueryType.DATA_EXTRACTION: 2,
            QueryType.SUMMARIZATION: 1,
            QueryType.ENTITY_LOOKUP: 1,
            QueryType.GENERAL_QA: 1,
            QueryType.COMPARISON: 2
        }.get(query_type, 1)

    def _get_max_expanded_chunks(self, query_type: QueryType) -> int:
        """
        Get hard limit on total chunks after expansion by query type.

        Args:
            query_type: Query type for adaptive limits

        Returns:
            Maximum total chunks after expansion
        """
        return {
            QueryType.DATA_EXTRACTION: 24,
            QueryType.SUMMARIZATION: 15,
            QueryType.ENTITY_LOOKUP: 10,
            QueryType.GENERAL_QA: 18,
            QueryType.COMPARISON: 20
        }.get(query_type, 18)

    def _build_citation_context(
        self,
        chunks: List[Dict],
        doc_id_to_index: Optional[Dict[str, int]] = None,
    ) -> Dict:
        """
        Build citation context for frontend resolution using [Sn:pN] format.

        The context object is sent to the frontend via SSE and used to resolve
        [Sn:pN] citation tokens in LLM responses to clickable PDF page links.
        Each chunk gets a sequential source index (1-based) matching its position in the prompt.

        Args:
            chunks: List of retrieved chunks (in order as shown to LLM).
            doc_id_to_index: Deprecated (not used). Kept for API compatibility.

        Returns:
            Dict with:
              - citations: list of citation metadata indexed by source position
                (source_index, page, chunk_id, bbox, ...)
              - document_map: {doc_id: filename} for display purposes
        """
        # Collect unique document IDs
        doc_ids = list(set(
            chunk.get('document_id') for chunk in chunks
            if chunk.get('document_id')
        ))

        if not doc_ids:
            return {"citations": [], "document_map": {}}

        # Batch fetch document info (1 query, not N)
        doc_info_list = self.document_repo.get_doc_info_by_ids(doc_ids)
        doc_map = {d['id']: d for d in doc_info_list}

        # Build citation entries with sequential source indices
        citations = []

        for source_idx, chunk in enumerate(chunks, 1):
            chunk_id = str(chunk.get('id', ''))
            if not chunk_id:
                continue

            doc_id = chunk.get('document_id')
            doc_info = doc_map.get(doc_id, {})
            metadata = chunk.get('chunk_metadata') or {}

            base_entry = {
                "source_index": source_idx,
                "chunk_id": chunk_id,
                "document_id": doc_id,
                "filename": doc_info.get('filename', 'Unknown'),
                "section": metadata.get('section_heading', ''),
            }

            # Narrative chunks that span multiple pages store paragraph_pages:
            # [{page, char_offset, bbox}, ...] — one entry per page transition.
            # KV chunks can store kv_pages with similar structure for page-accurate
            # citation resolution.
            paragraph_pages = metadata.get('paragraph_pages')
            if paragraph_pages:
                for pp in paragraph_pages:
                    pp_page = pp.get('page')
                    if not pp_page:
                        continue
                    pp_bbox = pp.get('bbox')
                    if pp_bbox:
                        pp_bbox = {**pp_bbox, "page": pp_page}
                    citations.append({
                        **base_entry,
                        "page": pp_page,
                        "bbox": pp_bbox or None,
                    })
            elif metadata.get('kv_pages'):
                for kvp in metadata.get('kv_pages'):
                    kv_page = kvp.get('page')
                    if not kv_page:
                        continue
                    kv_bbox = kvp.get('bbox')
                    if kv_bbox:
                        kv_bbox = {**kv_bbox, "page": kv_page}
                    citations.append({
                        **base_entry,
                        "page": kv_page,
                        "bbox": kv_bbox or None,
                    })
            else:
                # Single-page chunk (tables, KV pairs, or single-page narratives)
                bbox = metadata.get('bbox', {})
                page = bbox.get('page') if isinstance(bbox, dict) and bbox else chunk.get('page_number', 1)
                citations.append({
                    **base_entry,
                    "page": page,
                    "bbox": bbox or None,
                })

        logger.debug(
            "Built citation context",
            extra={
                "chunk_count": len(chunks),
                "citation_count": len(citations),
                "document_count": len(doc_info_list)
            }
        )

        return {
            "citations": citations,
            "document_map": {d['id']: d['filename'] for d in doc_info_list},
        }

    # All conversation memory & budget helpers moved to modular components.
