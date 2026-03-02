"""
Email Intelligence router — AI-summarized email threads per deal.
Named email_intel to avoid conflict with any existing email.py router.
"""

import base64
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_db
from database.models import Email, EmailExtraction
from services.demo_data import SIMULATED_EMAILS

router = APIRouter()


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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/threads/{deal_id}")
async def get_email_thread(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Return AI-summarized email thread for a deal."""
    session = _decode_session(authorization)
    if _is_demo(session):
        emails = SIMULATED_EMAILS.get(deal_id, [])
        latest_extraction = None
        if db is not None:
            try:
                extraction_result = await db.execute(
                    select(EmailExtraction)
                    .where(EmailExtraction.deal_zoho_id == deal_id)
                    .order_by(EmailExtraction.created_at.desc())
                    .limit(1)
                )
                latest_extraction = extraction_result.scalars().first()
            except Exception:
                pass
        return {
            "deal_id": deal_id,
            "thread_count": len(emails),
            "emails": emails,
            "extracted": {
                "next_step": latest_extraction.next_step if latest_extraction else None,
                "commitments": latest_extraction.commitments if latest_extraction else [],
                "open_questions": latest_extraction.open_questions if latest_extraction else [],
                "sentiment": latest_extraction.sentiment if latest_extraction else None,
            } if latest_extraction else None,
        }

    if db is None:
        return {"deal_id": deal_id, "thread_count": 0, "emails": []}

    try:
        rows = await db.execute(
            select(Email)
            .order_by(Email.sent_at.desc())
            .limit(20)
        )
        emails = rows.scalars().all()
    except Exception:
        return {"deal_id": deal_id, "thread_count": 0, "emails": []}

    return {
        "deal_id": deal_id,
        "thread_count": len(emails),
        "emails": [
            {
                "subject": e.subject,
                "from": e.from_address,
                "direction": e.direction,
                "sent_at": e.sent_at.isoformat(),
                "body_preview": (e.body_text or "")[:300],
            }
            for e in emails
        ],
    }


class SyncEmailsPayload(BaseModel):
    deal_id: str
    contact_emails: list[str] = []


@router.post("/sync")
async def sync_emails(
    payload: SyncEmailsPayload,
    authorization: str = Header(...),
):
    """Manual trigger: sync emails for a deal from Gmail."""
    session = _decode_session(authorization)
    access_token = session.get("access_token")
    if not access_token or access_token == "DEMO_MODE":
        return {"deal_id": payload.deal_id, "threads_found": 0, "message": "Gmail not connected"}

    from services.gmail_client import sync_emails_for_deal
    threads = await sync_emails_for_deal(access_token, payload.deal_id, payload.contact_emails)
    return {"deal_id": payload.deal_id, "threads_found": len(threads), "threads": threads}


class ComposeEmailPayload(BaseModel):
    deal_id: str
    tone_override: str | None = None
    additional_context: str | None = None


@router.post("/compose")
async def compose_email(
    payload: ComposeEmailPayload,
    authorization: str = Header(...),
):
    """Draft a follow-up email for a deal — wraps existing EmailGenerator."""
    _decode_session(authorization)
    # Use the /ask/deal/follow-up-email endpoint for richer email generation.
    raise HTTPException(
        status_code=307,
        detail="Use POST /ask/deal/follow-up-email for email composition.",
        headers={"Location": f"/ask/deal/follow-up-email"},
    )
