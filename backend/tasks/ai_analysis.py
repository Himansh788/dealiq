"""
Celery tasks for background AI analysis.

These run synchronously inside Celery workers (no asyncio).
All async service functions have sync wrappers here using asyncio.run().
"""

import asyncio
import logging
import os

from worker import celery_app

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine synchronously from a Celery task."""
    return asyncio.run(coro)


@celery_app.task(name="tasks.ai_analysis.analyze_deal", bind=True, max_retries=2)
def analyze_deal(self, deal_id: str, access_token: str):
    """
    Background task: run full AI health analysis on a deal and cache the result.

    Dispatched from POST /deals/{deal_id}/refresh when the request includes
    async_mode=true (future enhancement). Currently available for explicit dispatch.
    """
    try:
        from services.health_scorer import score_deal_from_zoho
        from services.cache import cache_key
        import json

        async def _run_analysis():
            from services.zoho_client import fetch_deal_by_id
            from services.cache import cache_set

            raw = await fetch_deal_by_id(deal_id, access_token)
            if not raw:
                return None

            score = score_deal_from_zoho(raw)

            # Persist health_signals to DB if available
            await _persist_health_signals(deal_id, score)

            key = cache_key("health", deal_id)
            await cache_set(key, score, ttl=int(os.getenv("CACHE_TTL_HEALTH_SCORES", "300")))
            return score

        result = _run(_run_analysis())
        logger.info("analyze_deal complete: deal_id=%s score=%s", deal_id, result.get("total_score") if result else "N/A")
        return {"deal_id": deal_id, "status": "completed", "score": result}

    except Exception as exc:
        logger.exception("analyze_deal failed for deal_id=%s: %s", deal_id, exc)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.ai_analysis.analyze_mismatch", bind=True, max_retries=1)
def analyze_mismatch(self, transcript: str, email_body: str, deal_id: str | None = None):
    """
    Background task: run narrative mismatch detection.

    Result is cached under dealiq:mismatch:{deal_id} if deal_id is provided.
    """
    try:
        async def _run_mismatch():
            from services.claude_client import check_mismatch
            from services.cache import cache_set, cache_key

            result = await check_mismatch(transcript, email_body)

            if deal_id and result:
                key = cache_key("mismatch", deal_id)
                await cache_set(key, result, ttl=int(os.getenv("CACHE_TTL_AI_ANALYSIS", "1800")))

            return result

        result = _run(_run_mismatch())
        return {"deal_id": deal_id, "status": "completed", "result": result}

    except Exception as exc:
        logger.exception("analyze_mismatch failed for deal_id=%s: %s", deal_id, exc)
        raise self.retry(exc=exc, countdown=15)


async def _persist_health_signals(deal_id: str, score: dict) -> None:
    """Persist computed health signals to the Deal.health_signals JSONB column."""
    try:
        from database.connection import AsyncSessionLocal
        from database.models import Deal
        from sqlalchemy import select

        if AsyncSessionLocal is None:
            return

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Deal).where(Deal.zoho_id == deal_id)
            )
            deal = result.scalar_one_or_none()
            if deal:
                deal.health_signals = score
                deal.health_score = score.get("total_score")
                deal.health_label = score.get("health_label")
                await session.commit()
    except Exception as exc:
        logger.debug("_persist_health_signals failed for deal_id=%s: %s", deal_id, exc)
