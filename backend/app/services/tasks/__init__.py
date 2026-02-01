# backend/app/services/tasks/__init__.py
"""
Celery task pipelines for document processing.

Three main pipelines:
1. Extraction Mode: Parse → Chunk → Summarize → Extract
2. Chat Mode: Parse → Chunk → Embed → Store
3. Workflow Mode: Retrieve Context → Generate Artifact

Import the pipeline starter functions:
    from app.services.tasks import start_extraction_chain, start_document_indexing_chain, start_workflow_chain
"""

# Import pipeline entry points
from app.verticals.private_equity.extraction.tasks import start_extraction_chain
from app.services.tasks.document_processor import start_document_indexing_chain
from app.verticals.private_equity.workflows.tasks import start_workflow_chain

# Import individual tasks (for testing or manual invocation)
from app.verticals.private_equity.extraction.tasks import (
    parse_document_task,
    chunk_document_task,
    summarize_context_task,
    extract_structured_task,
)
from app.services.tasks.document_processor import (
    embed_chunks_task,
    store_vectors_task,
)
from app.verticals.private_equity.workflows.tasks import (
    prepare_context_task,
    generate_artifact_task,
)

__all__ = [
    # Pipeline starters
    "start_extraction_chain",
    "start_document_indexing_chain",
    "start_workflow_chain",
    # Individual tasks
    "parse_document_task",
    "chunk_document_task",
    "summarize_context_task",
    "extract_structured_task",
    "embed_chunks_task",
    "store_vectors_task",
    "prepare_context_task",
    "generate_artifact_task",
]
