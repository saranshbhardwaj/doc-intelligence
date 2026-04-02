"""Comparison flow handler for RAG chat."""
from __future__ import annotations

from typing import List, Dict, Optional, AsyncIterator, Callable, Any
import json
import logging
import time

from app.config import settings
from app.core.rag.eval_contract import (
    RAG_EVAL_CONTRACT_VERSION,
    serialize_chunk_for_eval,
    serialize_query_understanding,
)
from app.repositories.document_repository import DocumentRepository


logger = logging.getLogger(__name__)


class ComparisonChatHandler:
    def __init__(
        self,
        db,
        comparison_retriever,
        fact_extractor,
        prompt_builder,
        llm_client,
        save_messages: Callable[..., AsyncIterator[str]] | Callable[..., object],
        on_comparison_context: Callable[[Dict], None],
        on_citation_context: Optional[Callable] = None,
        capture_io_log: bool = False,
        io_log_repo=None,
    ):
        self.db = db
        self.document_repo = DocumentRepository()
        self.comparison_retriever = comparison_retriever
        self.fact_extractor = fact_extractor
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.save_messages = save_messages
        self.on_comparison_context = on_comparison_context
        self.on_citation_context = on_citation_context
        self.capture_io_log = capture_io_log
        self._io_log_repo = io_log_repo

    @staticmethod
    def _flatten_eval_chunks(chunks_per_doc: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Flatten and deduplicate retrieved chunks for eval logging."""
        flattened: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()

        for doc_chunks in chunks_per_doc.values():
            for chunk in doc_chunks:
                chunk_id = chunk.get("id")
                dedupe_key = chunk_id or f"{chunk.get('document_id')}:{chunk.get('page_number')}:{chunk.get('text', '')[:80]}"
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                flattened.append(chunk)

        return flattened

    async def handle(
        self,
        session_id: str,
        collection_id: Optional[str],
        user_message: str,
        user_id: Optional[str],
        document_ids: List[str],
        summary_text: Optional[str],
        recent_messages: List[Dict],
        query_understanding=None,
        include_history: bool = True,  # Always default True; RAGService passes computed value
    ) -> AsyncIterator[str]:
        comparison_start = time.monotonic()
        logger.info(
            "Starting comparison retrieval",
            extra={
                "session_id": session_id,
                "num_documents": len(document_ids),
                "query_type": query_understanding.query_type.value if query_understanding else "comparison"
            }
        )

        # Compute per-doc chunk budget proportional to page count so larger
        # documents get more representation than short ones.
        base_chunks = getattr(settings, "comparison_chunks_per_doc", 8)

        # Narrow queries (1-2 specific data fields) need fewer chunks per doc.
        # Broad comparisons ("full comparison", no specific fields) use full budget.
        if query_understanding:
            data_fields = getattr(query_understanding, "data_fields", [])
            if data_fields and len(data_fields) <= 2:
                base_chunks = min(base_chunks, 6)
        doc_meta = self.document_repo.get_doc_metadata_by_ids(document_ids)
        page_counts = {m["id"]: (m["page_count"] or 1) for m in doc_meta}
        total_pages = sum(page_counts.values()) or 1
        chunks_per_doc_map: Dict[str, int] = {}
        for doc_id in document_ids:
            pages = page_counts.get(doc_id, 1)
            allocated = round((pages / total_pages) * base_chunks * len(document_ids))
            chunks_per_doc_map[doc_id] = max(3, min(base_chunks * 2, allocated))
        logger.info(
            "Adaptive comparison chunk allocation",
            extra={"session_id": session_id, "chunks_per_doc_map": chunks_per_doc_map}
        )

        comparison_context = await self.comparison_retriever.retrieve_for_comparison(
            query=user_message,
            document_ids=document_ids,
            collection_id=collection_id,
            chunks_per_doc=base_chunks,
            chunks_per_doc_map=chunks_per_doc_map,
            similarity_threshold=getattr(settings, "comparison_similarity_threshold", 0.6),
            max_documents=getattr(settings, "comparison_max_documents", 5),
            query_understanding=query_understanding,
            async_session=None  # Each doc opens its own session to avoid concurrent ISCE errors
        )

        num_paired = len(comparison_context.paired_chunks) if comparison_context.paired_chunks else 0
        num_clustered = len(comparison_context.clustered_chunks) if comparison_context.clustered_chunks else 0

        logger.info(
            "Comparison retrieval complete",
            extra={
                "session_id": session_id,
                "num_documents": comparison_context.num_documents,
                "num_paired": num_paired,
                "num_clustered": num_clustered,
                "document_names": [doc.filename for doc in comparison_context.documents]
            }
        )

        # Detect asymmetric context: any document with zero paired/clustered/unpaired chunks
        # signals that entity matching or retrieval failed for that document.
        all_represented: set = set()
        for pair in (comparison_context.paired_chunks or []):
            all_represented.add(pair.chunk_a.get("document_id"))
            all_represented.add(pair.chunk_b.get("document_id"))
        for cluster in (comparison_context.clustered_chunks or []):
            all_represented.update(cluster.chunks.keys())
        for doc_id, chunks in (comparison_context.unpaired_chunks or {}).items():
            if chunks:
                all_represented.add(doc_id)

        missing_docs = [
            {"id": d.id, "filename": d.filename}
            for d in comparison_context.documents
            if d.id not in all_represented
        ]
        if missing_docs:
            logger.warning(
                "Comparison asymmetry: documents with no matching chunks",
                extra={
                    "session_id": session_id,
                    "missing": [m["filename"] for m in missing_docs],
                }
            )
            yield ("comparison_warning", {
                "missing_documents": missing_docs,
                "message": "No relevant content found for: "
                    + ", ".join(m["filename"] for m in missing_docs)
                    + ". Comparison may be incomplete.",
            })
            # Continue — partial comparison is better than nothing

        yield ("thinking", "Extracting key facts from each document...")

        # Extract facts (optional)
        document_facts = None
        chunks_per_doc: Dict[str, List[Dict[str, Any]]] = {}
        try:
            import asyncio

            for doc in comparison_context.documents:
                doc_chunks = []
                seen_ids: set = set()

                def _add(chunk: dict) -> None:
                    cid = chunk.get("id")
                    if cid and cid not in seen_ids:
                        seen_ids.add(cid)
                        doc_chunks.append(chunk)

                if comparison_context.paired_chunks:
                    for pair in comparison_context.paired_chunks:
                        if pair.chunk_a.get("document_id") == doc.id:
                            _add(pair.chunk_a)
                        if pair.chunk_b.get("document_id") == doc.id:
                            _add(pair.chunk_b)
                if comparison_context.clustered_chunks:
                    for cluster in comparison_context.clustered_chunks:
                        if doc.id in cluster.chunks:
                            _add(cluster.chunks[doc.id])
                # Include unpaired chunks so document-specific facts (e.g. a cap-rate
                # table with no cross-doc counterpart) still reach the fact extractor.
                if comparison_context.unpaired_chunks:
                    for chunk in comparison_context.unpaired_chunks.get(doc.id, []):
                        _add(chunk)
                if doc_chunks:
                    chunks_per_doc[doc.id] = doc_chunks

            if chunks_per_doc:
                # Build citation context from ALL chunks (paired + clustered + unpaired).
                # This reuses the same _build_citation_context() logic as regular chat,
                # ensuring correct page resolution (bbox.page → page_number) and proper
                # bbox coordinates for all chunk types. Sent to frontend via SSE so that
                # clicking [Dn:pN] citations navigates to the correct page.
                if self.on_citation_context:
                    all_chunks_flat = [
                        c for doc_chunks in chunks_per_doc.values() for c in doc_chunks
                    ]
                    doc_id_to_index = {
                        doc.id: i + 1
                        for i, doc in enumerate(comparison_context.documents)
                    }
                    self.on_citation_context(all_chunks_flat, doc_id_to_index)

                fact_tasks = []
                for doc in comparison_context.documents:
                    if doc.id in chunks_per_doc:
                        fact_tasks.append(
                            self.fact_extractor.extract_facts(
                                chunks=chunks_per_doc[doc.id],
                                query=user_message,
                                comparison_aspects=(
                                    query_understanding.comparison_aspects
                                    if query_understanding
                                    else []
                                ),
                                document_name=doc.filename,
                                document_id=doc.id
                            )
                        )
                if fact_tasks:
                    document_facts = await asyncio.gather(*fact_tasks, return_exceptions=False)
                    # Guard: validate D-number ordering — document_facts[i] must match documents[i].
                    # asyncio.gather preserves input order, but log a warning if something is off.
                    docs_with_facts = [d for d in comparison_context.documents if d.id in chunks_per_doc]
                    for i, (doc, facts) in enumerate(zip(docs_with_facts, document_facts)):
                        if facts and hasattr(facts, "document_id") and facts.document_id != doc.id:
                            logger.warning(
                                "D-number ordering mismatch at index %d: expected doc %s, got %s",
                                i, doc.id, facts.document_id,
                                extra={"session_id": session_id},
                            )
                    logger.info(
                        "Fact extraction complete",
                        extra={
                            "session_id": session_id,
                            "num_documents": len(document_facts),
                            "total_facts": sum(len(f.facts) for f in document_facts if hasattr(f, "facts"))
                        }
                    )
        except Exception as e:
            logger.warning(
                f"Fact extraction failed, will use raw chunks: {e}",
                extra={"session_id": session_id},
                exc_info=True
            )
            document_facts = None

        # Serialize and store comparison context for SSE
        comparison_data = None
        try:
            comparison_data = {
                "documents": [
                    {"id": d.id, "filename": d.filename, "label": d.label}
                    for d in comparison_context.documents
                ],
                "paired_chunks": [
                    {
                        "chunk_a": {
                            "text": pair.chunk_a.get("text", ""),
                            "page": pair.chunk_a.get("page_number"),
                            "bbox": pair.chunk_a.get("bbox")
                        },
                        "chunk_b": {
                            "text": pair.chunk_b.get("text", ""),
                            "page": pair.chunk_b.get("page_number"),
                            "bbox": pair.chunk_b.get("bbox")
                        },
                        "similarity": float(pair.similarity),
                        "topic": pair.topic
                    }
                    for pair in comparison_context.paired_chunks
                ],
                "clustered_chunks": [
                    {
                        "chunks": {
                            doc_id: {
                                "text": chunk.get("text", ""),
                                "page": chunk.get("page_number"),
                                "bbox": chunk.get("bbox")
                            }
                            for doc_id, chunk in cluster.chunks.items()
                        },
                        "topic": cluster.topic,
                        "avg_similarity": float(cluster.avg_similarity)
                    }
                    for cluster in comparison_context.clustered_chunks
                ],
                "num_documents": comparison_context.num_documents
            }

            self.on_comparison_context(comparison_data)

            logger.debug(
                "Comparison context stored for SSE emission",
                extra={
                    "session_id": session_id,
                    "data_size": len(json.dumps(comparison_data))
                }
            )
        except Exception as e:
            logger.error(
                f"Failed to serialize comparison context: {e}",
                extra={"session_id": session_id},
                exc_info=True
            )

        # Build prompt
        # When include_history=False (standalone comparison), omit history from prompt.
        # Comparison prompts are already large; history rarely helps first-time comparisons.
        effective_recent = recent_messages if include_history else []
        effective_summary = summary_text if include_history else None

        if document_facts and any(f.facts for f in document_facts):
            prompt = self.prompt_builder.build_fact_based_comparison_prompt(
                docs=[
                    self.document_repo.get_by_id(doc.id)
                    for doc in comparison_context.documents
                ],
                document_facts=document_facts,
                user_message=user_message,
                comparison_aspects=(
                    query_understanding.comparison_aspects
                    if query_understanding
                    else []
                ),
                recent_messages=effective_recent,
                summary_text=effective_summary
            )
            prompt_mode = "fact_based"
            logger.info("Using fact-based comparison prompt", extra={"session_id": session_id, "prompt_type": "facts", "include_history": include_history})
        else:
            prompt = self.prompt_builder.build_comparison_prompt(
                user_message=user_message,
                comparison_context=comparison_context,
                recent_messages=effective_recent,
                summary_text=effective_summary,
                max_pairs=getattr(settings, "comparison_max_pairs", 8)
            )
            prompt_mode = "raw_chunks"
            logger.info("Using raw chunk comparison prompt", extra={"session_id": session_id, "prompt_type": "raw_chunks", "include_history": include_history})

        logger.debug(
            "Comparison prompt built",
            extra={"session_id": session_id, "prompt_length": len(prompt)}
        )

        # Stream LLM response
        assistant_message = ""
        usage_info = {}

        yield ("thinking", "Generating comparison response...")

        try:
            logger.info("Streaming comparison response from LLM", extra={"session_id": session_id, "user_id": user_id})
            llm_start = time.monotonic()

            async for event in self.llm_client.stream_chat(prompt):
                if event["type"] == "chunk":
                    chunk_text = event["text"]
                    assistant_message += chunk_text
                    yield ("chunk", chunk_text)
                elif event["type"] == "usage":
                    usage_info = event["data"]
                    logger.debug(
                        "LLM usage for comparison",
                        extra={
                            "session_id": session_id,
                            "usage": usage_info
                        }
                    )
                elif event["type"] == "error":
                    error_msg = event["data"]
                    logger.error(
                        f"LLM streaming error during comparison: {error_msg}",
                        extra={"session_id": session_id},
                        exc_info=True
                    )
                    raise RuntimeError(f"LLM streaming error: {error_msg}")

        except Exception as llm_error:
            logger.error(
                f"Failed during comparison LLM streaming: {llm_error}",
                extra={"session_id": session_id, "error_type": type(llm_error).__name__},
                exc_info=True
            )
            raise

        # Save messages with comparison metadata
        all_chunk_ids = []
        if comparison_context.paired_chunks:
            for pair in comparison_context.paired_chunks[:8]:
                if pair.chunk_a.get("id"):
                    all_chunk_ids.append(pair.chunk_a["id"])
                if pair.chunk_b.get("id"):
                    all_chunk_ids.append(pair.chunk_b["id"])

        if comparison_context.clustered_chunks:
            for cluster in comparison_context.clustered_chunks[:8]:
                for chunk in cluster.chunks.values():
                    if chunk.get("id"):
                        all_chunk_ids.append(chunk["id"])

        assistant_msg_id = await self.save_messages(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            source_chunks=all_chunk_ids,
            usage_data=usage_info,
            comparison_metadata=json.dumps(comparison_data) if comparison_data else None
        )

        if self.capture_io_log and self._io_log_repo and assistant_msg_id:
            eval_chunks = self._flatten_eval_chunks(chunks_per_doc)
            llm_duration_ms = int((time.monotonic() - llm_start) * 1000)
            self._io_log_repo.save_io_log(
                source_type="rag_chat",
                source_id=assistant_msg_id,
                stage="rag_chat_comparison",
                system_prompt=prompt,
                user_message=user_message,
                output=assistant_message,
                metadata={
                    "rag_eval_contract_version": RAG_EVAL_CONTRACT_VERSION,
                    "session_id": session_id,
                    "user_question": user_message,
                    "document_ids": document_ids,
                    "document_names": [d.filename for d in comparison_context.documents],
                    "chunk_ids": all_chunk_ids,
                    "chunk_count": len(eval_chunks),
                    "chunk_scores": [serialize_chunk_for_eval(chunk) for chunk in eval_chunks],
                    "chunk_texts": [chunk.get("text", "")[:500] for chunk in eval_chunks],
                    "query_understanding": serialize_query_understanding(query_understanding),
                    "num_documents": comparison_context.num_documents,
                    "num_paired": num_paired,
                    "num_clustered": num_clustered,
                    "comparison_mode": True,
                    "comparison_prompt_mode": prompt_mode,
                    "include_history": include_history,
                    "has_facts": (
                        document_facts is not None
                        and any(hasattr(f, "facts") and f.facts for f in document_facts)
                    ),
                    "total_duration_ms": int((time.monotonic() - comparison_start) * 1000),
                },
                input_tokens=usage_info.get("input_tokens", 0) if usage_info else 0,
                output_tokens=usage_info.get("output_tokens", 0) if usage_info else 0,
                cache_creation_tokens=usage_info.get("cache_creation_input_tokens", 0) if usage_info else 0,
                cache_read_tokens=usage_info.get("cache_read_input_tokens", 0) if usage_info else 0,
                duration_ms=llm_duration_ms,
                prompt_version=settings.rag_prompt_version,
            )

        logger.info(
            "Comparison chat complete",
            extra={
                "session_id": session_id,
                "response_length": len(assistant_message),
                "num_documents": comparison_context.num_documents,
                "num_pairs": len(comparison_context.paired_chunks) if comparison_context.paired_chunks else 0,
                "num_clusters": len(comparison_context.clustered_chunks) if comparison_context.clustered_chunks else 0
            }
        )
