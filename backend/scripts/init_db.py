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

from app.utils.logging import logger
import subprocess


def main():
    """Initialize database - create all tables"""
    try:
        logger.info("=" * 60)
        logger.info("Initializing Sand Cloud database...")
        logger.info("=" * 60)

        # Apply latest Alembic migrations instead of raw create_all
        result = subprocess.run(["alembic", "upgrade", "head"], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Alembic upgrade failed", extra={"stderr": result.stderr})
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)

        logger.info("Alembic migrations applied successfully")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"\nDatabase initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
