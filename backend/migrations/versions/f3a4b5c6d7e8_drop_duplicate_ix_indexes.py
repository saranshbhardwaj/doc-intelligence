"""Drop duplicate ix_ indexes shadowing canonical idx_ indexes (Supabase perf lint)

SQLAlchemy's index=True auto-creates ix_<table>_<col> indexes at the same time as
explicit op.create_index("idx_...") calls in migrations, producing identical duplicate
pairs. This migration drops the 9 redundant ix_-prefixed copies; the idx_-prefixed
canonical indexes remain untouched.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-03-01 00:00:00.000000
"""
from alembic import op


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None

_DUPLICATE_INDEXES = [
    # (index_name, table_name, [columns])
    ("ix_documents_content_hash", "documents", ["content_hash"]),
    ("ix_documents_org_id", "documents", ["org_id"]),
    ("ix_documents_user_id", "documents", ["user_id"]),
    ("ix_extractions_org_id", "extractions", ["org_id"]),
    ("ix_extractions_user_id", "extractions", ["user_id"]),
    ("ix_feedback_org_id", "feedback", ["org_id"]),
    ("ix_feedback_user_id", "feedback", ["user_id"]),
    ("ix_template_fill_runs_template_id", "template_fill_runs", ["template_id"]),
    ("ix_workflow_runs_org_id", "workflow_runs", ["org_id"]),
]


def upgrade() -> None:
    for index_name, _, __ in _DUPLICATE_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    for index_name, table_name, columns in _DUPLICATE_INDEXES:
        op.create_index(index_name, table_name, columns)
