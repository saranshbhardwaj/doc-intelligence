# backend/app/services/rag/rag_service.py
"""RAGService orchestrates chat flow using modular components.

Responsibilities limited to orchestration:
 1. Load & maybe summarize history via ConversationMemory
 2. Perform vector retrieval
 3. Enforce budget trims
 4. Build final prompt
 5. Stream LLM response
 6. Persist messages

Other concerns (prompt construction, memory management, budget logic) are delegated.
"""
from typing import List, Dict, Any, Optional, AsyncIterator
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db_models_chat import DocumentChunk, CollectionDocument, ChatMessage
from app.repositories.chat_repository import ChatRepository
from app.services.embeddings import get_embedding_provider
from app.services.llm_client import LLMClient
from app.config import settings
from app.utils.logging import logger
from app.services.rag.prompt_builder import PromptBuilder
from app.services.rag.memory import ConversationMemory
from app.services.rag.budget_enforcer import BudgetEnforcer


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
        self.llm_client = LLMClient(
            api_key=settings.anthropic_api_key,
            model=settings.cheap_llm_model,
            max_tokens=settings.cheap_llm_max_tokens,
            max_input_chars=settings.llm_max_input_chars,
            timeout_seconds=settings.cheap_llm_timeout_seconds,
        )
        # Inject modular components
        self.prompt_builder = PromptBuilder()
        self.memory = ConversationMemory(self.llm_client)
        self.budget = BudgetEnforcer()

    async def chat(
        self,
        session_id: str,
        collection_id: str,
        user_message: str,
        user_id: Optional[str] = None,
        num_chunks: int = 5,
        similarity_threshold: float = 0.0,  # Changed from 0.3 to 0.0 - return top chunks regardless of similarity
        document_ids: Optional[List[str]] = None
    ) -> AsyncIterator[str]:
        """
        Generate streaming chat response using RAG.

        Args:
            session_id: Chat session ID
            collection_id: Collection ID to search within
            user_message: User's question/message
            user_id: Optional user ID for logging
            num_chunks: Number of chunks to retrieve (default: 5)
            similarity_threshold: Minimum similarity score (0-1, default: 0.0 = return all top chunks)
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
                f"Invalid similarity_threshold: {similarity_threshold}, using default 0.0",
                extra={"session_id": session_id}
            )
            similarity_threshold = 0.0

        # STEP 0: History & optional summarization via memory component
        history_messages = self.memory.load_history(session_id)
        summary_text, recent_messages = await self.memory.maybe_summarize(session_id, history_messages, user_message)

        # ------------------------------------------------------------------
        # STEP 1: Embed the user question
        logger.info(
            f"Generating embedding for user query",
            extra={"user_id": user_id, "session_id": session_id}
        )
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
                "user_id": user_id,
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
                    "user_id": user_id,
                    "session_id": session_id,
                    "collection_id": collection_id,
                    "query_length": len(user_message),
                    "similarity_threshold": similarity_threshold
                }
            )
            # Continue with empty context - let LLM respond that it can't find relevant info

        # Step 3: Budget enforcement
        summary_text, recent_messages, relevant_chunks = await self.budget.enforce(
            memory=self.memory,
            user_message=user_message,
            summary_text=summary_text,
            recent_messages=recent_messages,
            relevant_chunks=relevant_chunks
        )

        # Cache summary if produced
        if summary_text:
            self.memory.cache_summary(session_id, len(history_messages), summary_text)

        # Step 4: Build prompt
        prompt = self.prompt_builder.build(
            user_message=user_message,
            relevant_chunks=relevant_chunks,
            recent_messages=recent_messages,
            summary_text=summary_text
        )

        # Step 5: Stream response from Claude with error handling
        full_response = ""
        try:
            async for chunk in self.llm_client.stream_chat(prompt):
                full_response += chunk
                yield chunk

            # Persist chat messages only after successful streaming
            await self._save_chat_messages(
                session_id=session_id,
                user_message=user_message,
                assistant_message=full_response,
                source_chunks=[chunk["id"] for chunk in relevant_chunks]
            )
        except Exception as stream_error:
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
            # Save partial response if any
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

    # All conversation memory & budget helpers moved to modular components.
