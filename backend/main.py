from dotenv import load_dotenv
load_dotenv(override=True)  # override=True ensures .env wins over any OS-level env vars

import logging
import os

# Ensure our application loggers emit INFO+ even when uvicorn defaults to WARNING.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
# Keep noisy third-party loggers at WARNING to avoid log spam.
for _noisy in ("httpx", "httpcore", "hpack", "urllib3", "botocore", "boto3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, deals, analysis, ai_rep, forecast, alerts, signals, trackers, coaching, activities, health
from routers.ask import router as ask_router
from routers.ask_demo import router as ask_demo_router
from routers.ms_auth import router as ms_auth_router
from routers.actions import router as actions_router
from routers.meeting import router as meeting_router
from routers.email_intel import router as email_intel_router
from routers.winloss import router as winloss_router
from routers.warnings import router as warnings_router
from routers.battlecard import router as battlecard_router
from routers.auth_crm import router as auth_crm_router
from routers.contacts import router as contacts_router
from routers.regional_analytics import router as regional_analytics_router
from routers.contracts import router as contracts_router
from routers.next_steps import router as next_steps_router
from routers.digest import router as digest_router
import uvicorn

app = FastAPI(
    title="DealIQ API",
    description="AI-powered deal clarity system for B2B SaaS revenue teams",
    version="1.0.0"
)

_frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
_allowed_origins = [_frontend_url, "http://localhost:5173", "http://localhost:3000", "http://localhost:8080"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(deals.router, prefix="/deals", tags=["Deals"])
app.include_router(analysis.router, prefix="/analysis", tags=["Analysis"])
app.include_router(ai_rep.router, prefix="/ai-rep", tags=["AI Sales Rep"])
app.include_router(forecast.router, prefix="/forecast", tags=["Forecast"])
app.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
app.include_router(signals.router, prefix="/signals", tags=["Signal Detector"])
app.include_router(trackers.router, prefix="/trackers", tags=["Smart Trackers"])
app.include_router(coaching.router, prefix="/coaching", tags=["Coaching"])
app.include_router(activities.router, prefix="/activities", tags=["Activities"])
app.include_router(health.router, tags=["Health"])
app.include_router(ask_router)
app.include_router(ask_demo_router)
app.include_router(ms_auth_router, prefix="/ms-auth", tags=["ms-auth"])
app.include_router(actions_router, prefix="/actions", tags=["actions"])
app.include_router(meeting_router, prefix="/meeting", tags=["meeting"])
app.include_router(email_intel_router, prefix="/email-intel", tags=["email-intel"])
app.include_router(winloss_router, prefix="/winloss", tags=["Win/Loss Intelligence"])
app.include_router(warnings_router, prefix="/warnings", tags=["Warnings"])
app.include_router(battlecard_router, tags=["Battle Card"])
app.include_router(auth_crm_router)  # /auth/{provider}/login + /auth/{provider}/callback
app.include_router(contacts_router, prefix="", tags=["Contact Intelligence"])
app.include_router(regional_analytics_router, prefix="/analytics", tags=["Regional Analytics"])
app.include_router(contracts_router, prefix="/contracts", tags=["Contract Intelligence"])
app.include_router(next_steps_router, tags=["Next Steps"])
app.include_router(digest_router, prefix="/digest", tags=["Daily Digest"])


_SEED_DOCX = os.path.join(os.path.dirname(__file__), "seeds", "vervotech_standard.docx")
_SEED_CONTRACT_NAME = "Vervotech Subscriber Agreement"
_SEED_CONTRACT_VERSION = "1.0"


async def _seed_standard_contract(logger) -> None:
    """On first startup, extract clauses from the bundled DOCX and store as the default standard contract."""
    import logging, json
    from database.connection import get_db

    if not os.path.exists(_SEED_DOCX):
        logger.warning("Seed DOCX not found at %s — skipping standard contract seed", _SEED_DOCX)
        return

    async for db in get_db():
        if db is None:
            logger.info("No DB — standard contract seed skipped (demo mode)")
            return
        try:
            from database.models import StandardContract
            from sqlalchemy import select
            result = await db.execute(select(StandardContract).limit(1))
            existing = result.scalar_one_or_none()
            if existing:
                logger.info("Standard contract already seeded (%s v%s) — skipping", existing.name, existing.version)
                return

            logger.info("Seeding standard contract from %s …", _SEED_DOCX)
            with open(_SEED_DOCX, "rb") as f:
                file_bytes = f.read()

            from services.contract_processor import extract_text_from_bytes, extract_clauses
            raw_text = await extract_text_from_bytes(file_bytes, "vervotech_standard.docx")
            clauses = await extract_clauses(raw_text)

            import shutil
            from routers.contracts import UPLOAD_DIR
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            dest = os.path.join(UPLOAD_DIR, "vervotech_standard.docx")
            shutil.copy2(_SEED_DOCX, dest)

            contract = StandardContract(
                name=_SEED_CONTRACT_NAME,
                version=_SEED_CONTRACT_VERSION,
                file_path=dest,
                raw_text=raw_text[:50000],
                is_active=True,
                clauses_json=json.dumps(clauses),
            )
            db.add(contract)
            await db.flush()
            logger.info("✓ Standard contract seeded: %s clauses extracted", len(clauses))
        except Exception as e:
            logger.warning("Contract seed DB write failed: %s", e)
        return  # only need first iteration of get_db()


@app.on_event("startup")
async def startup_event():
    import logging
    logger = logging.getLogger("dealiq.startup")

    try:
        from database.init_db import create_tables
        from database.connection import IS_POSTGRES
        await create_tables()
        db_type = "PostgreSQL" if IS_POSTGRES else "MySQL"
        logger.info("✓ %s connected and tables ready", db_type)
    except Exception as e:
        logger.warning("Database connection failed: %s", e)
        logger.warning("  Check DATABASE_URL in .env (MySQL or PostgreSQL)")
        logger.warning("  MySQL hint:      mysql+aiomysql://root:PASSWORD@localhost:3306/dealiq")
        logger.warning("  PostgreSQL hint: postgresql+asyncpg://user:pass@localhost:5432/dealiq")
        logger.warning("  App will run in stateless / demo mode")

    # ── Seed default standard contract from bundled DOCX ───────────────────────
    try:
        await _seed_standard_contract(logger)
    except Exception as e:
        logger.warning("Contract seed skipped: %s", e)

    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        async def _morning_scan_job():
            logger.info("Morning scan starting")
            try:
                from database.connection import get_db
                from services.daily_scanner import run_morning_scan
                async for db in get_db():
                    actions = await run_morning_scan(deals=[], db=db, generate_drafts=False)
                    logger.info("Morning scan complete, actions=%d", len(actions))
                    break
            except Exception as e:
                logger.exception("Morning scan failed: %s", e)

        async def _cache_cleanup_job():
            try:
                from services.email_cache import cleanup_expired_cache
                await cleanup_expired_cache()
            except Exception as e:
                logger.warning("Cache cleanup job failed: %s", e)

        async def _digest_email_job():
            """Send daily digest emails to users who have email notifications enabled."""
            logger.info("Digest email job starting")
            try:
                from database.connection import get_db
                from database.models import UserPreferences
                from sqlalchemy import select
                from services.digest_email import send_digest_email
                async for db in get_db():
                    if db is None:
                        break
                    result = await db.execute(
                        select(UserPreferences).where(UserPreferences.digest_email_enabled == True)
                    )
                    prefs_list = result.scalars().all()
                    for prefs in prefs_list:
                        if not prefs.email_address:
                            continue
                        try:
                            # Build a minimal digest for this user using demo data
                            # (full per-user Zoho fetch would need stored tokens)
                            from services.demo_data import SIMULATED_DEALS
                            from services.health_scorer import score_deal_from_zoho
                            from services.daily_digest_service import build_digest
                            deals = []
                            for d in SIMULATED_DEALS:
                                deal = dict(d)
                                r = score_deal_from_zoho(deal)
                                deal["health_score"] = r.total_score
                                deal["health_label"] = r.health_label
                                deals.append(deal)
                            digest = build_digest(deals)
                            await send_digest_email(prefs.email_address, digest)
                        except Exception as e:
                            logger.warning("Digest email failed for %s: %s", prefs.user_key, e)
                    break
            except Exception as e:
                logger.exception("Digest email job failed: %s", e)

        scheduler = AsyncIOScheduler()
        scheduler.add_job(_morning_scan_job, CronTrigger(hour=7, minute=0))
        scheduler.add_job(_cache_cleanup_job, CronTrigger(hour="*/1"))  # hourly
        scheduler.add_job(_digest_email_job, CronTrigger(hour=9, minute=0))  # 9 AM UTC default
        scheduler.start()
        logger.info("Scheduler started")
    except ModuleNotFoundError:
        logger.warning("apscheduler not installed — scheduler disabled. Run: pip install apscheduler")


@app.get("/")
def root():
    return {"message": "DealIQ API is running", "version": "1.0.0"}

@app.get("/debug/env")
def debug_env():
    import os
    db_url = os.getenv("DATABASE_URL")
    return {"db_url_set": db_url is not None, "db_url_prefix": db_url[:30] if db_url else None}


@app.get("/debug/db")
async def debug_db():
    """Diagnose DB connectivity, table list, and row counts. Works for both MySQL and PostgreSQL."""
    from sqlalchemy import text
    from database.connection import async_engine, AsyncSessionLocal, DATABASE_URL, IS_POSTGRES

    if async_engine is None:
        return {
            "connection": "FAILED",
            "error": "DATABASE_URL not set or engine failed to create",
            "database_url_prefix": (DATABASE_URL or "")[:40] or None,
        }

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return {"connection": "FAILED", "error": str(exc), "error_type": type(exc).__name__}

    try:
        async with async_engine.connect() as conn:
            if IS_POSTGRES:
                result = await conn.execute(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
                ))
            else:
                result = await conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result.fetchall()]

        counts = {}
        async with AsyncSessionLocal() as session:
            for table in tables:
                q = f'SELECT COUNT(*) FROM "{table}"' if IS_POSTGRES else f"SELECT COUNT(*) FROM `{table}`"
                result = await session.execute(text(q))
                counts[table] = result.scalar()

        return {
            "connection": "OK",
            "database_type": "postgresql" if IS_POSTGRES else "mysql",
            "database_url_prefix": DATABASE_URL[:40] if DATABASE_URL else None,
            "tables": tables,
            "row_counts": counts,
        }
    except Exception as exc:
        return {"connection": "OK", "count_error": str(exc)}

