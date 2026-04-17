"""add parser_used to documents

Revision ID: 2c222fbb1e62
Revises: 2a9c2b132df2
Create Date: 2026-02-23 01:18:35.869595

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2c222fbb1e62'
down_revision = '2a9c2b132df2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('documents')]

    if 'parser_used' not in cols:
        op.add_column(
            'documents',
            sa.Column('parser_used', sa.String(50), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('documents')]

    if 'parser_used' in cols:
        op.drop_column('documents', 'parser_used')