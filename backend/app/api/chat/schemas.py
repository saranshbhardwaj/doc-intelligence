"""Request/Response schemas for chat API endpoints."""

from typing import List, Optional
from pydantic import BaseModel, Field


class ComparisonConfirmRequest(BaseModel):
    """Request schema for confirming comparison with selected documents."""

    document_ids: List[str] = Field(
        ...,
        description="List of document IDs selected for comparison (2-3 documents)",
        min_length=0,
        max_length=3
    )
    original_query: str = Field(
        ...,
        description="Original user query that triggered comparison detection",
        min_length=1,
        max_length=4000
    )
    skip_comparison: bool = Field(
        default=False,
        description="If True, skip comparison and use normal RAG mode"
    )
