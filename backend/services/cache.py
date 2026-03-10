"""
Redis caching layer for DealIQ.

Usage:
    from services.cache import cache_get, cache_set, cache_delete_pattern, cache_key

    key = cache_key("health", deal_id)
    cached = await cache_get(key)
    if cached:
        return cached
    result = await compute_something()
    await cache_set(key, result, ttl=300)

If Redis is unavailable, all functions degrade gracefully (get → None, set → no-op).
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# TTL constants — override via .env
TTL_HEALTH_SCORES    = int(os.getenv("CACHE_TTL_HEALTH_SCORES",    "300"))   # 5 min
TTL_PIPELINE_METRICS = int(os.getenv("CACHE_TTL_PIPELINE_METRICS", "300"))   # 5 min (was 2 — too aggressive, caused redundant Groq calls)
TTL_AI_ANALYSIS      = int(os.getenv("CACHE_TTL_AI_ANALYSIS",      "3600"))  # 1 hr
TTL_DEAL_DETAIL      = int(os.getenv("CACHE_TTL_DEAL_DETAIL",      "180"))   # 3 min
TTL_EMAIL_ENRICHMENT = int(os.getenv("CACHE_TTL_EMAIL_ENRICHMENT",  "300"))  # 5 min
TTL_EMAIL_INTEL      = int(os.getenv("CACHE_TTL_EMAIL_INTEL",       "900"))  # 15 min — full thread+AI response
TTL_TIMELINE         = int(os.getenv("CACHE_TTL_TIMELINE",          "600"))  # 10 min
TTL_ACTIVITIES       = int(os.getenv("CACHE_TTL_ACTIVITIES",        "300"))  # 5 min

# Connection pool — created lazily on first use, shared across requests.
_pool = None


def _get_pool():
    """Return (or lazily create) the async Redis connection pool."""
    global _pool
    if _pool is None:
        try:
            import redis.asyncio as redis  # type: ignore[import-untyped]
            _pool = redis.ConnectionPool.from_url(
                REDIS_URL,
                decode_responses=True,
                max_connections=20,
            )
            logger.info("Redis connection pool created: %s", REDIS_URL[:30])
        except Exception as exc:
            logger.warning("Redis not available — caching disabled: %s", exc)
    return _pool


async def _get_client():
    """Return a Redis client from the shared pool, or None if Redis is unavailable."""
    pool = _get_pool()
    if pool is None:
        return None
    try:
        import redis.asyncio as redis  # type: ignore[import-untyped]
        return redis.Redis(connection_pool=pool)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public cache API
# ---------------------------------------------------------------------------

def cache_key(prefix: str, *args: Any) -> str:
    """
    Generate a consistent, namespaced cache key.

    Examples:
        cache_key("health", deal_id)       → "dealiq:health:abc123"
        cache_key("metrics", user_id)      → "dealiq:metrics:user@example.com"
    """
    raw = ":".join(str(a) for a in args)
    return f"dealiq:{prefix}:{raw}"


async def cache_get(key: str) -> Any | None:
    """
    Retrieve a value from cache.

    Returns the deserialized value on hit, or None on miss / Redis unavailable.
    """
    client = await _get_client()
    if client is None:
        return None
    try:
        val = await client.get(key)
        return json.loads(val) if val is not None else None
    except Exception as exc:
        logger.debug("cache_get failed for key=%s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl: int = 300) -> None:
    """
    Store a value in cache with a TTL (seconds).

    No-op if Redis is unavailable.
    """
    client = await _get_client()
    if client is None:
        return
    try:
        await client.set(key, json.dumps(value, default=str), ex=ttl)
    except Exception as exc:
        logger.debug("cache_set failed for key=%s: %s", key, exc)


async def cache_delete(key: str) -> None:
    """Delete a single key from cache."""
    client = await _get_client()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception as exc:
        logger.debug("cache_delete failed for key=%s: %s", key, exc)


async def cache_delete_pattern(pattern: str) -> int:
    """
    Invalidate all keys matching a glob pattern (e.g. "dealiq:health:*").

    Returns number of keys deleted. No-op if Redis is unavailable.
    """
    client = await _get_client()
    if client is None:
        return 0
    try:
        deleted = 0
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
            deleted += 1
        if deleted:
            logger.debug("cache_delete_pattern: deleted %d keys matching %s", deleted, pattern)
        return deleted
    except Exception as exc:
        logger.debug("cache_delete_pattern failed for pattern=%s: %s", pattern, exc)
        return 0


async def cache_flush_all() -> int:
    """Flush the entire dealiq:* namespace. Use sparingly (e.g. after full Zoho sync)."""
    return await cache_delete_pattern("dealiq:*")


async def cache_health() -> dict:
    """Return cache health info for the /health/cache endpoint."""
    client = await _get_client()
    if client is None:
        return {"status": "unavailable", "redis_url": REDIS_URL[:30]}
    try:
        await client.ping()
        info = await client.info("memory")
        return {
            "status": "connected",
            "redis_url": REDIS_URL[:30],
            "used_memory_human": info.get("used_memory_human"),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
