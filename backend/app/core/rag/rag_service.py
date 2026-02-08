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
from typing import List, Dict, Any, Optional, AsyncIterator
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db_models_chat import DocumentChunk, CollectionDocument
from app.db_models_documents import Document
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
from app.core.rag.query_understanding import QueryUnderstandingService, QueryType
from app.core.rag.fact_extractor import FactExtractor
from app.core.rag.context_expander import ContextExpander
from app.utils.chunk_metadata import validate_and_normalize_chunks
from app.core.rag.chat_persistence import ChatPersistence
from app.core.rag.comparison_flow import ComparisonChatHandler
from app.core.rag.document_matching import DocumentMatcher
import re
import json
import time
from app.services.service_locator import get_reranker


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

    def __init__(self, db: Session, reranker: Reranker | None = None):
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
        self.prompt_builder = PromptBuilder()
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
        self.fact_extractor = FactExtractor()

        # Context expander (for expanding chunks with related context)
        self.context_expander = ContextExpander()

        # Persistence helper
        self.persistence = ChatPersistence()

        # Comparison context for SSE emission (set during comparison queries)
        self.last_comparison_context = None

        # Citation context for SSE emission (set during general chat queries)
        self.last_citation_context = None

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
            on_comparison_context=self._set_comparison_context
        )

        # Low-signal chat detection (skip retrieval/reranking for acknowledgements)
        self._ack_words = {
            "ok", "okay", "k", "kk", "alright", "sure", "sounds", "good", "cool", "great",
            "perfect", "awesome", "nice", "fine", "got", "it", "understood", "yep", "yes",
            "no", "thanks", "thank", "you", "thx", "appreciate", "appreciated",
            "hi", "hello", "hey", "bye", "goodbye", "later", "cheers"
        }
        self._greeting_words = {"hi", "hello", "hey"}
        self._thanks_words = {"thanks", "thank", "thx", "appreciate", "appreciated"}
        self._farewell_words = {"bye", "goodbye", "later", "cheers"}

    def _is_low_signal_message(self, user_message: str) -> bool:
        if not user_message:
            return False
        msg = user_message.strip().lower()
        if not msg or len(msg) > 50:
            return False
        if "?" in msg:
            return False
        if re.search(r"\d", msg):
            return False
        normalized = re.sub(r"[^a-z\s]", " ", msg)
        words = [w for w in normalized.split() if w]
        if not words:
            return False
        return all(w in self._ack_words for w in words)

    def _low_signal_response(self, user_message: str) -> str:
        msg = (user_message or "").strip().lower()
        if any(w in msg for w in self._thanks_words):
            return "You're welcome! Let me know if you'd like me to analyze anything else."
        if any(w in msg for w in self._farewell_words):
            return "Got it. If you need anything else, just ask."
        if any(w in msg for w in self._greeting_words):
            return "Hi! What would you like to know about these documents?"
        return "Okay. Let me know if you'd like anything else."

    def _set_comparison_context(self, comparison_data: Dict):
        self.last_comparison_context = comparison_data

    async def chat(
        self,
        session_id: str,
        collection_id: Optional[str],
        user_message: str,
        user_id: Optional[str] = None,
        org_id: Optional[str] = None,
        num_chunks: int = 5,  # DEPRECATED: Now uses rag_final_top_k from config
        similarity_threshold: float = 0.0,  # DEPRECATED: Not used with hybrid retrieval
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
            num_chunks: DEPRECATED - Now uses settings.rag_final_top_k (kept for backwards compatibility)
            similarity_threshold: DEPRECATED - Not used with hybrid retrieval (kept for backwards compatibility)
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

        # Edge case: Validate num_chunks is positive
        if num_chunks <= 0:
            logger.warning(
                f"Invalid num_chunks: {num_chunks}, using default 5",
                extra={"session_id": session_id}
            )
            num_chunks = 5

        # Edge case: Validate similarity_threshold is in valid range
        if not (0 <= similarity_threshold <= 1):
            logger.warning(
                f"Invalid similarity_threshold: {similarity_threshold}, using default 0.0",
                extra={"session_id": session_id}
            )
            similarity_threshold = 0.0

        # STEP 0: History & optional summarization via memory component
        start_time = time.monotonic()
        history_messages = self.memory.load_history(session_id)
        summary_text, recent_messages, key_facts = await self.memory.maybe_summarize(session_id, history_messages, user_message)

        # STEP 0.25: Short-circuit low-signal messages (skip retrieval/rerank)
        if self._is_low_signal_message(user_message):
            assistant_message = self._low_signal_response(user_message)
            yield assistant_message
            await self.persistence.save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=assistant_message,
                source_chunks=[],
                usage_data=None,
                org_id=org_id
            )
            self.last_comparison_context = None
            return

        # STEP 0.5: Query Understanding (LLM-powered analysis)
        # Load document metadata for query understanding context
        doc_info = []
        if document_ids:
            doc_info = self.document_repo.get_doc_info_by_ids(document_ids)

        doc_filenames = [d["filename"] for d in doc_info]

        # Analyze query with LLM (cheap Haiku call)
        understanding = await self.query_understanding.understand(
            query=user_message,
            document_filenames=doc_filenames
        )

        # STEP 0.75: Adaptive retrieval sizing based on query intent
        retrieval_candidates = settings.rag_retrieval_candidates
        final_top_k = settings.rag_final_top_k
        if understanding.confidence is None or understanding.confidence >= 0.4:
            if understanding.query_type == QueryType.DATA_EXTRACTION:
                retrieval_candidates = max(retrieval_candidates, 25)
                final_top_k = max(final_top_k, 12)
            elif understanding.query_type == QueryType.SUMMARIZATION:
                retrieval_candidates = max(15, min(retrieval_candidates, 20))
                final_top_k = max(8, min(final_top_k, 10))
            elif understanding.query_type == QueryType.ENTITY_LOOKUP:
                retrieval_candidates = max(12, min(retrieval_candidates, 20))
                final_top_k = max(6, min(final_top_k, 10))

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

        # Branch to comparison flow if detected (or forced) and multiple documents available
        should_compare = (
            (force_comparison is True) or
            (force_comparison is None and understanding.query_type == QueryType.COMPARISON)
        )

        if should_compare and document_ids and len(document_ids) >= 2 and getattr(settings, 'comparison_enabled', True) and force_comparison is not False:
            max_docs = getattr(settings, 'comparison_max_documents', 3)

            # ≤3 docs in session: proceed automatically
            if len(document_ids) <= 3:
                final_doc_ids = document_ids
                logger.info(
                    f"Auto-proceeding with comparison (≤3 documents)",
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
                    logger.info(
                        f"Auto-proceeding with user-mentioned documents (2-3 docs)",
                        extra={
                            "session_id": session_id,
                            "num_docs": len(matched_ids)
                        }
                    )

                # User mentioned >3 specific docs: ask user to select up to 3
                elif matched_ids and len(matched_ids) > 3:
                    logger.info(
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
                    yield f"event: comparison_selection\ndata: {json.dumps(selection_event)}\n\n"
                    return  # Wait for user selection

                # No specific docs mentioned: ask user to select from all session docs
                else:
                    logger.info(
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
                    yield f"event: comparison_selection\ndata: {json.dumps(selection_event)}\n\n"
                    return  # Wait for user selection

            logger.info(
                f"Comparison query proceeding with {len(final_doc_ids)} documents",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "num_docs": len(final_doc_ids),
                    "understanding_type": understanding.query_type.value if understanding.query_type else "forced"
                }
            )

            async for chunk in self.comparison_handler.handle(
                session_id=session_id,
                collection_id=collection_id,
                user_message=user_message,
                user_id=user_id,
                document_ids=final_doc_ids,
                summary_text=summary_text,
                recent_messages=recent_messages,
                query_understanding=understanding  # For HyDE enhancement
            ):
                yield chunk
            self.last_comparison_context = None
            return  # Exit after comparison flow

        # ------------------------------------------------------------------
        # STEP 1: Hybrid retrieval (semantic + keyword search) - STANDARD FLOW
        logger.info(
            f"Starting hybrid retrieval for user query",
            extra={"user_id": user_id, "session_id": session_id}
        )
        retrieval_start = time.monotonic()

        # Use hybrid retriever (combines semantic + keyword search)
        # Use reformulated query for better keyword matching, but pass understanding for HyDE
        # Retrieve more candidates for potential re-ranking
        hybrid_results = self.hybrid_retriever.retrieve(
            query=understanding.reformulated_query,  # Use reformulated query for keyword search
            collection_id=collection_id,
            top_k=retrieval_candidates,
            document_ids=document_ids,
            query_understanding=understanding,  # For HyDE enhancement
            min_semantic_similarity=settings.rag_chat_semantic_similarity_floor
        )

        logger.info(
            f"Hybrid retrieval complete: {len(hybrid_results)} candidates retrieved",
            extra={
                "user_id": user_id,
                "session_id": session_id,
                "document_count": len(document_ids) if document_ids else 0,
                "retrieval_candidates": retrieval_candidates,
                "query_type": understanding.query_type.value,
                "retrieval_ms": round((time.monotonic() - retrieval_start) * 1000, 2)
            }
        )

        # ------------------------------------------------------------------
        # STEP 2: Re-ranking (optional, cross-encoder based)
        if self.reranker and hybrid_results:
            logger.info(
                f"Starting re-ranking of {len(hybrid_results)} candidates",
                extra={"session_id": session_id}
            )
            rerank_start = time.monotonic()

            # Re-rank with compression and metadata boosting
            relevant_chunks = self.reranker.rerank(
                query=user_message,
                chunks=hybrid_results,
                query_understanding=understanding,
                top_k=final_top_k
            )

            logger.info(
                f"Re-ranking complete: {len(relevant_chunks)} final chunks selected",
                extra={
                    "session_id": session_id,
                    "top_rerank_score": relevant_chunks[0]["rerank_score"] if relevant_chunks else 0,
                    "rerank_ms": round((time.monotonic() - rerank_start) * 1000, 2)
                }
            )
        else:
            # No re-ranker: use hybrid results directly
            relevant_chunks = hybrid_results[:final_top_k]
            logger.info(
                f"Re-ranker disabled, using top {len(relevant_chunks)} hybrid results",
                extra={"session_id": session_id}
            )

        # Edge case: Handle when no relevant chunks are found
        if not relevant_chunks:
            logger.warning(
                "No relevant chunks found for user query",
                extra={
                    "user_id": user_id,
                    "session_id": session_id,
                    "document_count": len(document_ids) if document_ids else 0,
                    "query_length": len(user_message),
                    "similarity_threshold": similarity_threshold
                }
            )
            # Continue with empty context - let LLM respond that it can't find relevant info

        # ------------------------------------------------------------------
        # STEP 2.5: Validate and normalize chunk metadata
        if relevant_chunks:
            logger.debug(
                f"Validating {len(relevant_chunks)} chunks before budget enforcement",
                extra={"session_id": session_id}
            )
            relevant_chunks = validate_and_normalize_chunks(relevant_chunks)
            logger.debug(
                f"Chunk validation complete: {len(relevant_chunks)} valid chunks",
                extra={"session_id": session_id}
            )

        # ------------------------------------------------------------------
        # STEP 2.6: Context Expansion (all query types)
        if relevant_chunks and settings.rag_expansion_enabled:
            expansion_start = time.monotonic()

            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as async_session:
                # Quality gate: Only expand chunks above rerank score threshold
                rerank_floor = settings.rag_expansion_rerank_floor
                chunks_to_expand = [
                    c for c in relevant_chunks
                    if c.get('rerank_score', 0) >= rerank_floor
                ]
                chunks_below_floor = [
                    c for c in relevant_chunks
                    if c.get('rerank_score', 0) < rerank_floor
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
                logger.info(
                    "Context expansion complete",
                    extra={
                        "session_id": session_id,
                        "expanded_count": expanded_count,
                        "total_chunks": len(relevant_chunks),
                        "expansion_ms": round((time.monotonic() - expansion_start) * 1000, 2)
                    }
                )

        # ------------------------------------------------------------------
        # STEP 3: Budget enforcement
        budget_start = time.monotonic()
        summary_text, recent_messages, relevant_chunks = await self.budget.enforce(
            memory=self.memory,
            user_message=user_message,
            summary_text=summary_text,
            recent_messages=recent_messages,
            relevant_chunks=relevant_chunks
        )
        logger.info(
            "Budget enforcement complete",
            extra={
                "session_id": session_id,
                "remaining_chunks": len(relevant_chunks),
                "budget_ms": round((time.monotonic() - budget_start) * 1000, 2)
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
        # STEP 3.5: Build citation context for frontend (general chat mode)
        if relevant_chunks:
            citation_start = time.monotonic()
            self.last_citation_context = self._build_citation_context(relevant_chunks)
            logger.info(
                "Citation context built",
                extra={
                    "session_id": session_id,
                    "citation_count": len(self.last_citation_context.get("citations", [])),
                    "citation_ms": round((time.monotonic() - citation_start) * 1000, 2)
                }
            )
        else:
            self.last_citation_context = None

        # ------------------------------------------------------------------
        # STEP 4: Build prompt
        prompt_start = time.monotonic()
        prompt = self.prompt_builder.build(
            user_message=user_message,
            relevant_chunks=relevant_chunks,
            recent_messages=recent_messages,
            summary_text=summary_text
        )
        logger.info(
            "Prompt built",
            extra={
                "session_id": session_id,
                "prompt_length": len(prompt),
                "prompt_ms": round((time.monotonic() - prompt_start) * 1000, 2)
            }
        )

        # ------------------------------------------------------------------
        # STEP 5: Stream response from Claude with error handling
        full_response = ""
        usage_data = None
        llm_start = time.monotonic()
        try:
            async for item in self.llm_client.stream_chat(prompt):
                # Handle different stream item types
                if item["type"] == "chunk":
                    text_chunk = item["text"]
                    full_response += text_chunk
                    yield text_chunk
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

            # Persist chat messages only after successful streaming
            await self.persistence.save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=full_response,
                source_chunks=[chunk["id"] for chunk in relevant_chunks],
                usage_data=usage_data,
                comparison_metadata=json.dumps(self.last_comparison_context) if self.last_comparison_context else None,
                citation_context=self.last_citation_context,
                org_id=org_id
            )

            total_latency = time.monotonic() - start_time
            logger.info(
                "Chat response complete",
                extra={
                    "session_id": session_id,
                    "response_length": len(full_response),
                    "llm_ms": round((time.monotonic() - llm_start) * 1000, 2),
                    "total_ms": round(total_latency * 1000, 2)
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

    def _build_citation_context(self, chunks: List[Dict]) -> Dict:
        """
        Build citation context for frontend resolution using DocumentRepository.

        Creates a mapping of chunk ID prefixes to document information,
        enabling clickable citations in the UI with O(1) lookup.

        Args:
            chunks: List of retrieved chunks

        Returns:
            Dict with citations array and document_map
        """
        from app.repositories.document_repository import DocumentRepository

        doc_repo = DocumentRepository()

        # Collect unique document IDs
        doc_ids = list(set(
            chunk.get('document_id') for chunk in chunks
            if chunk.get('document_id')
        ))

        if not doc_ids:
            return {"citations": [], "document_map": {}}

        # Batch fetch document info (1 query, not N)
        doc_info_list = doc_repo.get_doc_info_by_ids(doc_ids)
        doc_map = {d['id']: d for d in doc_info_list}

        # Build citation entries
        citations = []
        for chunk in chunks:
            chunk_id = str(chunk.get('id', ''))
            if not chunk_id:
                continue

            doc_id = chunk.get('document_id')
            doc_info = doc_map.get(doc_id, {})
            metadata = chunk.get('chunk_metadata') or chunk.get('metadata') or {}

            # Use bbox page if available (physical PDF page from Azure DI bounding_regions)
            # This is more accurate than page_number column which may contain document's internal numbering
            bbox = metadata.get('bbox', {})
            page = bbox.get('page') if bbox else chunk.get('page_number', 1)

            citations.append({
                "ref": chunk_id[:8],  # Short reference for LLM
                "chunk_id": chunk_id,  # Full ID for lookup
                "document_id": doc_id,
                "filename": doc_info.get('filename', 'Unknown'),
                "page": page,  # Physical PDF page number
                "section": metadata.get('section_heading', ''),
                "bbox": bbox or None,  # For PDF highlighting (includes accurate page number)
            })

        logger.info(
            "Built citation context",
            extra={
                "chunk_count": len(chunks),
                "citation_count": len(citations),
                "document_count": len(doc_info_list)
            }
        )

        return {
            "citations": citations,
            "document_map": {d['id']: d['filename'] for d in doc_info_list}
        }

    # All conversation memory & budget helpers moved to modular components.
