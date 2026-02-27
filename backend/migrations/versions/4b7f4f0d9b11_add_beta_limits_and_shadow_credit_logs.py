"""add beta limits and shadow credit logs

Revision ID: 4b7f4f0d9b11
Revises: ed9083b88fa4
Create Date: 2026-02-24 11:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "4b7f4f0d9b11"
down_revision = "ed9083b88fa4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("workflow_runs_limit", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "users",
        sa.Column("extractions_limit", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "users",
        sa.Column("template_fill_runs_limit", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "users",
        sa.Column("chat_messages_limit", sa.Integer(), nullable=False, server_default="30"),
    )

    op.create_table(
        "shadow_credit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("operation_type", sa.String(length=50), nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("shadow_credits", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shadow_credit_logs_user_id", "shadow_credit_logs", ["user_id"], unique=False)
    op.create_index("ix_shadow_credit_logs_org_id", "shadow_credit_logs", ["org_id"], unique=False)
    op.create_index("ix_shadow_credit_logs_operation_type", "shadow_credit_logs", ["operation_type"], unique=False)
    op.create_index("ix_shadow_credit_logs_reference_id", "shadow_credit_logs", ["reference_id"], unique=False)
    op.create_index("ix_shadow_credit_logs_created_at", "shadow_credit_logs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shadow_credit_logs_created_at", table_name="shadow_credit_logs")
    op.drop_index("ix_shadow_credit_logs_reference_id", table_name="shadow_credit_logs")
    op.drop_index("ix_shadow_credit_logs_operation_type", table_name="shadow_credit_logs")
    op.drop_index("ix_shadow_credit_logs_org_id", table_name="shadow_credit_logs")
    op.drop_index("ix_shadow_credit_logs_user_id", table_name="shadow_credit_logs")
    op.drop_table("shadow_credit_logs")

    op.drop_column("users", "chat_messages_limit")
    op.drop_column("users", "template_fill_runs_limit")
    op.drop_column("users", "extractions_limit")
    op.drop_column("users", "workflow_runs_limit")
