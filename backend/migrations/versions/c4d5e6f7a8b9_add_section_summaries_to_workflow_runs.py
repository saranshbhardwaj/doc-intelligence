"""add section_summaries to workflow_runs for map-reduce execution

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2025-12-01

Changes:
- Add section_summaries JSONB column to workflow_runs table
- Stores section-by-section summaries from map-reduce execution
- Schema: {"section_key": {"summary": str, "citations": [], "key_metrics": []}}
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add section_summaries JSONB column to workflow_runs."""
    op.add_column('workflow_runs',
                  sa.Column('section_summaries',
                           postgresql.JSONB(astext_type=sa.Text()),
                           nullable=True))
    print("✅ Added section_summaries column to workflow_runs")


def downgrade() -> None:
    """Remove section_summaries column from workflow_runs."""
    op.drop_column('workflow_runs', 'section_summaries')
    print("✅ Removed section_summaries column from workflow_runs")
