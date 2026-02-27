"""add shadow credit lifecycle columns

Revision ID: a7fd572ad161
Revises: 4b7f4f0d9b11
Create Date: 2026-02-24 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7fd572ad161"
down_revision = "4b7f4f0d9b11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shadow_credit_logs",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="committed"),
    )
    op.add_column("shadow_credit_logs", sa.Column("reversed_at", sa.DateTime(), nullable=True))
    op.add_column("shadow_credit_logs", sa.Column("reverse_reason", sa.Text(), nullable=True))
    op.create_index("ix_shadow_credit_logs_status", "shadow_credit_logs", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shadow_credit_logs_status", table_name="shadow_credit_logs")
    op.drop_column("shadow_credit_logs", "reverse_reason")
    op.drop_column("shadow_credit_logs", "reversed_at")
    op.drop_column("shadow_credit_logs", "status")
