"""add session_documents table

Revision ID: add_session_documents
Revises: 3c8d9e0f1g2h
Create Date: 2025-01-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_session_documents'
down_revision = '3c8d9e0f1g2h'  # After retrieval_spec migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create session_documents junction table.

    Links chat sessions to specific documents, allowing:
    - Sessions with documents from multiple collections
    - Per-session document selection
    - Flexible document management
    """

    # Create session_documents table
    op.create_table(
        'session_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', sa.String(36), sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes for efficient queries
    op.create_index(
        'idx_session_documents_session_id',
        'session_documents',
        ['session_id']
    )

    op.create_index(
        'idx_session_documents_document_id',
        'session_documents',
        ['document_id']
    )

    # Unique constraint: same document can't be added to session twice
    op.create_unique_constraint(
        'uq_session_documents_session_document',
        'session_documents',
        ['session_id', 'document_id']
    )

    # Make collection_id nullable in chat_sessions (sessions are independent of collections)
    op.alter_column(
        'chat_sessions',
        'collection_id',
        existing_type=sa.String(36),
        nullable=True
    )

    # Migrate existing data: populate session_documents from collection relationships
    # For each existing session, link it to all documents in its collection
    op.execute("""
        INSERT INTO session_documents (id, session_id, document_id, added_at)
        SELECT
            gen_random_uuid()::text,
            cs.id,
            cd.document_id,
            cs.created_at
        FROM chat_sessions cs
        INNER JOIN collection_documents cd ON cd.collection_id = cs.collection_id
        WHERE cs.collection_id IS NOT NULL
    """)


def downgrade() -> None:
    """Remove session_documents table and revert changes"""

    # Make collection_id non-nullable again
    op.alter_column(
        'chat_sessions',
        'collection_id',
        existing_type=sa.String(36),
        nullable=False
    )

    # Drop constraints and indexes
    op.drop_constraint('uq_session_documents_session_document', 'session_documents', type_='unique')
    op.drop_index('idx_session_documents_document_id', table_name='session_documents')
    op.drop_index('idx_session_documents_session_id', table_name='session_documents')

    # Drop table
    op.drop_table('session_documents')
