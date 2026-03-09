"""
DB-backed cache for Zoho email body responses.

Each method opens and closes its own session using AsyncSessionLocal (the factory),
so it is safe to call from concurrent asyncio tasks. No session is ever shared.

Design contract:
  - get_*  methods: one session → one SELECT → close
  - set_*  methods: one session → one INSERT/UPDATE → commit → close
  - Called from zoho_client._fetch_emails_for_record:
      1. get_many()  before asyncio.gather()  (batch read, 1 session)
      2. set_many()  after  asyncio.gather()  (batch write, 1 session)
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import IS_POSTGRES

logger = logging.getLogger(__name__)

# Email bodies are immutable once received — safe to cache for 24 hours
EMAIL_BODY_TTL_HOURS = 24

# Stored in response_data when the body is genuinely empty.
# Prevents re-fetching a URL we already know returns nothing.
_EMPTY_SENTINEL = "__EMPTY__"


def _make_key(module: str, record_id: str, message_id: str) -> str:
    return f"zoho:email_body:{module}/{record_id}:{message_id}"


def _get_factory():
    """Return AsyncSessionLocal or None if DB is not configured."""
    from database.connection import AsyncSessionLocal
    return AsyncSessionLocal


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_cached_email_bodies_batch(
    keys_meta: list[tuple[str, str, str]],  # [(module, record_id, message_id), ...]
) -> dict[str, str | None]:
    """
    Batch cache lookup. Returns {message_id: body_or_None}.
      None  → cache miss (fetch from Zoho)
      ""    → known-empty (skip Zoho; previous fetch returned nothing)
      str   → cached body text

    Uses a single SELECT … IN (…) — one fresh session, opened and closed here.
    """
    factory = _get_factory()
    if factory is None or not keys_meta:
        return {mid: None for _, _, mid in keys_meta}

    from database.models import ApiCache

    now = datetime.utcnow()  # naive UTC — TIMESTAMP WITHOUT TIME ZONE
    key_to_mid: dict[str, str] = {_make_key(m, r, mid): mid for m, r, mid in keys_meta}
    result: dict[str, str | None] = {mid: None for _, _, mid in keys_meta}

    try:
        async with factory() as session:
            rows = await session.execute(
                select(ApiCache.cache_key, ApiCache.response_data).where(
                    ApiCache.cache_key.in_(list(key_to_mid)),
                    ApiCache.expires_at > now,
                )
            )
            for cache_key, response_data in rows:
                mid = key_to_mid.get(cache_key)
                if not mid:
                    continue
                body = json.loads(response_data).get("body", _EMPTY_SENTINEL)
                result[mid] = "" if body == _EMPTY_SENTINEL else body

        hits = sum(1 for v in result.values() if v is not None)
        logger.debug(
            "email_cache batch lookup: %d keys → %d hits, %d misses",
            len(keys_meta), hits, len(keys_meta) - hits,
        )
    except Exception as e:
        logger.warning("email_cache batch get error: %s", e)
        # Return all-miss so the caller falls through to Zoho
        return {mid: None for _, _, mid in keys_meta}

    return result


async def set_cached_email_bodies_batch(
    entries: list[tuple[str, str, str, str]],  # [(module, record_id, message_id, body), ...]
) -> None:
    """
    Batch cache write. One session, one transaction for all entries.
    Pass body="" to record a known-empty result (prevents future re-fetches).
    """
    factory = _get_factory()
    if factory is None or not entries:
        return

    from database.models import ApiCache

    now = datetime.utcnow()  # naive UTC — TIMESTAMP WITHOUT TIME ZONE
    expires = now + timedelta(hours=EMAIL_BODY_TTL_HOURS)

    rows = []
    for module, record_id, message_id, body in entries:
        stored = _EMPTY_SENTINEL if body == "" else body
        rows.append({
            "cache_key": _make_key(module, record_id, message_id),
            "response_data": json.dumps({"body": stored}),
            "source": "zoho",
            "endpoint": "email_body",
            "expires_at": expires,
        })

    try:
        async with factory() as session:
            if IS_POSTGRES:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                stmt = pg_insert(ApiCache).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["cache_key"],
                    set_={
                        "response_data": stmt.excluded.response_data,
                        "expires_at": stmt.excluded.expires_at,
                        "updated_at": now,
                    },
                )
            else:
                from sqlalchemy.dialects.mysql import insert as mysql_insert
                stmt = mysql_insert(ApiCache).values(rows)
                stmt = stmt.on_duplicate_key_update(
                    response_data=stmt.inserted.response_data,
                    expires_at=stmt.inserted.expires_at,
                    updated_at=now,
                )
            await session.execute(stmt)
            await session.commit()
        logger.debug("email_cache batch write: stored %d entries", len(rows))
    except Exception as e:
        logger.warning("email_cache batch set error: %s", e)


async def cleanup_expired_cache() -> int:
    """Delete expired cache entries. Returns count deleted. Safe to call from scheduler."""
    factory = _get_factory()
    if factory is None:
        return 0

    from database.models import ApiCache

    now = datetime.utcnow()  # naive UTC
    try:
        async with factory() as session:
            result = await session.execute(
                delete(ApiCache).where(ApiCache.expires_at <= now)
            )
            await session.commit()
            deleted = result.rowcount or 0
        if deleted:
            logger.info("email_cache cleanup: deleted %d expired entries", deleted)
        return deleted
    except Exception as e:
        logger.warning("email_cache cleanup error: %s", e)
        return 0
