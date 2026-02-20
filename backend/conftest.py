"""Root pytest configuration - test database and settings overrides."""
import os
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Set test environment variables before importing app modules
# Use PostgreSQL test database (separate from main DB)
os.environ["DATABASE_URL"] = "postgresql+psycopg://docint:docint@localhost:5432/docint_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use separate test DB
os.environ["USE_REDIS_CACHE"] = "false"  # Disable Redis for tests
os.environ["ANTHROPIC_API_KEY"] = "test-api-key"

from app.database import Base


@pytest.fixture(scope="session")
def test_engine():
    """Create PostgreSQL test engine.

    Note: This assumes PostgreSQL is running and docint_test database exists.
    If the database doesn't exist, run: CREATE DATABASE docint_test;
    """
    test_db_url = "postgresql+psycopg://docint:docint@localhost:5432/docint_test"
    engine = create_engine(test_db_url, echo=False)

    # Import all models to register them with Base
    import app.db_models
    import app.db_models_users
    import app.db_models_chat
    import app.db_models_workflows
    import app.db_models_documents
    import app.db_models_templates

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
