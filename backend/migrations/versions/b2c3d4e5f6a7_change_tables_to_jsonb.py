"""change_tables_to_jsonb

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-11-26

Changes:
- Change document_chunks.tables from Text to JSONB
- Change document_chunks.narrative_text from Text to Text (no change, just confirmation)

Why JSONB:
- Stores structured table metadata (row_count, column_count, etc.)
- Allows future querying: WHERE tables->0->>'row_count' > 10
- Matches chunk_metadata pattern (also JSONB)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Change tables column from Text to JSONB.

    Idempotent: checks if column is already JSONB before altering.
    """
    conn = op.get_bind()
    inspector = inspect(conn)

    # Get current column type
    columns = {col['name']: col for col in inspector.get_columns('document_chunks')}

    if 'tables' in columns:
        current_type = str(columns['tables']['type'])

        # Only alter if not already JSONB
        if 'JSONB' not in current_type and 'JSON' not in current_type:
            print(f"Migrating 'tables' column from {current_type} to JSONB...")

            # Convert existing Text data to JSONB
            # If column has string data like "[{...}]", this will fail - but we haven't deployed yet
            # If column is NULL or empty, this is safe
            op.execute("""
                ALTER TABLE document_chunks
                ALTER COLUMN tables TYPE JSONB
                USING CASE
                    WHEN tables IS NULL THEN NULL
                    WHEN tables = '' THEN NULL
                    ELSE tables::jsonb
                END
            """)
            print("✅ 'tables' column migrated to JSONB")
        else:
            print(f"✅ 'tables' column is already JSONB (type: {current_type}), skipping")
    else:
        print("⚠️  'tables' column not found in document_chunks table")


def downgrade() -> None:
    """
    Revert tables column from JSONB back to Text.
    """
    conn = op.get_bind()
    inspector = inspect(conn)

    columns = {col['name']: col for col in inspector.get_columns('document_chunks')}

    if 'tables' in columns:
        current_type = str(columns['tables']['type'])

        # Only alter if currently JSONB
        if 'JSONB' in current_type or 'JSON' in current_type:
            print(f"Reverting 'tables' column from {current_type} to Text...")

            # Convert JSONB back to Text (as JSON string)
            op.execute("""
                ALTER TABLE document_chunks
                ALTER COLUMN tables TYPE TEXT
                USING CASE
                    WHEN tables IS NULL THEN NULL
                    ELSE tables::text
                END
            """)
            print("✅ 'tables' column reverted to Text")
        else:
            print(f"✅ 'tables' column is already Text (type: {current_type}), skipping")
    else:
        print("⚠️  'tables' column not found in document_chunks table")
