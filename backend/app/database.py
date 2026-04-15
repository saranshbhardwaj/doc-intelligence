# backend/app/database.py
"""Database configuration and session management"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.utils.logging import logger
from app.config import settings


def _build_database_urls(raw_url: str) -> tuple[str, str]:
    """
    Derive sync (psycopg3) and async (asyncpg) SQLAlchemy URLs from any
    common DATABASE_URL format:

        postgres://...              Railway / Heroku style
        postgresql://...            Standard, no driver specified
        postgresql+psycopg://...    Already psycopg3 (docker-compose)
        sqlite:///...               Local development
    """
    url = raw_url

    # Normalize legacy "postgres://" prefix used by Railway / Heroku
    if url.startswith("postgres://"):
        url = "postgresql" + url[len("postgres"):]

    # SQLite — no driver swapping needed
    if url.startswith("sqlite"):
        return url, url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    # Strip any existing driver prefix so we have a clean "postgresql://..." base
    if "://" in url:
        base = "postgresql://" + url.split("://", 1)[1]
    else:
        base = url

    sync_url  = base.replace("postgresql://", "postgresql+psycopg://",  1)
    async_url = base.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Append prepare_threshold=0 to the sync URL query string so psycopg3
    # disables prepared statements even when connect_args is ignored (e.g. when
    # the URL is passed through an external pool or middleware on Railway).
    separator = "&" if "?" in sync_url else "?"
    if "prepare_threshold" not in sync_url:
        sync_url = f"{sync_url}{separator}prepare_threshold=0"

    return sync_url, async_url


# Get database URL from settings (which loads from .env)
# Fallback to os.environ directly — pydantic-settings may miss env vars
# when the env_file path doesn't exist (e.g. in Railway containers).
DATABASE_URL = (
    settings.database_url
    or settings.supabase_database_url
    or os.environ.get("DATABASE_URL", "")
    or os.environ.get("SUPABASE_DATABASE_URL", "")
)

if not DATABASE_URL:
    # Log available env hints to help diagnose Railway variable injection
    _has_db = "DATABASE_URL" in os.environ
    logger.error(
        "DATABASE_URL is not set",
        extra={"in_os_environ": _has_db, "settings_value": repr(settings.database_url)},
    )
    raise RuntimeError("DATABASE_URL is not set. Define it in .env or docker-compose environment.")

SYNC_DATABASE_URL, ASYNC_DATABASE_URL = _build_database_urls(DATABASE_URL)
backend_kind = "sqlite" if DATABASE_URL.startswith("sqlite") else "postgres"
logger.info("Database configuration loaded", extra={"backend": backend_kind})

# Create engine with connection pooling
# For SQLite, we need check_same_thread=False
connect_args = {}
pool_config = {}

if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # prepare_threshold=0: disable server-side prepared statements.
    # Required for Supabase PgBouncer (transaction mode, port 6543) — PgBouncer
    # does not support prepared statements across pooled connections. Without this,
    # concurrent workers collide on statement names (DuplicatePreparedStatement).
    # See: https://www.psycopg.org/psycopg3/docs/advanced/prepare.html
    connect_args = {"prepare_threshold": 0}
    # PostgreSQL connection pool configuration for production scalability
    pool_config = {
        "pool_size": 20,           # Base connections per container
        "max_overflow": 10,        # Allow 10 overflow (total 30 max)
        "pool_pre_ping": True,     # Validate connections before reuse (prevents stale connections)
        "pool_recycle": 3600,      # Recycle connections after 1 hour
        "pool_timeout": 30,        # Wait 30s for connection before error
    }

engine = create_engine(SYNC_DATABASE_URL, connect_args=connect_args, **pool_config)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine with connection pooling (same config as sync engine)
async_pool_config = {}
if not DATABASE_URL.startswith("sqlite"):
    async_pool_config = {
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "pool_timeout": 30,
    }

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False, **async_pool_config)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency to get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_session():
    """Async generator to get async database session"""
    async with AsyncSessionLocal() as session:
        yield session


def init_db():
    """Initialize database - create all tables"""
    logger.info("Initializing database...")

    # Enable pgvector extension (PostgreSQL only)
    if not DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.commit()
                logger.info("pgvector extension enabled")
        except Exception as e:
            logger.warning(f"Could not enable pgvector extension: {e}")

    # Import all models to register them with Base (imports needed for side effects)
    import app.db_models  # noqa: F401 - Extraction, ParserOutput, CacheEntry, JobState
    import app.db_models_users  # noqa: F401 - User
    import app.db_models_chat  # noqa: F401 - Collection, CollectionDocument, DocumentChunk, ChatSession, ChatMessage
    import app.db_models_workflows  # noqa: F401 - Workflow, WorkflowRun
    import app.db_models_documents  # noqa: F401 - Document (canonical)
    import app.db_models_templates  # noqa: F401 - ExcelTemplate, TemplateFillRun
    import app.db_models_pe_diligence  # noqa: F401 - PE diligence domain models

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")
