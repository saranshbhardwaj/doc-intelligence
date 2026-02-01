"""Comparison flow handler for RAG chat."""
from __future__ import annotations

from typing import List, Dict, Optional, AsyncIterator, Callable
import json
import logging

from app.config import settings
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
        on_comparison_context: Callable[[Dict], None]
    ):
        self.db = db
        self.document_repo = DocumentRepository()
        self.comparison_retriever = comparison_retriever
        self.fact_extractor = fact_extractor
        self.prompt_builder = prompt_builder
        self.llm_client = llm_client
        self.save_messages = save_messages
        self.on_comparison_context = on_comparison_context

    async def handle(
        self,
        session_id: str,
        collection_id: Optional[str],
        user_message: str,
        user_id: Optional[str],
        document_ids: List[str],
        summary_text: Optional[str],
        recent_messages: List[Dict],
        query_understanding=None
    ) -> AsyncIterator[str]:
        logger.info(
            "Starting comparison retrieval",
            extra={
                "session_id": session_id,
                "num_documents": len(document_ids),
                "query_type": query_understanding.query_type.value if query_understanding else "comparison"
            }
        )

        comparison_context = await self.comparison_retriever.retrieve_for_comparison(
            query=user_message,
            document_ids=document_ids,
            collection_id=collection_id,
            chunks_per_doc=getattr(settings, "comparison_chunks_per_doc", 10),
            similarity_threshold=getattr(settings, "comparison_similarity_threshold", 0.6),
            max_documents=getattr(settings, "comparison_max_documents", 5),
            query_understanding=query_understanding,
            async_session=None
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

        # Extract facts (optional)
        document_facts = None
        try:
            import asyncio

            chunks_per_doc = {}
            for doc in comparison_context.documents:
                doc_chunks = []
                if comparison_context.paired_chunks:
                    for pair in comparison_context.paired_chunks:
                        if pair.chunk_a.get("document_id") == doc.id or pair.chunk_a.get("id"):
                            doc_chunks.append(pair.chunk_a)
                        if pair.chunk_b.get("document_id") == doc.id or pair.chunk_b.get("id"):
                            doc_chunks.append(pair.chunk_b)
                if comparison_context.clustered_chunks:
                    for cluster in comparison_context.clustered_chunks:
                        if doc.id in cluster.chunks:
                            doc_chunks.append(cluster.chunks[doc.id])
                if doc_chunks:
                    chunks_per_doc[doc.id] = doc_chunks

            if chunks_per_doc:
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
                recent_messages=recent_messages,
                summary_text=summary_text
            )
            logger.info("Using fact-based comparison prompt", extra={"session_id": session_id, "prompt_type": "facts"})
        else:
            prompt = self.prompt_builder.build_comparison_prompt(
                user_message=user_message,
                comparison_context=comparison_context,
                recent_messages=recent_messages,
                summary_text=summary_text,
                max_pairs=getattr(settings, "comparison_max_pairs", 8)
            )
            logger.info("Using raw chunk comparison prompt", extra={"session_id": session_id, "prompt_type": "raw_chunks"})

        logger.debug(
            "Comparison prompt built",
            extra={"session_id": session_id, "prompt_length": len(prompt)}
        )

        # Stream LLM response
        assistant_message = ""
        usage_info = {}

        try:
            logger.info("Streaming comparison response from LLM", extra={"session_id": session_id, "user_id": user_id})

            async for event in self.llm_client.stream_chat(prompt):
                if event["type"] == "chunk":
                    chunk_text = event["text"]
                    assistant_message += chunk_text
                    yield chunk_text
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

        await self.save_messages(
            session_id=session_id,
            user_message=user_message,
            assistant_message=assistant_message,
            source_chunks=all_chunk_ids,
            usage_data=usage_info,
            comparison_metadata=json.dumps(comparison_data) if comparison_data else None
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
