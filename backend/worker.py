"""
Celery worker configuration for DealIQ.

Start worker:
    celery -A worker worker --loglevel=info --queues=ai,sync,health

Start beat scheduler (periodic tasks):
    celery -A worker beat --loglevel=info
"""

import os
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "dealiq",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "tasks.ai_analysis",
        "tasks.health",
        "tasks.sync",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=120,           # hard limit: 2 min per task
    task_soft_time_limit=90,       # soft limit: warn at 90s
    worker_concurrency=4,
    result_expires=3600,           # keep task results for 1 hour
    task_routes={
        "tasks.ai_analysis.*": {"queue": "ai"},
        "tasks.sync.*": {"queue": "sync"},
        "tasks.health.*": {"queue": "health"},
    },
)

# Periodic tasks (run celery beat alongside worker)
celery_app.conf.beat_schedule = {
    "refresh-health-scores-every-5-min": {
        "task": "tasks.health.recompute_all",
        "schedule": crontab(minute="*/5"),
    },
}
