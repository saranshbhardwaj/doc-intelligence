"""Fix job_states check constraint to include template_fill_run_id

The check constraint "job_states_entity_exactly_one_fk_check" was created
before template_fill_run_id was added to the job_states table. It only
enforces 3 conditions (extraction_id, document_id, workflow_run_id), so
inserting a row with only template_fill_run_id set fails.

This migration drops the old constraint and recreates it with the correct
4 conditions.

Revision ID: d1e2f3a4b5c6
Revises: c4d5e6f7a8b9
Create Date: 2026-02-27 00:00:00.000000
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


_CONSTRAINT_NAME = "job_states_entity_exactly_one_fk_check"

_NEW_CONSTRAINT = (
    "(extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR "
    "(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR "
    "(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL AND template_fill_run_id IS NULL) OR "
    "(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NOT NULL)"
)

# The old 3-condition constraint (without template_fill_run_id) for downgrade
_OLD_CONSTRAINT = (
    "(extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL) OR "
    "(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL) OR "
    "(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL)"
)


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "job_states", type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, "job_states", _NEW_CONSTRAINT)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, "job_states", type_="check")
    op.create_check_constraint(_CONSTRAINT_NAME, "job_states", _OLD_CONSTRAINT)
