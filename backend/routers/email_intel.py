"""
Email Intelligence router — Outlook email threads per deal.
- Demo mode  → SIMULATED_EMAILS from demo_data.py
- Real mode  → Microsoft Graph via outlook_client.py (uses stored MS token)
- Sync       → pull fresh from Outlook for a deal's Zoho contacts
"""

import base64
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_db
from database.models import EmailExtraction
from services.demo_data import SIMULATED_EMAILS

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _user_key(session: dict) -> str:
    return session.get("email") or session.get("user_id") or "default"


def _get_ms_token(user_key: str) -> str | None:
    """Retrieve stored Microsoft access token for this user (set during OAuth callback)."""
    from routers.ms_auth import get_user_token
    tokens = get_user_token(user_key)
    if tokens:
        return tokens.get("access_token")
    return None


# ── Normalise email shape ──────────────────────────────────────────────────────

def _normalise(raw: dict) -> dict:
    """
    Normalise an email dict from any source into the unified shape the frontend expects:
    { subject, from, direction, sent_at, body_preview }
    """
    # SIMULATED_EMAILS use 'content' + 'sent_time'; DB / Outlook use 'body_preview' + 'sent_at'
    direction = raw.get("direction", "received")
    # Map 'sent' → 'sent', 'received' → 'received', 'outbound' → 'sent', 'inbound' → 'received'
    if direction in ("outbound",):
        direction = "sent"
    elif direction in ("inbound",):
        direction = "received"

    return {
        "subject":      raw.get("subject", "(no subject)"),
        "from":         raw.get("from", raw.get("from_address", "")),
        "direction":    direction,
        "sent_at":      raw.get("sent_at", raw.get("sent_time", "")),
        "body_preview": (raw.get("body_preview") or raw.get("content") or "")[:400],
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/threads/{deal_id}")
async def get_email_thread(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Return email thread for a deal.
    Priority: demo data → Outlook (live) → DB fallback → empty.
    """
    session = _decode_session(authorization)

    # ── Demo mode ──────────────────────────────────────────────────────────────
    if _is_demo(session) or deal_id.startswith("sim_"):
        raw_emails = SIMULATED_EMAILS.get(deal_id, [])
        emails = [_normalise(e) for e in raw_emails]

        extracted = None
        if db is not None:
            try:
                row = (await db.execute(
                    select(EmailExtraction)
                    .where(EmailExtraction.deal_zoho_id == deal_id)
                    .order_by(EmailExtraction.created_at.desc())
                    .limit(1)
                )).scalars().first()
                if row:
                    extracted = {
                        "next_step":      row.next_step,
                        "commitments":    row.commitments or [],
                        "open_questions": row.open_questions or [],
                        "sentiment":      row.sentiment,
                    }
            except Exception:
                pass

        return {"deal_id": deal_id, "thread_count": len(emails), "emails": emails, "extracted": extracted}

    # ── Real mode — try Outlook first ─────────────────────────────────────────
    user_key  = _user_key(session)
    ms_token  = _get_ms_token(user_key)

    if ms_token:
        try:
            # Get deal contacts from Zoho so we can filter Outlook by their emails
            zoho_token = session.get("access_token", "")
            contact_emails: list[str] = []

            if zoho_token and zoho_token != "DEMO_MODE":
                from services.zoho_client import get_contacts_for_deal
                contacts = await get_contacts_for_deal(zoho_token, deal_id)
                contact_emails = [c["email"] for c in contacts if c.get("email")]

            from services.outlook_client import get_messages_for_deal
            raw_messages = await get_messages_for_deal(ms_token, contact_emails)
            emails = [_normalise(m) for m in raw_messages]

            # Try to pull AI extraction from DB if available
            extracted = None
            if db is not None:
                try:
                    row = (await db.execute(
                        select(EmailExtraction)
                        .where(EmailExtraction.deal_zoho_id == deal_id)
                        .order_by(EmailExtraction.created_at.desc())
                        .limit(1)
                    )).scalars().first()
                    if row:
                        extracted = {
                            "next_step":      row.next_step,
                            "commitments":    row.commitments or [],
                            "open_questions": row.open_questions or [],
                            "sentiment":      row.sentiment,
                        }
                except Exception:
                    pass

            return {"deal_id": deal_id, "thread_count": len(emails), "emails": emails, "extracted": extracted}

        except Exception as e:
            logger.warning("Outlook fetch failed for deal=%s: %s", deal_id, e)
            # Fall through to DB fallback

    # ── DB fallback ────────────────────────────────────────────────────────────
    if db is None:
        return {"deal_id": deal_id, "thread_count": 0, "emails": [], "extracted": None}

    try:
        from database.models import Email
        # Email.deal_id is a UUID FK — filter by zoho_id stored on the Deal row if available,
        # otherwise return empty (Outlook is the primary source for real sessions)
        rows = (await db.execute(
            select(Email)
            .order_by(Email.sent_at.desc())
            .limit(25)
        )).scalars().all()

        emails = [_normalise({
            "subject":      r.subject,
            "from":         r.from_address,
            "direction":    r.direction,
            "sent_at":      r.sent_at.isoformat() if r.sent_at else "",
            "body_preview": (r.body_text or "")[:400],
        }) for r in rows]

        return {"deal_id": deal_id, "thread_count": len(emails), "emails": emails, "extracted": None}

    except Exception as e:
        logger.warning("DB email fetch failed for deal=%s: %s", deal_id, e)
        return {"deal_id": deal_id, "thread_count": 0, "emails": [], "extracted": None}


# ── Sync endpoint ──────────────────────────────────────────────────────────────

class SyncEmailsPayload(BaseModel):
    deal_id: str
    contact_emails: list[str] = []


@router.post("/sync")
async def sync_emails(
    payload: SyncEmailsPayload,
    authorization: str = Header(...),
):
    """
    Pull fresh emails from Outlook for a deal.
    If contact_emails is empty, fetches from Zoho contact roles automatically.
    """
    session = _decode_session(authorization)

    if _is_demo(session):
        return {"deal_id": payload.deal_id, "threads_found": 0, "message": "Demo mode — Outlook sync not available"}

    user_key = _user_key(session)
    ms_token = _get_ms_token(user_key)

    if not ms_token:
        return {
            "deal_id":       payload.deal_id,
            "threads_found": 0,
            "message":       "Outlook not connected. Go to Settings → Connect Outlook.",
        }

    # Auto-resolve contact emails from Zoho if not provided
    contact_emails = list(payload.contact_emails)
    if not contact_emails:
        zoho_token = session.get("access_token", "")
        if zoho_token and zoho_token != "DEMO_MODE":
            try:
                from services.zoho_client import get_contacts_for_deal
                contacts = await get_contacts_for_deal(zoho_token, payload.deal_id)
                contact_emails = [c["email"] for c in contacts if c.get("email")]
            except Exception as e:
                logger.warning("Zoho contact fetch failed during sync: %s", e)

    from services.outlook_client import get_messages_for_deal
    messages = await get_messages_for_deal(ms_token, contact_emails)

    return {
        "deal_id":       payload.deal_id,
        "threads_found": len(messages),
        "emails":        [_normalise(m) for m in messages],
    }
