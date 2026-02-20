"""Add missing database indexes for scalability.

Adds indexes on:
- Foreign keys without indexes (for CASCADE deletes and joins)
- Status columns used in filtering
- Composite indexes for common query patterns

Revision ID: 004
Revises: 003
Create Date: 2026-02-09 12:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    """Add missing indexes for performance optimization."""

    # ========================================
    # Foreign Key Indexes (CASCADE deletes)
    # ========================================

    # parser_outputs.extraction_id - used in CASCADE deletes
    op.create_index(
        "idx_parser_outputs_extraction_id",
        "parser_outputs",
        ["extraction_id"]
    )

    # template_fill_runs FKs
    op.create_index(
        "idx_template_fill_runs_template_id",
        "template_fill_runs",
        ["template_id"]
    )
    op.create_index(
        "idx_template_fill_runs_document_id",
        "template_fill_runs",
        ["document_id"]
    )

    # feedback polymorphic FKs (all 4 entity references)
    op.create_index(
        "idx_feedback_chat_message_id",
        "feedback",
        ["chat_message_id"]
    )
    op.create_index(
        "idx_feedback_workflow_run_id",
        "feedback",
        ["workflow_run_id"]
    )
    op.create_index(
        "idx_feedback_template_fill_run_id",
        "feedback",
        ["template_fill_run_id"]
    )
    op.create_index(
        "idx_feedback_extraction_id",
        "feedback",
        ["extraction_id"]
    )

    # usage_logs.extraction_id - used in CASCADE deletes
    op.create_index(
        "idx_usage_logs_extraction_id",
        "usage_logs",
        ["extraction_id"]
    )

    # workflows.replacement_workflow_id - self-referential FK
    op.create_index(
        "idx_workflows_replacement_workflow_id",
        "workflows",
        ["replacement_workflow_id"]
    )

    # ========================================
    # Status Indexes (frequently filtered)
    # ========================================

    # workflow_runs.status - used in list queries with status filter
    op.create_index(
        "idx_workflow_runs_status",
        "workflow_runs",
        ["status"]
    )

    # ========================================
    # Composite Indexes (common query patterns)
    # ========================================

    # template_fill_runs(user_id, org_id, status) - list runs for user with status filter
    op.create_index(
        "idx_template_fill_runs_user_org_status",
        "template_fill_runs",
        ["user_id", "org_id", "status"]
    )

    # workflow_runs(user_id, org_id) - list runs for user
    op.create_index(
        "idx_workflow_runs_user_org",
        "workflow_runs",
        ["user_id", "org_id"]
    )


def downgrade():
    """Remove all indexes added in this migration."""

    # Composite indexes
    op.drop_index("idx_workflow_runs_user_org", "workflow_runs")
    op.drop_index("idx_template_fill_runs_user_org_status", "template_fill_runs")

    # Status indexes
    op.drop_index("idx_workflow_runs_status", "workflow_runs")

    # Self-referential FK
    op.drop_index("idx_workflows_replacement_workflow_id", "workflows")

    # Usage logs FK
    op.drop_index("idx_usage_logs_extraction_id", "usage_logs")

    # Feedback polymorphic FKs
    op.drop_index("idx_feedback_extraction_id", "feedback")
    op.drop_index("idx_feedback_template_fill_run_id", "feedback")
    op.drop_index("idx_feedback_workflow_run_id", "feedback")
    op.drop_index("idx_feedback_chat_message_id", "feedback")

    # Template fill runs FKs
    op.drop_index("idx_template_fill_runs_document_id", "template_fill_runs")
    op.drop_index("idx_template_fill_runs_template_id", "template_fill_runs")

    # Parser outputs FK
    op.drop_index("idx_parser_outputs_extraction_id", "parser_outputs")
