import logging

logger = logging.getLogger(__name__)

# New columns added to existing tables.
# Each tuple: (table_name, column_name, MySQL column definition)
# Using INFORMATION_SCHEMA check instead of ALTER TABLE IF NOT EXISTS for MySQL 5.7 compat.
_COLUMN_MIGRATIONS = [
    # deals — cache fields
    ("deals", "synced_at",          "DATETIME NULL"),
    ("deals", "raw_data",           "JSON NULL"),
    ("deals", "closing_date",       "VARCHAR(20) NULL"),
    ("deals", "last_activity_time", "VARCHAR(50) NULL"),
    ("deals", "next_step",          "TEXT NULL"),
    ("deals", "health_score",       "INT NULL"),
    ("deals", "health_label",       "VARCHAR(20) NULL"),
    ("deals", "sync_source",        "VARCHAR(50) NULL DEFAULT 'zoho'"),
    # health_scores — versioning
    ("health_scores", "score_version", "INT NULL DEFAULT 1"),
    # emails — freshness tracking
    ("emails", "synced_at",    "DATETIME NULL"),
    ("emails", "zoho_email_id", "VARCHAR(100) NULL"),
    # email_analyses — model versioning
    ("email_analyses", "model_version", "VARCHAR(50) NULL DEFAULT 'claude-haiku'"),
]


async def _apply_column_migrations(conn) -> None:
    """Add any missing columns to existing tables without touching existing data."""
    from sqlalchemy import text
    for table, column, definition in _COLUMN_MIGRATIONS:
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = :table
              AND COLUMN_NAME  = :column
        """), {"table": table, "column": column})
        exists = result.scalar()
        if not exists:
            await conn.execute(text(
                f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}"
            ))
            logger.info("Migration applied: %s.%s added", table, column)


async def create_tables() -> None:
    """
    Create all database tables defined in models.py, then apply column migrations.

    - Called from the FastAPI startup event in main.py.
    - Skips silently if DATABASE_URL is not configured so demo mode is unaffected.
    - create_all is idempotent (never drops existing tables).
    - _apply_column_migrations adds any new columns to existing tables.
    """
    from database.connection import async_engine, DATABASE_URL

    if not DATABASE_URL or async_engine is None:
        logger.info("DATABASE_URL not set — skipping table creation (demo mode active)")
        return

    try:
        from database.models import Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await _apply_column_migrations(conn)

        logger.info("Database tables verified / created / migrated successfully")
    except Exception as exc:
        logger.error("Failed to initialise database: %s", exc)
