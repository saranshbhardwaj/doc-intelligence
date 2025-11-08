# backend/app/database.py
"""Database configuration and session management"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.utils.logging import logger
from app.config import settings

# Get database URL from settings (which loads from .env)
DATABASE_URL = settings.database_url

if not DATABASE_URL:
    # Fail fast – explicit URL required now that we use Postgres in containers
    raise RuntimeError("DATABASE_URL is not set. Define it in .env or docker-compose environment.")
else:
    backend_kind = "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres"
    logger.info("Database configuration loaded", extra={"backend": backend_kind})

# Create engine
# For SQLite, we need check_same_thread=False
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database - create all tables"""
    logger.info("Initializing database...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")
