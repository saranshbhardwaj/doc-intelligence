"""Root pytest configuration - test database and settings overrides."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing app modules
# Use PostgreSQL test database (separate from main DB).
# When running inside Docker (via `docker compose exec api`), Postgres is reachable as
# the service name "db". Allow an env override so both local and container runs work.
_db_host = os.environ.get("TEST_DB_HOST", "localhost")
os.environ["DATABASE_URL"] = f"postgresql+psycopg://docint:docint@{_db_host}:5432/docint_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use separate test DB
os.environ["USE_REDIS_CACHE"] = "false"  # Disable Redis for tests
os.environ["ANTHROPIC_API_KEY"] = "test-api-key"

from app.database import Base


def _disable_unsupported_vector_indexes_for_tests() -> None:
    """Drop indexes that are not portable across local pgvector versions.

    Some local Postgres/pgvector combinations do not support creating HNSW
    indexes without explicit operator classes during metadata.create_all().
    These indexes are performance-only and not required for integration tests.
    """
    table = Base.metadata.tables.get("document_chunks")
    if table is None:
        return

    unsupported = {idx for idx in table.indexes if idx.name == "idx_document_chunks_embedding"}
    for idx in unsupported:
        table.indexes.remove(idx)


@pytest.fixture(scope="session")
def test_engine():
    """Create PostgreSQL test engine.

    Note: This assumes PostgreSQL is running and docint_test database exists.
    If the database doesn't exist, run: CREATE DATABASE docint_test;
    """
    test_db_url = f"postgresql+psycopg://docint:docint@{_db_host}:5432/docint_test"
    engine = create_engine(test_db_url, echo=False)

    # Import all models to register them with Base
    import app.db_models
    import app.db_models_users
    import app.db_models_chat
    import app.db_models_workflows
    import app.db_models_documents
    import app.db_models_templates

    _disable_unsupported_vector_indexes_for_tests()

    # Enable pgvector extension (if using vector columns)
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    except Exception:
        pass  # Extension may not be installed, that's OK for tests

    # Create all tables
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: Drop all tables after test session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    """Provide a transactional database session that rolls back after each test.

    This ensures test isolation - each test gets a clean database state.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def override_db_session(db_session, monkeypatch):
    """Override app's SessionLocal to use test database session.

    This allows repository methods to automatically use the test database.
    """
    def mock_session_local():
        return db_session

    monkeypatch.setattr("app.database.SessionLocal", mock_session_local)
    return db_session
