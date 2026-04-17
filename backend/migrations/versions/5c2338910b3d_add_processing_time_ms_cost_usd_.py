"""add processing_time_ms cost_usd completed_at to documents

Revision ID: 5c2338910b3d
Revises: 2c222fbb1e62
Create Date: 2026-02-23 01:27:27.852671

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c2338910b3d'
down_revision = '2c222fbb1e62'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('documents')}

    if 'processing_time_ms' not in cols:
        op.add_column(
            'documents',
            sa.Column('processing_time_ms', sa.Integer(), nullable=True)
        )

    if 'cost_usd' not in cols:
        # use sa.Float for float8 (double precision)
        op.add_column(
            'documents',
            sa.Column('cost_usd', sa.Float(), nullable=True)
        )

    if 'completed_at' not in cols:
        op.add_column(
            'documents',
            sa.Column('completed_at', sa.TIMESTAMP(timezone=True), nullable=True)
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = {c['name'] for c in inspector.get_columns('documents')}

    if 'completed_at' in cols:
        op.drop_column('documents', 'completed_at')

    if 'cost_usd' in cols:
        op.drop_column('documents', 'cost_usd')

    if 'processing_time_ms' in cols:
        op.drop_column('documents', 'processing_time_ms')