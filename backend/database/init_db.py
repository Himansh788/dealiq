import logging

logger = logging.getLogger(__name__)


async def create_tables() -> None:
    """
    Create all database tables defined in models.py.

    - Called from the FastAPI startup event in main.py.
    - Skips silently if DATABASE_URL is not configured so demo mode is unaffected.
    - Uses `checkfirst=True` semantics via create_all — safe to call on every
      startup; existing tables are never dropped or modified.
    """
    from database.connection import async_engine, DATABASE_URL

    if not DATABASE_URL or async_engine is None:
        logger.info("DATABASE_URL not set — skipping table creation (demo mode active)")
        return

    try:
        # Import Base here to avoid circular imports at module load time
        from database.models import Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database tables verified / created successfully")
    except Exception as exc:
        # Log and continue — a DB failure must not crash the API server.
        # Demo mode and all Zoho-backed endpoints remain operational.
        logger.error("Failed to create database tables: %s", exc)
