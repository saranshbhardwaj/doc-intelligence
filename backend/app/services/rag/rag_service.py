# backend/app/services/rag/rag_service.py
"""
RAG (Retrieval-Augmented Generation) service for Chat Mode.

Handles:
- Real-time chat responses (NO Celery - direct streaming)
- Vector similarity search to find relevant chunks
- Claude API streaming for chat responses
"""
from typing import List, Dict, Any, Optional, AsyncIterator
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db_models_chat import DocumentChunk, CollectionDocument
from app.repositories.chat_repository import ChatRepository
from app.services.embeddings import get_embedding_provider
from app.services.llm_client import LLMClient
from app.config import settings
from app.utils.logging import logger


class RAGService:
    """
    RAG service for real-time chat responses.

    Workflow:
    1. User asks a question
    2. Embed the question
    3. Vector search for relevant chunks
    4. Build prompt with chunks + question
    5. Stream response from Claude
    6. Save chat history
    """

    def __init__(self, db: Session):
        """
        Initialize RAG service.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.embedder = get_embedding_provider()
        # Using cheap model for testing - switch back to llm_model for production
        self.llm_client = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.cheap_llm_model,  # Using Haiku for cost-effective testing
            max_tokens=settings.cheap_llm_max_tokens,
            max_input_chars=settings.llm_max_input_chars,
            timeout_seconds=settings.cheap_llm_timeout_seconds,
        )

    async def chat(
        self,
        session_id: str,
        collection_id: str,
        user_message: str,
        num_chunks: int = 5,
        similarity_threshold: float = 0.3,
        document_ids: Optional[List[str]] = None
    ) -> AsyncIterator[str]:
        """
        Generate streaming chat response using RAG.

        Args:
            session_id: Chat session ID
            collection_id: Collection ID to search within
            user_message: User's question/message
            num_chunks: Number of chunks to retrieve (default: 5)
            similarity_threshold: Minimum similarity score (0-1, default: 0.3)
            document_ids: Optional filter by specific documents

        Yields:
            Streaming response chunks from Claude
        """
        # Edge case: Validate user_message is not empty
        if not user_message or not user_message.strip():
            logger.warning(
                "Empty user message received",
                extra={"session_id": session_id, "collection_id": collection_id}
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
                f"Invalid similarity_threshold: {similarity_threshold}, using default 0.3",
                extra={"session_id": session_id}
            )
            similarity_threshold = 0.3

        # Step 1: Embed the user question
        logger.info(f"Generating embedding for user query", extra={"session_id": session_id})
        query_embedding = self.embedder.embed_text(user_message)

        # Step 2: Vector similarity search
        relevant_chunks = await self._vector_search(
            query_embedding=query_embedding,
            collection_id=collection_id,
            limit=num_chunks,
            similarity_threshold=similarity_threshold,
            document_ids=document_ids
        )

        logger.info(
            f"Retrieved {len(relevant_chunks)} relevant chunks",
            extra={
                "session_id": session_id,
                "collection_id": collection_id,
                "num_chunks": len(relevant_chunks)
            }
        )

        # Edge case: Handle when no relevant chunks are found
        if not relevant_chunks:
            logger.warning(
                "No relevant chunks found for user query",
                extra={
                    "session_id": session_id,
                    "collection_id": collection_id,
                    "query_length": len(user_message),
                    "similarity_threshold": similarity_threshold
                }
            )
            # Continue with empty context - let LLM respond that it can't find relevant info

        # Step 3: Build prompt with context
        prompt = self._build_rag_prompt(user_message, relevant_chunks)

        # Step 4: Stream response from Claude with error handling
        full_response = ""
        try:
            async for chunk in self.llm_client.stream_chat(prompt):
                full_response += chunk
                yield chunk

            # Step 5: Save chat history (only if streaming completed successfully)
            await self._save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=full_response,
                source_chunks=[chunk["id"] for chunk in relevant_chunks]
            )

        except Exception as stream_error:
            # Edge case: LLM streaming failed mid-response
            logger.error(
                f"LLM streaming failed: {stream_error}",
                extra={
                    "session_id": session_id,
                    "collection_id": collection_id,
                    "partial_response_length": len(full_response),
                    "error_type": type(stream_error).__name__
                },
                exc_info=True
            )

            # Save partial response if we got any content before failure
            if full_response:
                try:
                    await self._save_chat_messages(
                        session_id=session_id,
                        user_message=user_message,
                        assistant_message=f"{full_response}\n\n[Error: Response was interrupted due to technical issues]",
                        source_chunks=[chunk["id"] for chunk in relevant_chunks]
                    )
                except Exception as save_error:
                    logger.error(
                        f"Failed to save partial chat response: {save_error}",
                        extra={"session_id": session_id}
                    )

            # Re-raise the streaming error
            raise

    async def _vector_search(
        self,
        query_embedding: List[float],
        collection_id: str,
        limit: int,
        similarity_threshold: float,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform vector similarity search using pgvector.

        Args:
            query_embedding: Query embedding vector
            collection_id: Collection ID
            limit: Maximum number of results
            similarity_threshold: Minimum cosine similarity (0-1)
            document_ids: Optional document filter

        Returns:
            List of chunk dicts with text, similarity, metadata
        """
        # Build query
        stmt = select(
            DocumentChunk.id,
            DocumentChunk.text,
            DocumentChunk.document_id,
            DocumentChunk.page_number,
            DocumentChunk.section_type,
            DocumentChunk.section_heading,
            DocumentChunk.is_tabular,
            CollectionDocument.filename,
            # Cosine similarity using pgvector
            (DocumentChunk.embedding.cosine_distance(query_embedding)).label("distance")
        ).join(
            CollectionDocument,
            DocumentChunk.document_id == CollectionDocument.id
        ).where(
            CollectionDocument.collection_id == collection_id
        )

        # Filter by specific documents if provided
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        # Order by similarity (lower distance = higher similarity)
        stmt = stmt.order_by("distance").limit(limit)

        # Execute query
        results = self.db.execute(stmt).fetchall()

        # Convert to dicts
        chunks = []
        for row in results:
            # Convert cosine distance to similarity score (0-1, higher is better)
            # pgvector's cosine_distance returns values in range [0, 2]:
            # - 0 = identical vectors (cosine similarity = 1)
            # - 1 = orthogonal vectors (cosine similarity = 0)
            # - 2 = opposite vectors (cosine similarity = -1)
            # Formula: similarity = 1 - (distance / 2) maps [0, 2] → [1, 0]
            distance = row.distance
            similarity = 1 - (distance / 2)

            # Apply similarity threshold
            if similarity < similarity_threshold:
                continue

            chunks.append({
                "id": row.id,
                "text": row.text,
                "similarity": round(similarity, 4),
                "document_id": row.document_id,
                "filename": row.filename,
                "page_number": row.page_number,
                "section_type": row.section_type,
                "section_heading": row.section_heading,
                "is_tabular": row.is_tabular
            })

        return chunks

    def _build_rag_prompt(
        self,
        user_message: str,
        relevant_chunks: List[Dict[str, Any]]
    ) -> str:
        """
        Build RAG prompt with retrieved context.

        Args:
            user_message: User's question
            relevant_chunks: Retrieved chunks from vector search

        Returns:
            Formatted prompt for Claude
        """
        # Edge case: Handle empty chunks
        if not relevant_chunks:
            # Build prompt without context - let LLM know no relevant documents found
            prompt = f"""You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts.

IMPORTANT INSTRUCTIONS:
- Only use information from the provided document excerpts
- If the documents don't contain relevant information, say so clearly
- Be concise but thorough

DOCUMENT EXCERPTS:

[No relevant document excerpts found for this query]

---

USER QUESTION: {user_message}

ANSWER:"""
            return prompt

        # Build context from retrieved chunks
        context_sections = []
        for i, chunk in enumerate(relevant_chunks, 1):
            source_info = f"Source {i}: {chunk['filename']}"
            if chunk.get('page_number'):
                source_info += f" (Page {chunk['page_number']})"
            if chunk.get('section_heading'):
                source_info += f" - {chunk['section_heading']}"

            context_sections.append(f"{source_info}\n{chunk['text']}\n")

        context = "\n---\n\n".join(context_sections)

        # Build full prompt
        prompt = f"""You are a financial analyst AI assistant. Answer the user's question based on the provided document excerpts.

IMPORTANT INSTRUCTIONS:
- Only use information from the provided document excerpts
- If the documents don't contain relevant information, say so clearly
- Cite sources by mentioning the document name and page number
- Be concise but thorough
- Use bullet points for clarity when appropriate

DOCUMENT EXCERPTS:

{context}

---

USER QUESTION: {user_message}

ANSWER:"""

        return prompt

    async def _save_chat_messages(
        self,
        session_id: str,
        user_message: str,
        assistant_message: str,
        source_chunks: List[str]
    ):
        """
        Save user message and assistant response to database.

        Args:
            session_id: Chat session ID
            user_message: User's message
            assistant_message: Assistant's response
            source_chunks: List of chunk IDs used for response
        """
        import json

        chat_repo = ChatRepository()

        try:
            # Get current message count for ordering
            message_count = chat_repo.get_message_count(session_id)

            # Edge case: Validate message_count
            if message_count is None:
                logger.warning(
                    f"get_message_count returned None for session {session_id}, defaulting to 0",
                    extra={"session_id": session_id}
                )
                message_count = 0

            # Save user message
            user_msg_saved = chat_repo.save_message(
                session_id=session_id,
                role="user",
                content=user_message,
                message_index=message_count,
                retrieval_query=user_message
            )

            # Edge case: Check if user message save succeeded
            if not user_msg_saved:
                logger.error(
                    "Failed to save user message to database",
                    extra={"session_id": session_id}
                )
                raise ValueError("Failed to save user message")

            # Save assistant message
            assistant_msg_saved = chat_repo.save_message(
                session_id=session_id,
                role="assistant",
                content=assistant_message,
                message_index=message_count + 1,
                source_chunks=json.dumps(source_chunks),
                num_chunks_retrieved=len(source_chunks),
                model_used=settings.cheap_llm_model,  # Using Haiku for testing
                # TODO: Calculate actual tokens and cost
                tokens_used=None,
                cost_usd=None
            )

            # Edge case: Check if assistant message save succeeded
            if not assistant_msg_saved:
                logger.error(
                    "Failed to save assistant message to database",
                    extra={"session_id": session_id}
                )
                raise ValueError("Failed to save assistant message")

            # Update session message count (increment by 2 for user + assistant messages)
            count_updated = chat_repo.increment_message_count(session_id, increment=2)

            # Edge case: Check if message count increment succeeded
            if not count_updated:
                logger.warning(
                    "Failed to increment message count for session",
                    extra={"session_id": session_id}
                )
                # Don't raise - messages are saved, count mismatch is recoverable

            logger.info(
                f"Saved chat messages",
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
        stmt = select(ChatMessage).where(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.message_index)

        if limit:
            stmt = stmt.limit(limit)

        messages = self.db.execute(stmt).scalars().all()

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
