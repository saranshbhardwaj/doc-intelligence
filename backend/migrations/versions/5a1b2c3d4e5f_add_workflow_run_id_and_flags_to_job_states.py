"""add workflow_run_id and workflow stage flags to job_states

Revision ID: 5a1b2c3d4e5f
Revises: e26f80b0d932
Create Date: 2025-11-12 22:45:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5a1b2c3d4e5f'
down_revision = '9f7c1a2b3c4d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add workflow_run_id column + index + FK
    op.add_column('job_states', sa.Column('workflow_run_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_job_states_workflow_run_id'), 'job_states', ['workflow_run_id'], unique=False)
    op.create_foreign_key(None, 'job_states', 'workflow_runs', ['workflow_run_id'], ['id'], ondelete='CASCADE')

    # Add workflow-specific stage completion flags
    op.add_column('job_states', sa.Column('context_completed', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.add_column('job_states', sa.Column('artifact_completed', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.add_column('job_states', sa.Column('validation_completed', sa.Boolean(), nullable=True, server_default=sa.text('false')))

    # Drop old XOR constraint and add new exactly-one constraint
    try:
        op.drop_constraint('job_states_entity_xor_check', 'job_states', type_='check')
    except Exception:
        # Constraint may already be absent if prior migration adjusted
        pass

    op.create_check_constraint(
        'job_states_entity_exactly_one_fk_check',
        'job_states',
        '((extraction_id IS NOT NULL AND collection_document_id IS NULL AND workflow_run_id IS NULL) OR '
        '(extraction_id IS NULL AND collection_document_id IS NOT NULL AND workflow_run_id IS NULL) OR '
        '(extraction_id IS NULL AND collection_document_id IS NULL AND workflow_run_id IS NOT NULL))'
    )


def downgrade() -> None:
    # Drop new constraint
    op.drop_constraint('job_states_entity_exactly_one_fk_check', 'job_states', type_='check')

    # Remove workflow-specific columns
    op.drop_column('job_states', 'validation_completed')
    op.drop_column('job_states', 'artifact_completed')
    op.drop_column('job_states', 'context_completed')

    # Remove workflow_run_id FK + index + column
    op.drop_constraint(None, 'job_states', type_='foreignkey')
    op.drop_index(op.f('ix_job_states_workflow_run_id'), table_name='job_states')
    op.drop_column('job_states', 'workflow_run_id')

    # Restore old XOR constraint (extraction vs collection_document)
    op.create_check_constraint(
        'job_states_entity_xor_check',
        'job_states',
        '(extraction_id IS NOT NULL AND collection_document_id IS NULL) OR '
        '(extraction_id IS NULL AND collection_document_id IS NOT NULL)'
    )
