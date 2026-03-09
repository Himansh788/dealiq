"""
Deal cache service — read/write Zoho deal data to MySQL.

Freshness rules (via cache_manager):
  - Fresh  (< 5 min): return from DB immediately, no Zoho call.
  - Stale  (> 5 min but data exists): return stale data immediately;
      if >30% of the user's deals are stale, trigger a background bulk sync.
  - Empty  (no rows): return None so the caller falls through to Zoho.

All operations are fail-safe: DB errors are logged and the app continues
in stateless mode (direct Zoho API calls every time).
"""
import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from services.cache_manager import (
    is_fresh, get_cache_status, BULK_SYNC_STALE_THRESHOLD, TTL_CONFIG,
)

logger = logging.getLogger(__name__)


def deal_internal_id(zoho_id: str) -> str:
    """Deterministic UUID from a Zoho deal ID.

    Using uuid5 means the same Zoho ID always maps to the same internal UUID,
    so health_scores / decisions foreign keys stay consistent without a lookup.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_X500, f"zoho_deal:{zoho_id}"))


async def get_cached_deals(
    db, user_id: str
) -> tuple[Optional[list[dict]], dict]:
    """Return (deals, cache_meta) for a user.

    deals     — list of raw deal dicts if any rows exist, else None.
    cache_meta — dict suitable for embedding in API responses as _cache.

    Returns (None, ...) only when there are zero rows in the DB, so the caller
    knows to do a blocking Zoho fetch.  When rows exist but are stale, returns
    the stale deals immediately and the caller should trigger a background sync.
    """
    if db is None:
        return None, _no_cache_meta()
    try:
        from sqlalchemy import text

        result = await db.execute(
            text("""
                SELECT raw_data, synced_at
                FROM   deals
                WHERE  owner_email = :uid
                  AND  raw_data    IS NOT NULL
                  AND  is_demo     = false
                ORDER  BY synced_at DESC
            """),
            {"uid": user_id},
        )
        rows = result.fetchall()

        if not rows:
            return None, _no_cache_meta()

        deals: list[dict] = []
        oldest_synced_at: Optional[datetime] = None
        stale_count = 0

        for (raw, synced_at) in rows:
            if isinstance(raw, str):
                raw = json.loads(raw)
            deals.append(raw)

            if not is_fresh(synced_at, "deals"):
                stale_count += 1
            if oldest_synced_at is None or (synced_at and synced_at < oldest_synced_at):
                oldest_synced_at = synced_at

        stale_ratio = stale_count / len(rows)
        needs_bg_sync = stale_ratio >= BULK_SYNC_STALE_THRESHOLD

        if needs_bg_sync:
            logger.debug(
                "BG sync needed for %s: %d/%d deals stale (%.0f%%)",
                user_id, stale_count, len(rows), stale_ratio * 100,
            )
        else:
            logger.debug("Cache HIT: %d deals for %s", len(deals), user_id)

        cache_meta = get_cache_status(oldest_synced_at, "deals")
        cache_meta["needs_background_sync"] = needs_bg_sync
        cache_meta["stale_count"] = stale_count
        cache_meta["total_count"] = len(rows)

        return deals, cache_meta

    except Exception as exc:
        logger.warning("Cache read failed: %s", exc)
        return None, _no_cache_meta()


def _no_cache_meta() -> dict:
    return get_cache_status(None, "deals")


async def invalidate_deal(db, zoho_id: str) -> None:
    """Force a single deal stale by zeroing its synced_at.

    The next list_deals call will see it as stale and background-refresh it.
    """
    if db is None or not zoho_id:
        return
    from sqlalchemy import text
    try:
        await db.execute(
            text("UPDATE deals SET synced_at = '2000-01-01' WHERE zoho_id = :zid"),
            {"zid": zoho_id},
        )
        await db.commit()
    except Exception as exc:
        logger.warning("Invalidate deal failed deal=%s: %s", zoho_id, exc)
        try:
            await db.rollback()
        except Exception:
            pass


async def upsert_deals(
    db,
    deals: list[dict],
    user_id: str,
    health_results: dict | None = None,
    sync_source: str = "zoho",
) -> None:
    """Upsert a list of mapped deal dicts into the cache table.

    health_results: optional {zoho_id: DealHealthResult} — caches the latest
    score alongside the deal so the team-summary scorer has pre-computed data.
    sync_source: 'zoho' | 'manual' | 'demo'
    """
    if db is None or not deals:
        return
    from sqlalchemy import text
    from database.connection import IS_POSTGRES
    now = datetime.utcnow()  # naive UTC — works with TIMESTAMP WITHOUT TIME ZONE
    health_results = health_results or {}
    try:
        for deal in deals:
            zoho_id = str(deal.get("id") or deal.get("zoho_id") or "").strip()
            if not zoho_id:
                continue
            internal_id = deal_internal_id(zoho_id)

            hr = health_results.get(zoho_id)

            params = {
                "id":           internal_id,
                "zoho_id":      zoho_id,
                "name":         (deal.get("name") or deal.get("deal_name") or "")[:255],
                "company":      (deal.get("account_name") or deal.get("company") or "")[:255],
                "stage":        (deal.get("stage") or "")[:100],
                "amount":       float(deal.get("amount") or 0),
                "owner_email":  str(user_id or "")[:255],
                "closing_date": (str(deal.get("closing_date") or "")[:20]) or None,
                "lat":          (str(deal.get("last_activity_time") or "")[:50]) or None,
                "next_step":    deal.get("next_step") or None,
                "health_score": (hr.total_score if hr else None) or deal.get("health_score") or None,
                "health_label": (hr.health_label if hr else None) or deal.get("health_label") or None,
                "sync_source":  sync_source[:50],
                "synced_at":    now,
                "raw_data":     json.dumps(deal),
                "now":          now,
            }

            if IS_POSTGRES:
                await db.execute(text("""
                    INSERT INTO deals
                        (id, zoho_id, name, company, stage, amount, owner_email,
                         closing_date, last_activity_time, next_step,
                         health_score, health_label, sync_source, is_demo,
                         synced_at, raw_data, created_at)
                    VALUES
                        (:id, :zoho_id, :name, :company, :stage, :amount, :owner_email,
                         :closing_date, :lat, :next_step,
                         :health_score, :health_label, :sync_source, false,
                         :synced_at, cast(:raw_data AS jsonb), :now)
                    ON CONFLICT (zoho_id) DO UPDATE SET
                        name               = EXCLUDED.name,
                        company            = EXCLUDED.company,
                        stage              = EXCLUDED.stage,
                        amount             = EXCLUDED.amount,
                        owner_email        = EXCLUDED.owner_email,
                        closing_date       = EXCLUDED.closing_date,
                        last_activity_time = EXCLUDED.last_activity_time,
                        next_step          = EXCLUDED.next_step,
                        health_score       = EXCLUDED.health_score,
                        health_label       = EXCLUDED.health_label,
                        sync_source        = EXCLUDED.sync_source,
                        synced_at          = EXCLUDED.synced_at,
                        raw_data           = EXCLUDED.raw_data
                """), params)
            else:
                await db.execute(text("""
                    INSERT INTO deals
                        (id, zoho_id, name, company, stage, amount, owner_email,
                         closing_date, last_activity_time, next_step,
                         health_score, health_label, sync_source, is_demo,
                         synced_at, raw_data, created_at)
                    VALUES
                        (:id, :zoho_id, :name, :company, :stage, :amount, :owner_email,
                         :closing_date, :lat, :next_step,
                         :health_score, :health_label, :sync_source, 0,
                         :synced_at, :raw_data, :now)
                    ON DUPLICATE KEY UPDATE
                        name               = VALUES(name),
                        company            = VALUES(company),
                        stage              = VALUES(stage),
                        amount             = VALUES(amount),
                        owner_email        = VALUES(owner_email),
                        closing_date       = VALUES(closing_date),
                        last_activity_time = VALUES(last_activity_time),
                        next_step          = VALUES(next_step),
                        health_score       = VALUES(health_score),
                        health_label       = VALUES(health_label),
                        sync_source        = VALUES(sync_source),
                        synced_at          = VALUES(synced_at),
                        raw_data           = VALUES(raw_data)
                """), params)
        await db.commit()
        logger.debug("Upserted %d deals to cache (source=%s)", len(deals), sync_source)
    except Exception as exc:
        logger.warning("Cache write failed: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
