#!/usr/bin/env python3
"""Database migration: Add context field to extractions table

This migration adds an optional 'context' column to the extractions table
to store user-provided guidance for the extraction process.

Usage:
    python migrate_add_context_field.py
"""
import sys
from sqlalchemy import text, inspect
from app.database import engine
from app.utils.logging import logger


def migrate():
    """Add context column to extractions table if it doesn't exist"""
    print("Checking if context column needs to be added...")

    try:
        # Check if column already exists
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('extractions')]

        if 'context' in columns:
            print("✓ Context column already exists. Nothing to do.")
            return

        print("Adding context column to extractions table...")

        # Add the column
        with engine.connect() as conn:
            # SQLite and PostgreSQL both support this syntax
            conn.execute(text("""
                ALTER TABLE extractions
                ADD COLUMN context TEXT NULL
            """))
            conn.commit()

        print("✓ Migration complete! Context column added to extractions table.")
        print("\nUsers can now provide optional context when uploading documents:")
        print("  - Frontend: Context input appears after file selection")
        print("  - Backend: Context is passed to LLM to guide extraction focus")
        print("  - Max length: 500 characters")

    except Exception as e:
        logger.exception("Migration failed")
        print(f"\n❌ Migration failed: {e}")
        print("\nIf you're seeing 'duplicate column' errors, the migration may have")
        print("already been applied. Check your database schema.")
        sys.exit(1)


if __name__ == "__main__":
    migrate()
