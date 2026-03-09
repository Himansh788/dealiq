"""
Celery periodic task: refresh all deal health scores every 5 minutes.
Scheduled via celery beat (see worker.py beat_schedule).
"""

import asyncio
import logging
import os

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.health.recompute_all")
def recompute_all():
    """
    Periodic task (every 5 min): re-score all active deals and refresh the cache.

    Only runs if DATABASE_URL is set and deals exist in the DB.
    Skips gracefully in demo mode.
    """
    asyncio.run(_async_recompute_all())


async def _async_recompute_all() -> None:
    from database.connection import AsyncSessionLocal, DATABASE_URL
    from services.cache import cache_set, cache_key
    import os

    if not DATABASE_URL or AsyncSessionLocal is None:
        logger.debug("recompute_all: no DB configured — skipping")
        return

    try:
        from database.models import Deal
        from services.health_scorer import score_deal_from_zoho
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Deal).where(Deal.is_demo == False))
            deals = result.scalars().all()

        if not deals:
            logger.debug("recompute_all: no deals in DB — skipping")
            return

        refreshed = 0
        for deal in deals:
            raw = deal.raw_data
            if not raw:
                continue
            try:
                score = score_deal_from_zoho(raw)
                key = cache_key("health", deal.zoho_id or deal.id)
                await cache_set(key, score, ttl=int(os.getenv("CACHE_TTL_HEALTH_SCORES", "300")))

                # Persist back to health_signals column
                async with AsyncSessionLocal() as session:
                    session.add(deal)
                    deal.health_signals = score
                    deal.health_score = score.get("total_score")
                    deal.health_label = score.get("health_label")
                    await session.commit()

                refreshed += 1
            except Exception as exc:
                logger.debug("recompute_all: failed for deal %s: %s", deal.id, exc)

        logger.info("recompute_all: refreshed %d/%d deals", refreshed, len(deals))

    except Exception as exc:
        logger.exception("recompute_all failed: %s", exc)
