"""Database models for Excel template filling feature."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ExcelTemplate(Base):
    """
    Excel template model for Real Estate vertical.

    Stores reusable Excel templates that can be filled with data from PDFs.
    """
    __tablename__ = "excel_templates"

    # Primary key
    id = Column(String(36), primary_key=True)

    # Ownership
    user_id = Column(String(100), nullable=False, index=True)

    # Template metadata
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100), index=True)  # 'offering_memo', 'rent_roll', 'investment_summary', 'custom'

    # File storage
    file_path = Column(String(512), nullable=False)  # R2/S3 path
    file_extension = Column(String(10), nullable=False, default=".xlsx")  # .xlsx or .xlsm
    file_size_bytes = Column(Integer, nullable=False)
    content_hash = Column(String(64), nullable=False)  # SHA256 for deduplication

    # Template schema (detected fillable cells, formula cells, sheets)
    # Example structure:
    # {
    #   "sheets": [
    #     {
    #       "name": "Summary",
    #       "fillable_cells": [
    #         {"cell": "B2", "label": "Property Name", "row": 1, "col": 1, "type": "text"},
    #         {"cell": "C5", "label": "Total SF", "row": 4, "col": 2, "type": "number"}
    #       ],
    #       "formula_cells": ["D10", "E20"],
    #       "grid": [[{"value": "Label", "type": "label"}, {"value": "", "type": "fillable"}]]
    #     }
    #   ],
    #   "total_fields": 45
    # }
    schema_metadata = Column(JSONB)

    # Usage tracking
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True))

    # Status
    active = Column(Boolean, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    # No cascade - fill runs preserved with template_id=NULL when template deleted (matches DB ondelete='SET NULL')
    fill_runs = relationship("TemplateFillRun", back_populates="template")

    def __repr__(self):
        return f"<ExcelTemplate(id={self.id}, name={self.name}, user_id={self.user_id})>"


class TemplateFillRun(Base):
    """
    Template fill run model.

    Represents a single execution of filling an Excel template with data from a PDF.
    Tracks the full lifecycle: field detection → mapping → extraction → filling.
    """
    __tablename__ = "template_fill_runs"

    # Primary key
    id = Column(String(36), primary_key=True)

    # Foreign keys
    template_id = Column(String(36), ForeignKey("excel_templates.id", ondelete="SET NULL"))
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="SET NULL"))
    user_id = Column(String(100), nullable=False, index=True)

    # Template snapshot (preserve context if template is deleted)
    # Stores: {name, description, schema_metadata}
    template_snapshot = Column(JSONB)

    # Field mapping (user-editable)
    # Structure:
    # {
    #   "pdf_fields": [
    #     {
    #       "id": "f1",
    #       "name": "Property Name",
    #       "type": "text",
    #       "sample_value": "Sunset Plaza",
    #       "confidence": 0.95,
    #       "source_page": 1
    #     }
    #   ],
    #   "mappings": [
    #     {
    #       "pdf_field_id": "f1",
    #       "excel_cell": "B2",
    #       "excel_sheet": "Summary",
    #       "excel_label": "Property Name",
    #       "status": "auto_mapped",  # auto_mapped | user_edited | manual | unmapped
    #       "confidence": 0.92
    #     }
    #   ]
    # }
    field_mapping = Column(JSONB, nullable=False, default={})

    # Extracted data from PDF
    # Structure:
    # {
    #   "f1": {
    #     "value": "Sunset Plaza",
    #     "confidence": 0.95,
    #     "source_page": 1,
    #     "source_text": "...Sunset Plaza is a premium...",
    #     "user_edited": false
    #   }
    # }
    extracted_data = Column(JSONB, default={})

    # Output artifact (filled Excel file)
    # Same pattern as WorkflowRun:
    # {"backend": "r2", "key": "fills/abc123.xlsx", "size": 45120}
    # OR {"backend": "inline", "data": "base64..."}
    artifact = Column(JSONB)

    # Processing status
    # States: queued → detecting_fields → mapping → extracting → filling → completed/failed
    status = Column(String(20), default="queued", index=True, nullable=False)
    current_stage = Column(String(50))

    # Stage completion flags (for resume capability)
    field_detection_completed = Column(Boolean, default=False)
    auto_mapping_completed = Column(Boolean, default=False)
    user_review_completed = Column(Boolean, default=False)  # User reviewed/edited mapping
    extraction_completed = Column(Boolean, default=False)
    filling_completed = Column(Boolean, default=False)

    # Metrics
    total_fields_detected = Column(Integer)
    total_fields_mapped = Column(Integer)
    total_fields_filled = Column(Integer)
    auto_mapped_count = Column(Integer)  # How many fields were auto-mapped
    user_edited_count = Column(Integer)  # How many mappings user changed

    # Cost tracking
    cost_usd = Column(Float, default=0.0)
    processing_time_ms = Column(Integer)

    # Error handling
    error_stage = Column(String(50))
    error_message = Column(Text)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    template = relationship("ExcelTemplate", back_populates="fill_runs")
    document = relationship("Document", foreign_keys=[document_id])
    job_states = relationship("JobState", back_populates="template_fill_run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TemplateFillRun(id={self.id}, template_id={self.template_id}, status={self.status})>"
