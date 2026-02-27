"""upgrade embedding dimension from 384 to 768 for OpenAI text-embedding-3-small

Switches from local sentence-transformer (all-MiniLM-L6-v2, 384d) to
OpenAI text-embedding-3-small with dimensions=768 (Matryoshka reduction).

Existing embeddings become invalid after this migration — a re-embed
task must be run to regenerate all document chunk embeddings.

Revision ID: b1c2d3e4f5a6
Revises: a7fd572ad161
Create Date: 2026-02-24 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "a7fd572ad161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop HNSW index (can't alter vector dimension with index present)
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding")

    # 2. Null out existing embeddings (they're from a different model / vector space)
    op.execute("UPDATE document_chunks SET embedding = NULL")

    # 3. Change column type: Vector(384) → Vector(768)
    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(768)"
    )

    # 4. Recreate HNSW index with cosine distance operator
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding "
        "ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding")

    op.execute("UPDATE document_chunks SET embedding = NULL")

    op.execute(
        "ALTER TABLE document_chunks "
        "ALTER COLUMN embedding TYPE vector(384)"
    )

    op.execute(
        "CREATE INDEX idx_document_chunks_embedding "
        "ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