@app.get("/debug/ai")
async def debug_ai():
    """Verify Claude (Anthropic) is connected and responding."""
    import os
    from anthropic import AsyncAnthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"status": "error", "error": "ANTHROPIC_API_KEY not set in .env"}
    try:
        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": "Reply with exactly: DealIQ is running on Claude."}],
        )
        return {
            "status": "ok",
            "model": resp.model,
            "response": resp.content[0].text,
            "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/debug/routes")
def debug_routes():
    routes = [{"path": r.path, "methods": r.methods} for r in app.routes]
    return routes    

@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/health/db")
async def health_db():
    """Check database connectivity. Returns connected/disconnected + error detail."""
    try:
        from sqlalchemy import text
        from database.connection import async_engine, IS_POSTGRES
        if async_engine is None:
            return {"status": "disconnected", "error": "DATABASE_URL not set"}
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "connected", "db": "postgresql" if IS_POSTGRES else "mysql"}
    except Exception as e:
        return {"status": "disconnected", "error": str(e)}


@app.get("/health/cache")
async def health_cache():
    """Check Redis cache connectivity."""
    from services.cache import cache_health
    return await cache_health()


@app.post("/admin/cache/refresh")
async def admin_cache_refresh():
    """Manually flush the entire dealiq:* cache namespace."""
    from services.cache import cache_flush_all
    deleted = await cache_flush_all()
    return {"status": "cache_cleared", "keys_deleted": deleted}


@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    """
    Poll status of a background Celery task.

    Returns: status = processing | completed | failed
    Only available when Celery/Redis are configured.
    """
    try:
        from worker import celery_app as _celery
        result = _celery.AsyncResult(task_id)
        if result.ready():
            if result.successful():
                return {"status": "completed", "result": result.get(propagate=False)}
            else:
                return {"status": "failed", "error": str(result.result)}
        elif result.state == "STARTED":
            return {"status": "processing", "state": "started"}
        else:
            return {"status": "processing", "state": result.state}
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)