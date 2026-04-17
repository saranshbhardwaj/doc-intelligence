"""rename documents.name to filename

Revision ID: 90eb9e953431
Revises: 006
Create Date: 2026-02-22 17:01:01.269603

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '90eb9e953431'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        'documents',
        'name',
        new_column_name='filename'
    )


def downgrade() -> None:
    op.alter_column(
        'documents',
        'filename',
        new_column_name='name'
    )