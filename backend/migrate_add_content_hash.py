#!/usr/bin/env python3
"""Database migration: Add content_hash field to extractions table

This migration adds a 'content_hash' column to the extractions table
to enable duplicate detection and prevent re-processing of identical files.

The content_hash is a SHA256 hash of the file content, allowing the system to:
- Detect when a user uploads the same file multiple times
- Return existing extraction results instead of re-processing
- Save API costs and processing time
- Work alongside the cache system (user-scoped vs global cache)

Usage:
    python migrate_add_content_hash.py
"""
import sys
from sqlalchemy import text, inspect
from app.database import engine
from app.utils.logging import logger


def migrate():
    """Add content_hash column to extractions table if it doesn't exist"""
    print("Checking if content_hash column needs to be added...")

    try:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('extractions')]

        if 'content_hash' in columns:
            print("[OK] Content_hash column already exists. Nothing to do.")
            return

        print("Adding content_hash column to extractions table...")

        # Add the column with index
        with engine.connect() as conn:
            # Add column
            conn.execute(text("""
                ALTER TABLE extractions
                ADD COLUMN content_hash VARCHAR(64) NULL
            """))

            # Create index for faster lookups
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_extractions_content_hash
                ON extractions(content_hash)
            """))

            conn.commit()

        print("[OK] Migration complete! Content_hash column added to extractions table.")
        print("\nDuplicate detection is now enabled:")
        print("  - System calculates SHA256 hash of uploaded file content")
        print("  - Before processing, checks if user already has extraction for this content")
        print("  - If found, returns existing extraction (no re-processing)")
        print("  - Saves API costs and processing time")
        print("  - Works alongside cache system (user-scoped vs global)")

    except Exception as e:
        logger.exception("Migration failed", exc_info=True)
        print(f"\n[ERROR] Migration failed: {e}")
        print("\nIf you're seeing 'duplicate column' errors, the migration may have")
        print("already been applied. Check your database schema.")
        sys.exit(1)


if __name__ == "__main__":
    migrate()
