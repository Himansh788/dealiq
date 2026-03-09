import os
import logging

logger = logging.getLogger(__name__)

# New columns added to existing tables.
# Each tuple: (table_name, column_name, mysql_definition, postgres_definition)
# postgres_definition can be None if same as mysql_definition.
_COLUMN_MIGRATIONS = [
    # deals — cache fields
    ("deals", "synced_at",          "DATETIME NULL",                    "TIMESTAMPTZ NULL"),
    ("deals", "raw_data",           "JSON NULL",                        "JSONB NULL"),
    ("deals", "closing_date",       "VARCHAR(20) NULL",                 None),
    ("deals", "last_activity_time", "VARCHAR(50) NULL",                 None),
    ("deals", "next_step",          "TEXT NULL",                        None),
    ("deals", "health_score",       "INT NULL",                         None),
    ("deals", "health_label",       "VARCHAR(20) NULL",                 None),
    ("deals", "sync_source",        "VARCHAR(50) NULL DEFAULT 'zoho'",  "VARCHAR(50) NULL DEFAULT 'zoho'"),
    # deals — JSONB / flexible metadata columns
    ("deals", "health_signals",     "JSON NULL",                        "JSONB NULL DEFAULT '{}'"),
    ("deals", "ai_analysis",        "JSON NULL",                        "JSONB NULL DEFAULT '{}'"),
    ("deals", "deal_metadata",      "JSON NULL",                        "JSONB NULL DEFAULT '{}'"),
    ("deals", "activity_summary",   "JSON NULL",                        "JSONB NULL DEFAULT '{}'"),
    # health_scores — versioning
    ("health_scores", "score_version", "INT NULL DEFAULT 1",            None),
    # emails — freshness tracking
    ("emails", "synced_at",         "DATETIME NULL",                    "TIMESTAMPTZ NULL"),
    ("emails", "zoho_email_id",     "VARCHAR(100) NULL",                None),
    # email_analyses — model versioning
    ("email_analyses", "model_version", "VARCHAR(50) NULL DEFAULT 'claude-haiku'", None),
]


async def _apply_column_migrations_mysql(conn) -> None:
    """Add missing columns to existing tables using MySQL INFORMATION_SCHEMA."""
    from sqlalchemy import text
    for table, column, mysql_def, _pg_def in _COLUMN_MIGRATIONS:
        result = await conn.execute(text("""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = :table
              AND COLUMN_NAME  = :column
        """), {"table": table, "column": column})
        exists = result.scalar()
        if not exists:
            await conn.execute(text(
                f"ALTER TABLE `{table}` ADD COLUMN `{column}` {mysql_def}"
            ))
            logger.info("Migration applied: %s.%s added", table, column)


async def _apply_column_migrations_postgres(conn) -> None:
    """Add missing columns using PostgreSQL information_schema. Uses IF NOT EXISTS (PG 9.6+)."""
    from sqlalchemy import text
    for table, column, mysql_def, pg_def in _COLUMN_MIGRATIONS:
        col_def = pg_def if pg_def is not None else mysql_def
        # PostgreSQL supports ADD COLUMN IF NOT EXISTS natively (9.6+)
        await conn.execute(text(
            f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{column}" {col_def}'
        ))
    logger.info("PostgreSQL column migrations applied (IF NOT EXISTS — idempotent)")


async def create_tables() -> None:
    """
    Create all database tables defined in models.py, then apply column migrations.

    - Called from the FastAPI startup event in main.py.
    - Skips silently if DATABASE_URL is not configured so demo mode is unaffected.
    - create_all is idempotent (never drops existing tables).
    - Column migrations add any new columns to existing tables.

    Supports both MySQL (aiomysql) and PostgreSQL (asyncpg).
    Set USE_ALEMBIC=true in .env to skip auto-migration (use Alembic instead).
    """
    from database.connection import async_engine, DATABASE_URL, IS_POSTGRES

    if not DATABASE_URL or async_engine is None:
        logger.info("DATABASE_URL not set — skipping table creation (demo mode active)")
        return

    use_alembic = os.getenv("USE_ALEMBIC", "false").lower() == "true"

    try:
        from database.models import Base

        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

            if not use_alembic:
                if IS_POSTGRES:
                    await _apply_column_migrations_postgres(conn)
                else:
                    await _apply_column_migrations_mysql(conn)
            else:
                logger.info("USE_ALEMBIC=true — skipping auto column migrations")

        db_type = "PostgreSQL" if IS_POSTGRES else "MySQL"
        logger.info("%s tables verified / created / migrated successfully", db_type)
    except Exception as exc:
        logger.error("Failed to initialise database: %s", exc)
