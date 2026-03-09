"""
Health score persistence.

Every time a deal is scored, a row is inserted into health_scores so we can
show trend arrows (improving / declining / stable) on the dashboard.
"""
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


async def persist_health_score(db, deal_zoho_id: str, result) -> None:
    """Insert a DealHealthResult into the health_scores table.

    Safe to call on every score computation — it only appends, never updates.
    Silently no-ops if db is None.
    """
    if db is None or not deal_zoho_id:
        return
    from sqlalchemy import text
    from services.deal_db import deal_internal_id
    try:
        internal_id = deal_internal_id(deal_zoho_id)

        # Guard: skip if the parent deal row doesn't exist yet (FK constraint).
        # Deals are lazily synced to the DB; the health score can be retried later.
        exists = await db.execute(
            text("SELECT 1 FROM deals WHERE id = :id LIMIT 1"),
            {"id": internal_id},
        )
        if not exists.scalar():
            logger.debug("Score persist skipped deal=%s — not in deals table yet", deal_zoho_id)
            return

        signals_json = json.dumps([
            {"name": s.name, "score": s.score, "max_score": s.max_score,
             "label": s.label, "detail": s.detail}
            for s in (result.signals or [])
        ])
        await db.execute(text("""
            INSERT INTO health_scores
                (id, deal_id, total_score, signals, health_label, recommendation,
                 scored_at, score_version)
            VALUES
                (:id, :deal_id, :score, :signals, :label, :rec, :now, :ver)
        """), {
            "id":      str(uuid.uuid4()),
            "deal_id": internal_id,
            "score":   result.total_score,
            "signals": signals_json,
            "label":   result.health_label,
            "rec":     (result.recommendation or "")[:1000],
            "now":     datetime.utcnow(),  # naive UTC — PostgreSQL TIMESTAMP WITHOUT TIME ZONE
            "ver":     1,
        })
        await db.commit()
    except Exception as exc:
        logger.warning("Score persist failed deal=%s: %s", deal_zoho_id, exc)
        try:
            await db.rollback()
        except Exception:
            pass


async def get_score_history(db, deal_zoho_id: str, days: int = 30) -> list[dict]:
    """Return score history for a deal, newest first (up to 90 rows)."""
    if db is None:
        return []
    from sqlalchemy import text
    from services.deal_db import deal_internal_id
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await db.execute(text("""
            SELECT total_score, health_label, scored_at
            FROM   health_scores
            WHERE  deal_id   = :deal_id
              AND  scored_at > :cutoff
            ORDER  BY scored_at DESC
            LIMIT  90
        """), {"deal_id": deal_internal_id(deal_zoho_id), "cutoff": cutoff})
        rows = result.fetchall()
        return [
            {
                "score":     r[0],
                "label":     r[1],
                "scored_at": r[2].isoformat() if r[2] else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Score history failed deal=%s: %s", deal_zoho_id, exc)
        return []


async def batch_get_trends(db, zoho_ids: list[str]) -> dict[str, str]:
    """Return {zoho_id: trend} for a list of deals in a single SQL query.

    Trend is 'improving' / 'declining' / 'stable'.
    Used in list_deals to annotate every deal row without N+1 queries.
    """
    if db is None or not zoho_ids:
        return {}
    from sqlalchemy import text
    from services.deal_db import deal_internal_id

    internal_ids = [deal_internal_id(zid) for zid in zoho_ids]
    id_to_zoho = {deal_internal_id(zid): zid for zid in zoho_ids}

    from database.connection import IS_POSTGRES

    try:
        cutoff_now  = datetime.utcnow()  # naive UTC for TIMESTAMP WITHOUT TIME ZONE columns
        cutoff_7d   = cutoff_now - timedelta(days=7)
        cutoff_old  = cutoff_now - timedelta(days=8)

        # PostgreSQL uses = ANY(:ids) with a list; MySQL uses IN :ids with a tuple.
        if IS_POSTGRES:
            latest_res = await db.execute(text("""
                SELECT deal_id, total_score
                FROM   health_scores h1
                WHERE  deal_id = ANY(:ids)
                  AND  scored_at = (
                      SELECT MAX(scored_at) FROM health_scores h2
                      WHERE h2.deal_id = h1.deal_id
                  )
            """), {"ids": internal_ids})
        else:
            latest_res = await db.execute(text("""
                SELECT deal_id, total_score
                FROM   health_scores h1
                WHERE  deal_id IN :ids
                  AND  scored_at = (
                      SELECT MAX(scored_at) FROM health_scores h2
                      WHERE h2.deal_id = h1.deal_id
                  )
            """), {"ids": tuple(internal_ids)})
        latest = {r[0]: r[1] for r in latest_res.fetchall()}

        # Oldest score in the window 7-8 days ago per deal
        if IS_POSTGRES:
            old_res = await db.execute(text("""
                SELECT deal_id, total_score
                FROM   health_scores h1
                WHERE  deal_id = ANY(:ids)
                  AND  scored_at < :cutoff_7d
                  AND  scored_at > :cutoff_old
                ORDER  BY scored_at DESC
            """), {"ids": internal_ids, "cutoff_7d": cutoff_7d, "cutoff_old": cutoff_old})
        else:
            old_res = await db.execute(text("""
                SELECT deal_id, total_score
                FROM   health_scores h1
                WHERE  deal_id IN :ids
                  AND  scored_at < :cutoff_7d
                  AND  scored_at > :cutoff_old
                ORDER  BY scored_at DESC
            """), {"ids": tuple(internal_ids), "cutoff_7d": cutoff_7d, "cutoff_old": cutoff_old})
        # Keep only the most recent per deal in that window
        old: dict[str, int] = {}
        for r in old_res.fetchall():
            if r[0] not in old:
                old[r[0]] = r[1]

        trends: dict[str, str] = {}
        for internal_id, zoho_id in id_to_zoho.items():
            if internal_id not in latest or internal_id not in old:
                continue
            diff = latest[internal_id] - old[internal_id]
            if diff >= 5:
                trends[zoho_id] = "improving"
            elif diff <= -5:
                trends[zoho_id] = "declining"
            else:
                trends[zoho_id] = "stable"

        return trends
    except Exception as exc:
        logger.warning("Batch trends failed: %s", exc)
        return {}
