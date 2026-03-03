from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import auth, deals, analysis, ai_rep, forecast, alerts, signals, trackers, coaching, activities, health
from routers.ask import router as ask_router
from routers.ask_demo import router as ask_demo_router
from routers.ms_auth import router as ms_auth_router
from routers.actions import router as actions_router
from routers.meeting import router as meeting_router
from routers.email_intel import router as email_intel_router
import uvicorn

app = FastAPI(
    title="DealIQ API",
    description="AI-powered deal clarity system for B2B SaaS revenue teams",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.on_event("startup")
async def startup_event():
    import logging
    logger = logging.getLogger("dealiq.startup")

    try:
        from database.init_db import create_tables
        await create_tables()
    except Exception as e:
        logger.warning("DB init skipped (no Postgres?): %s", e)

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

        scheduler = AsyncIOScheduler()
        scheduler.add_job(_morning_scan_job, CronTrigger(hour=7, minute=0))
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

@app.get("/debug/routes")
def debug_routes():
    routes = [{"path": r.path, "methods": r.methods} for r in app.routes]
    return routes    

@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)