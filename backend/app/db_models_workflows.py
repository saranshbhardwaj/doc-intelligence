"""Database models for workflow templates and workflow executions."""
from sqlalchemy import Column, String, Integer, DateTime, Text, Float, Boolean, ForeignKey, JSON, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base
import uuid


class Workflow(Base):
    """Reusable workflow template (e.g., Investment Memo, Red Flags Summary).

    Stores prompt template and variable schema so runs are reproducible & versioned.
    """
    __tablename__ = "workflows"
    __table_args__ = (
        Index("idx_workflows_name", "name"),
        Index("idx_workflows_domain", "domain"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    domain = Column(String(50), nullable=False, default="private_equity")  # private_equity | real_estate
    category = Column(String(100), nullable=True)  # deal_flow | diligence | portfolio | custom
    description = Column(Text, nullable=True)

    # Template definition
    prompt_template = Column(Text, nullable=False)  # Jinja2 style template (full technical prompt)
    user_prompt_template = Column(Text, nullable=True)  # User-facing simplified prompt for editing
    user_prompt_max_length = Column(Integer, nullable=True)  # Character limit for user edits (default 1000)
    variables_schema = Column(JSONB, nullable=True)  # JSON schema for variables
    output_schema = Column(JSONB, nullable=True)  # JSON Schema for expected output
    retrieval_spec_json = Column(JSONB, nullable=True)  # Retrieval specification for workflow sections
    output_format = Column(String(50), nullable=False, default="markdown")  # markdown | json | pptx | xlsx | pdf
    min_documents = Column(Integer, nullable=False, default=1)
    max_documents = Column(Integer, nullable=True)  # null = no upper bound

    version = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=True)
    deprecated_at = Column(DateTime(timezone=True), nullable=True)  # When workflow was deprecated
    replacement_workflow_id = Column(String(36), nullable=True)  # Points to replacement workflow

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    # NOTE: No cascade delete - preserve historical runs even if workflow template is deleted
    runs = relationship("WorkflowRun", back_populates="workflow")


class WorkflowRun(Base):
    """Execution instance of a workflow.

    Tracks variables, document scope, artifacts produced and cost metrics.
    References canonical documents table (not collection_documents).
    """
    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("idx_workflow_runs_workflow_id", "workflow_id"),
        Index("idx_workflow_runs_user_id", "user_id"),
        Index("idx_workflow_runs_collection_id", "collection_id"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # SET NULL on delete - preserve run history even if workflow template is deleted
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(String(100), nullable=False)
    collection_id = Column(String(36), ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)

    # Workflow snapshot - preserves context even if workflow is deleted
    workflow_snapshot = Column(JSONB, nullable=True)  # {name, description, version, category}

    # Document scope (references canonical documents, not collection_documents)
    document_ids = Column(JSONB, nullable=True)  # JSON array of document IDs
    variables = Column(JSONB, nullable=True)  # JSON of provided variables

    # Strategy used (context assembly)
    mode = Column(String(30), nullable=False, default="single_doc")  # single_doc | multi_doc
    strategy = Column(String(30), nullable=True)  # full_context | retrieval | hybrid

    # Status lifecycle
    status = Column(String(20), nullable=False, default="queued")  # queued | running | completed | failed
    error_message = Column(Text, nullable=True)

    # Artifacts
    artifact = Column(JSONB, nullable=True)  # JSON describing produced files/structured output
    output_format = Column(String(50), nullable=True)

    # Metrics
    token_usage = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    currency = Column(String(10), nullable=True)  # ISO currency code (USD, EUR, GBP, etc.)
    citations_count = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=True)
    citation_invalid_count = Column(Integer, nullable=True)
    validation_errors = Column(JSONB, nullable=True)  # List of validation errors
    context_stats = Column(JSONB, nullable=True)  # Retrieval stats
    section_summaries = Column(JSONB, nullable=True)  # Map-reduce section summaries with citations

    version = Column(Integer, nullable=False, default=1)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workflow = relationship("Workflow", back_populates="runs")
