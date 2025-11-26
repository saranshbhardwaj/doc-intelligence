"""merge session_documents and workflow_defensive_fields

Revision ID: 391dff3481ad
Revises: ('add_session_documents', '4d9e0f1g2h3i')
Create Date: 2025-11-25 23:11:39.545381

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '391dff3481ad'
down_revision = ('add_session_documents', '4d9e0f1g2h3i')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass