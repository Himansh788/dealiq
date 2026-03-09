import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

# Load .env so DATABASE_URL is available when running alembic commands.
load_dotenv()

# Allow importing from backend root (e.g. `from database.models import Base`)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Wire in our SQLAlchemy models for autogenerate support.
from database.models import Base  # noqa: E402
target_metadata = Base.metadata

# Override the URL from .env — use psycopg2 (sync) for Alembic even if asyncpg is in DATABASE_URL.
def _get_sync_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    # Alembic uses synchronous drivers; swap asyncpg → psycopg2
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("mysql+aiomysql://", "mysql+pymysql://")
    return url


def run_migrations_offline() -> None:
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_sync_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
