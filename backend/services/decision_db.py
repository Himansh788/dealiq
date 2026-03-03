"""
ACK decision persistence.

Stores Advance / Close / Kill / Escalate decisions so they survive page reloads
and can be surfaced in the deal timeline / history view.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def persist_decision(
    db,
    deal_zoho_id: str,
    action: str,
    user_email: str,
    reasoning: Optional[str] = None,
) -> None:
    """Insert an ACK decision row.

    Safe to call on every ACK — idempotent in the sense that duplicates are
    allowed (the rep may advance the same deal twice on different dates).
    Silently no-ops if db is None.
    """
    if db is None or not deal_zoho_id:
        return
    from sqlalchemy import text
    from services.deal_db import deal_internal_id
    try:
        await db.execute(text("""
            INSERT INTO decisions
                (id, deal_id, user_email, action, reasoning, decided_at)
            VALUES
                (:id, :deal_id, :user_email, :action, :reasoning, :now)
        """), {
            "id":         str(uuid.uuid4()),
            "deal_id":    deal_internal_id(deal_zoho_id),
            "user_email": user_email[:255],
            "action":     action[:20],
            "reasoning":  (reasoning or "")[:5000] or None,
            "now":        datetime.now(timezone.utc),
        })
        await db.commit()
    except Exception as exc:
        logger.warning("Decision persist failed deal=%s: %s", deal_zoho_id, exc)
        try:
            await db.rollback()
        except Exception:
            pass


async def get_deal_decisions(db, deal_zoho_id: str) -> list[dict]:
    """Return decision history for a deal, newest first (up to 50 rows)."""
    if db is None or not deal_zoho_id:
        return []
    from sqlalchemy import text
    from services.deal_db import deal_internal_id
    try:
        result = await db.execute(text("""
            SELECT action, user_email, reasoning, decided_at
            FROM   decisions
            WHERE  deal_id = :deal_id
            ORDER  BY decided_at DESC
            LIMIT  50
        """), {"deal_id": deal_internal_id(deal_zoho_id)})
        rows = result.fetchall()
        return [
            {
                "action":     r[0],
                "user_email": r[1],
                "reasoning":  r[2],
                "decided_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Decision history failed deal=%s: %s", deal_zoho_id, exc)
        return []
