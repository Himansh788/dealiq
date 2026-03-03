"""
Cache freshness utility.

Single source of truth for TTL configuration and staleness checks.
No DB dependencies — pure datetime logic so it can be used anywhere.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TTL config — how old is "too old" for each table
# None means the data never expires (transcripts, summaries are immutable).
# ---------------------------------------------------------------------------
TTL_CONFIG: dict[str, Optional[timedelta]] = {
    "deals":                timedelta(minutes=5),
    "health_scores":        timedelta(minutes=15),
    "emails":               timedelta(minutes=10),
    "email_analyses":       timedelta(hours=24),
    "transcripts":          None,
    "transcript_summaries": None,
    "meeting_log":          timedelta(hours=1),
}

# If this fraction of cached rows is stale, trigger a background bulk sync
# rather than waiting for the next full cache miss.
BULK_SYNC_STALE_THRESHOLD = 0.30


def is_fresh(synced_at: Optional[datetime], table_name: str) -> bool:
    """Return True when cached data is still within its TTL.

    Always returns True for tables with TTL=None (never-expiring data).
    Always returns False when synced_at is None (data was never cached).
    """
    ttl = TTL_CONFIG.get(table_name)
    if ttl is None:
        return True
    if synced_at is None:
        return False

    now = datetime.now(timezone.utc)
    if synced_at.tzinfo is None:
        synced_at = synced_at.replace(tzinfo=timezone.utc)

    fresh = (now - synced_at) < ttl
    logger.debug(
        "Cache check [%s]: age=%s ttl=%s fresh=%s",
        table_name, now - synced_at, ttl, fresh,
    )
    return fresh


def get_cache_status(synced_at: Optional[datetime], table_name: str) -> dict:
    """Return a _cache metadata dict suitable for embedding in API responses.

    Frontend uses this to show Live / Syncing / Stale indicators.
    """
    ttl = TTL_CONFIG.get(table_name)
    ttl_seconds = int(ttl.total_seconds()) if ttl else None

    if synced_at is None:
        return {
            "cached": False,
            "fresh": False,
            "synced_at": None,
            "age_seconds": None,
            "ttl_seconds": ttl_seconds,
            "expires_in_seconds": 0,
            "source": "not_cached",
        }

    now = datetime.now(timezone.utc)
    if synced_at.tzinfo is None:
        synced_at = synced_at.replace(tzinfo=timezone.utc)

    age = now - synced_at
    age_seconds = int(age.total_seconds())
    fresh = is_fresh(synced_at, table_name)

    expires_in = 0
    if ttl and fresh:
        expires_in = max(0, int((ttl - age).total_seconds()))

    return {
        "cached": True,
        "fresh": fresh,
        "synced_at": synced_at.isoformat(),
        "age_seconds": age_seconds,
        "ttl_seconds": ttl_seconds,
        "expires_in_seconds": expires_in,
        "source": "cache" if fresh else "stale",
    }
