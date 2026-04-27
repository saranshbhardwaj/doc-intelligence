# backend/app/database.py
"""Database configuration and session management"""
import os
from sqlalchemy import create_engine, event, text
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
    # PostgreSQL connection pool configuration.
    # PgBouncer (port 6543, transaction mode) handles physical connection multiplexing,
    # so SQLAlchemy's pool only needs to hold a small number of client-side slots per
    # container. Large pool_size values waste resources since PgBouncer serialises the
    # actual Postgres connections anyway.
    # 5 containers × (5 + 5) = ~50 client slots → PgBouncer maps these to ~10-20 real connections.
    pool_config = {
        "pool_size": 5,            # Small — PgBouncer does the real pooling
        "max_overflow": 5,         # Total 10 per container
        "pool_pre_ping": True,     # Validate connections before reuse
        "pool_recycle": 1800,      # 30 min — transaction mode connections are cheap to recreate
        "pool_timeout": 30,        # Wait 30s for a slot before error
    }

engine = create_engine(SYNC_DATABASE_URL, connect_args=connect_args, **pool_config)

# Disable psycopg3 server-side prepared statements on every new physical connection.
# connect_args alone is insufficient — SQLAlchemy's dialect.initialize() runs
# `select current_schema()` before connect_args settings are applied, which collides
# on PgBouncer (transaction mode, port 6543). Setting the attribute directly on the
# raw dbapi connection is the only reliable way to disable prepare for ALL queries.
if not DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def disable_prepared_statements(dbapi_connection, connection_record):
        dbapi_connection.prepare_threshold = None

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Async engine with connection pooling (same config as sync engine)
async_pool_config = {}
if not DATABASE_URL.startswith("sqlite"):
    async_pool_config = {
        "pool_size": 5,
        "max_overflow": 5,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
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
