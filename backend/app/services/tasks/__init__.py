# backend/app/services/tasks/__init__.py
"""
Celery task pipelines for document processing.

Two main pipelines:
1. Extraction Mode: Parse → Chunk → Summarize → Extract
2. Chat Mode: Parse → Chunk → Embed → Store

Import the pipeline starter functions:
    from app.services.tasks import start_extraction_chain, start_chat_indexing_chain
"""

# Import pipeline entry points
from app.services.tasks.extraction import start_extraction_chain
from app.services.tasks.chat import start_chat_indexing_chain

# Import individual tasks (for testing or manual invocation)
from app.services.tasks.extraction import (
    parse_document_task,
    chunk_document_task,
    summarize_context_task,
    extract_structured_task,
)
from app.services.tasks.chat import (
    embed_chunks_task,
    store_vectors_task,
)

__all__ = [
    # Pipeline starters
    "start_extraction_chain",
    "start_chat_indexing_chain",
    # Individual tasks
    "parse_document_task",
    "chunk_document_task",
    "summarize_context_task",
    "extract_structured_task",
    "embed_chunks_task",
    "store_vectors_task",
]
