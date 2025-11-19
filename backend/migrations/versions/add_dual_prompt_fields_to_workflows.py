"""add_dual_prompt_fields_to_workflows

Revision ID: f8a9b0c1d2e3
Revises: clean_schema_2025_11_16
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a9b0c1d2e3'
down_revision = 'clean_schema_2025_11_16'
branch_labels = None
depends_on = None


def upgrade():
    # Add user_prompt_template column to workflows table
    op.add_column('workflows', sa.Column('user_prompt_template', sa.Text(), nullable=True))

    # Add user_prompt_max_length column to workflows table
    op.add_column('workflows', sa.Column('user_prompt_max_length', sa.Integer(), nullable=True))


def downgrade():
    # Remove user_prompt_max_length column
    op.drop_column('workflows', 'user_prompt_max_length')

    # Remove user_prompt_template column
    op.drop_column('workflows', 'user_prompt_template')
