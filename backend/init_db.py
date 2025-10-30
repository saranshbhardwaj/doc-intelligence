# backend/init_db.py
"""Database initialization script

Run this to create all tables in your database.

Usage:
    python init_db.py
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.database import init_db, engine
from app.db_models import *  # Import all models
from app.utils.logging import logger


def main():
    """Initialize database - create all tables"""
    try:
        logger.info("=" * 60)
        logger.info("Initializing Sand Cloud database...")
        logger.info("=" * 60)

        # Create all tables
        init_db()

        # Show created tables
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        logger.info(f"\nCreated {len(tables)} tables:")
        for table in tables:
            logger.info(f"  ✓ {table}")

        logger.info("\n" + "=" * 60)
        logger.info("Database initialization completed successfully!")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\nDatabase initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
