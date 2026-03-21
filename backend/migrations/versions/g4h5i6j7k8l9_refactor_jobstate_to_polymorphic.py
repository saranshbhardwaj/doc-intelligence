"""Refactor JobState to polymorphic entity_type + entity_id pattern

Removes rigid XOR constraint and 4 nullable FK columns, replacing with a
flexible entity_type + entity_id pattern. This eliminates the need to modify
the schema for each new entity type (analysis_run, investigation_run, etc.).

Revision ID: g4h5i6j7k8l9
Revises: f3a4b5c6d7e8
Create Date: 2026-03-14 00:00:00.000000
"""
import sqlalchemy as sa
from alembic import op

revision = "g4h5i6j7k8l9"
down_revision = "5a6b7c8d9e0f"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add new polymorphic columns
    op.add_column('job_states', sa.Column('entity_type', sa.String(50), nullable=True))
    op.add_column('job_states', sa.Column('entity_id', sa.String(36), nullable=True))

    # 2. Backfill from existing FK columns
    op.execute("""
        UPDATE job_states SET entity_type = 'extraction',        entity_id = extraction_id       WHERE extraction_id IS NOT NULL;
    """)
    op.execute("""
        UPDATE job_states SET entity_type = 'document',          entity_id = document_id         WHERE document_id IS NOT NULL;
    """)
    op.execute("""
        UPDATE job_states SET entity_type = 'workflow_run',      entity_id = workflow_run_id     WHERE workflow_run_id IS NOT NULL;
    """)
    op.execute("""
        UPDATE job_states SET entity_type = 'template_fill_run', entity_id = template_fill_run_id WHERE template_fill_run_id IS NOT NULL;
    """)

    # 3. Make new columns non-nullable
    op.alter_column('job_states', 'entity_type', nullable=False)
    op.alter_column('job_states', 'entity_id', nullable=False)

    # 4. Drop XOR constraint
    op.drop_constraint('job_states_entity_exactly_one_fk_check', 'job_states', type_='check')

    # 5. Drop old FK indexes
    op.drop_index('idx_job_states_extraction_id', table_name='job_states')
    op.drop_index('idx_job_states_document_id', table_name='job_states')
    op.drop_index('idx_job_states_workflow_run_id', table_name='job_states')
    op.drop_index('idx_job_states_template_fill_run_id', table_name='job_states')

    # 6. Drop FK columns
    op.drop_column('job_states', 'extraction_id')
    op.drop_column('job_states', 'document_id')
    op.drop_column('job_states', 'workflow_run_id')
    op.drop_column('job_states', 'template_fill_run_id')

    # 7. Drop unused stage flag columns
    op.drop_column('job_states', 'summarizing_completed')
    op.drop_column('job_states', 'extracting_completed')
    op.drop_column('job_states', 'validation_completed')

    # 8. Add compound index on entity_type + entity_id
    op.create_index('idx_job_states_entity', 'job_states', ['entity_type', 'entity_id'])


def downgrade():
    # 1. Drop compound index
    op.drop_index('idx_job_states_entity', table_name='job_states')

    # 2. Re-add unused stage flags
    op.add_column('job_states', sa.Column('summarizing_completed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('job_states', sa.Column('extracting_completed', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('job_states', sa.Column('validation_completed', sa.Boolean(), nullable=False, server_default=sa.false()))

    # 3. Re-add FK columns
    op.add_column('job_states', sa.Column('extraction_id', sa.String(36), nullable=True))
    op.add_column('job_states', sa.Column('document_id', sa.String(36), nullable=True))
    op.add_column('job_states', sa.Column('workflow_run_id', sa.String(36), nullable=True))
    op.add_column('job_states', sa.Column('template_fill_run_id', sa.String(36), nullable=True))

    # 4. Backfill FK columns from polymorphic data
    op.execute("""
        UPDATE job_states SET extraction_id = entity_id WHERE entity_type = 'extraction';
    """)
    op.execute("""
        UPDATE job_states SET document_id = entity_id WHERE entity_type = 'document';
    """)
    op.execute("""
        UPDATE job_states SET workflow_run_id = entity_id WHERE entity_type = 'workflow_run';
    """)
    op.execute("""
        UPDATE job_states SET template_fill_run_id = entity_id WHERE entity_type = 'template_fill_run';
    """)

    # 5. Re-add FK constraints
    op.create_foreign_key(None, 'job_states', 'extractions', ['extraction_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'job_states', 'documents', ['document_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'job_states', 'workflow_runs', ['workflow_run_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key(None, 'job_states', 'template_fill_runs', ['template_fill_run_id'], ['id'], ondelete='CASCADE')

    # 6. Re-add XOR constraint
    op.create_check_constraint(
        'job_states_entity_exactly_one_fk_check',
        'job_states',
        '((extraction_id IS NOT NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NOT NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NOT NULL AND template_fill_run_id IS NULL) OR '
        '(extraction_id IS NULL AND document_id IS NULL AND workflow_run_id IS NULL AND template_fill_run_id IS NOT NULL))'
    )

    # 7. Re-add FK indexes
    op.create_index('idx_job_states_extraction_id', 'job_states', ['extraction_id'])
    op.create_index('idx_job_states_document_id', 'job_states', ['document_id'])
    op.create_index('idx_job_states_workflow_run_id', 'job_states', ['workflow_run_id'])
    op.create_index('idx_job_states_template_fill_run_id', 'job_states', ['template_fill_run_id'])

    # 8. Drop polymorphic columns
    op.drop_column('job_states', 'entity_type')
    op.drop_column('job_states', 'entity_id')
