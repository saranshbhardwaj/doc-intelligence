"""add missing columns to document_chunks and chat_messages

Revision ID: d0f0d19b3702
Revises: 5c2338910b3d
Create Date: 2026-02-23 01:50:33.564870

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0f0d19b3702'
down_revision = '5c2338910b3d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # ---------- document_chunks ----------
    cols_dc = {c['name'] for c in inspector.get_columns('document_chunks')}

    if 'text' not in cols_dc:
        op.add_column('document_chunks', sa.Column('text', sa.Text(), nullable=True))

    if 'page_number' not in cols_dc:
        op.add_column('document_chunks', sa.Column('page_number', sa.Integer(), nullable=True))

    if 'section_type' not in cols_dc:
        op.add_column('document_chunks', sa.Column('section_type', sa.String(50), nullable=True))

    if 'section_heading' not in cols_dc:
        op.add_column('document_chunks', sa.Column('section_heading', sa.Text(), nullable=True))

    if 'is_tabular' not in cols_dc:
        op.add_column('document_chunks', sa.Column('is_tabular', sa.Boolean(), nullable=True))


    # ---------- chat_messages ----------
    cols_cm = {c['name'] for c in inspector.get_columns('chat_messages')}

    if 'message_index' not in cols_cm:
        op.add_column('chat_messages', sa.Column('message_index', sa.Integer(), nullable=True))

    if 'source_chunks' not in cols_cm:
        op.add_column('chat_messages', sa.Column('source_chunks', sa.Text(), nullable=True))

    if 'retrieval_query' not in cols_cm:
        op.add_column('chat_messages', sa.Column('retrieval_query', sa.Text(), nullable=True))

    if 'num_chunks_retrieved' not in cols_cm:
        op.add_column('chat_messages', sa.Column('num_chunks_retrieved', sa.Integer(), nullable=True))

    if 'model_used' not in cols_cm:
        op.add_column('chat_messages', sa.Column('model_used', sa.String(100), nullable=True))

    if 'tokens_used' not in cols_cm:
        op.add_column('chat_messages', sa.Column('tokens_used', sa.Integer(), nullable=True))

    if 'cost_usd' not in cols_cm:
        op.add_column('chat_messages', sa.Column('cost_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    cols_cm = {c['name'] for c in inspector.get_columns('chat_messages')}
    if 'cost_usd' in cols_cm:
        op.drop_column('chat_messages', 'cost_usd')
    if 'tokens_used' in cols_cm:
        op.drop_column('chat_messages', 'tokens_used')
    if 'model_used' in cols_cm:
        op.drop_column('chat_messages', 'model_used')
    if 'num_chunks_retrieved' in cols_cm:
        op.drop_column('chat_messages', 'num_chunks_retrieved')
    if 'retrieval_query' in cols_cm:
        op.drop_column('chat_messages', 'retrieval_query')
    if 'source_chunks' in cols_cm:
        op.drop_column('chat_messages', 'source_chunks')
    if 'message_index' in cols_cm:
        op.drop_column('chat_messages', 'message_index')

    cols_dc = {c['name'] for c in inspector.get_columns('document_chunks')}
    if 'is_tabular' in cols_dc:
        op.drop_column('document_chunks', 'is_tabular')
    if 'section_heading' in cols_dc:
        op.drop_column('document_chunks', 'section_heading')
    if 'section_type' in cols_dc:
        op.drop_column('document_chunks', 'section_type')
    if 'page_number' in cols_dc:
        op.drop_column('document_chunks', 'page_number')
    if 'text' in cols_dc:
        op.drop_column('document_chunks', 'text')