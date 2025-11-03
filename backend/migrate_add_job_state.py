#!/usr/bin/env python3
"""Database migration: Add JobState table for real-time progress tracking

Run this once to add the job_states table to your database.

Usage:
    python migrate_add_job_state.py
"""
from app.database import engine, Base
from app.db_models import JobState, Extraction  # Import models to register them

def migrate():
    """Create JobState table if it doesn't exist"""
    print("Creating JobState table...")

    # This will create only tables that don't exist yet
    Base.metadata.create_all(bind=engine)

    print("✓ Migration complete! JobState table created.")
    print("\nYou can now use:")
    print("  - POST /api/extract/async - Upload document and get job_id")
    print("  - GET /api/jobs/{job_id}/stream - Real-time progress via SSE")
    print("  - GET /api/jobs/{job_id}/status - Poll for current status")

if __name__ == "__main__":
    migrate()
