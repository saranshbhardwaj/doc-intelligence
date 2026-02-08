# backend/app/database.py
"""Database configuration and session management"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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

# Create async engine and session factory for async operations
# Convert sync DATABASE_URL to async (postgresql -> postgresql+asyncpg, sqlite -> sqlite+aiosqlite)
if DATABASE_URL.startswith("postgresql"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
elif DATABASE_URL.startswith("sqlite"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    ASYNC_DATABASE_URL = DATABASE_URL

async_engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
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

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized successfully")
