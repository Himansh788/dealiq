import os
import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")

# Normalise driver tokens for async engine compatibility.
# MySQL: pymysql (sync-only) → aiomysql (async)
# PostgreSQL: psycopg2 (sync-only) → asyncpg (async)
if DATABASE_URL and "mysql+pymysql://" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("mysql+pymysql://", "mysql+aiomysql://")
    logger.debug("Normalised DATABASE_URL driver: pymysql -> aiomysql")
elif DATABASE_URL and "postgresql+psycopg2://" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    logger.debug("Normalised DATABASE_URL driver: psycopg2 -> asyncpg")
elif DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    # Heroku-style shorthand
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    logger.debug("Normalised DATABASE_URL driver: postgres:// -> postgresql+asyncpg://")

# Detect which database engine is in use for dialect-specific code paths.
IS_POSTGRES = DATABASE_URL is not None and (
    "postgresql" in DATABASE_URL or "asyncpg" in DATABASE_URL
)
IS_MYSQL = DATABASE_URL is not None and "mysql" in DATABASE_URL

# ---------------------------------------------------------------------------
# Engine + session factory — only created when DATABASE_URL is present.
# If DATABASE_URL is not set, all DB helpers return None/False gracefully
# so the demo flow continues to work without any database.
# ---------------------------------------------------------------------------

async_engine = None
AsyncSessionLocal = None

if DATABASE_URL:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

        async_engine = create_async_engine(
            DATABASE_URL,
            echo=False,           # flip to True for SQL query logging during dev
            pool_pre_ping=True,   # detect stale connections before use
            pool_recycle=3600,    # recycle connections every hour (important for MySQL)
            pool_size=10,
            max_overflow=20,
        )

        AsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

        db_type = "PostgreSQL" if IS_POSTGRES else "MySQL"
        logger.info("%s async engine created — pool_size=10, max_overflow=20", db_type)
    except Exception as exc:
        logger.warning("Failed to create DB engine: %s — running without database", exc)
        async_engine = None
        AsyncSessionLocal = None
else:
    logger.info("DATABASE_URL not set — running in DB-less / demo mode")


async def get_db() -> AsyncGenerator:
    """
    FastAPI dependency.  Yields an AsyncSession when DATABASE_URL is configured.
    Yields None if no database is configured so callers can guard with `if db:`.
    """
    if AsyncSessionLocal is None:
        yield None
        return

    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_health() -> bool:
    """
    Returns True if a live DB connection can be obtained, False otherwise.
    Safe to call even when DATABASE_URL is not set.
    """
    if async_engine is None:
        return False

    try:
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("DB health check failed: %s", exc)
        return False
