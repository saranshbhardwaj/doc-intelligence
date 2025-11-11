from __future__ import annotations
import os
import sys
from pathlib import Path
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Ensure project root (where 'app' package lives) is on sys.path.
# Works whether running in container (/app) or locally (backend/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import settings and metadata AFTER path injection
try:
    from app.config import settings  # type: ignore
    from app.database import Base  # type: ignore
    # Import models to ensure they are registered with Base.metadata
    import app.db_models  # noqa: F401
    import app.db_models_users  # noqa: F401
    import app.db_models_chat  # noqa: F401
except ModuleNotFoundError:
    # Fallback: explicitly add container root and current working directory
    ROOT_CANDIDATES = [Path('/app'), Path.cwd()]
    for cand in ROOT_CANDIDATES:
        if cand.exists() and str(cand) not in sys.path:
            sys.path.insert(0, str(cand))
    from app.config import settings  # type: ignore
    from app.database import Base  # type: ignore
    import app.db_models  # noqa: F401
    import app.db_models_users  # noqa: F401
    import app.db_models_chat  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from environment (.env loaded by settings)
database_url = settings.database_url
if not database_url:
    raise RuntimeError("DATABASE_URL not set; cannot run migrations")
config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

target_metadata = Base.metadata

def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Render concurrent operations (CREATE INDEX CONCURRENTLY) as-is
            # These operations must run outside transaction blocks
            render_as_batch=False,
        )

        # Check if we need to run without transaction for CONCURRENTLY operations
        # Set CONCURRENTLY mode by setting isolation_level to AUTOCOMMIT
        connection.execution_options(isolation_level="AUTOCOMMIT")
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
