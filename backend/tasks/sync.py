"""
Celery tasks for Zoho CRM synchronization.
"""

import asyncio
import logging

from worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.sync.sync_zoho_deals", bind=True, max_retries=1)
def sync_zoho_deals(self, access_token: str, user_id: str | None = None):
    """
    Background task: fetch all deals from Zoho CRM, upsert to DB, flush cache.

    Dispatched after a manual /deals/sync call so the HTTP response returns
    immediately while the sync runs in the background.
    """
    try:
        asyncio.run(_async_sync_zoho(access_token, user_id))
    except Exception as exc:
        logger.exception("sync_zoho_deals failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


async def _async_sync_zoho(access_token: str, user_id: str | None) -> None:
    from services.cache import cache_flush_all

    try:
        from services.zoho_client import fetch_deals
        from services.deal_db import upsert_deals
        from database.connection import AsyncSessionLocal

        deals = await fetch_deals(access_token)
        if not deals:
            logger.info("sync_zoho_deals: no deals returned from Zoho")
            return

        if AsyncSessionLocal:
            async with AsyncSessionLocal() as session:
                await upsert_deals(deals, session)
                await session.commit()

        # Flush all caches after a full sync
        flushed = await cache_flush_all()
        logger.info("sync_zoho_deals: synced %d deals, flushed %d cache keys", len(deals), flushed)

    except Exception as exc:
        logger.exception("_async_sync_zoho failed: %s", exc)
        raise
