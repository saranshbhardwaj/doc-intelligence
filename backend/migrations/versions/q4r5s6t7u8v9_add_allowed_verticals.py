"""Add allowed_verticals JSONB column to users

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-04-08

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'q4r5s6t7u8v9'
down_revision = 'p3q4r5s6t7u8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add allowed_verticals column with default ["real_estate"] for new users
    op.add_column(
        'users',
        sa.Column(
            'allowed_verticals',
            JSONB,
            nullable=False,
            server_default='["real_estate"]'
        )
    )


def downgrade() -> None:
    op.drop_column('users', 'allowed_verticals')
