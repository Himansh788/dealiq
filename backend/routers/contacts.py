"""
Contact Intelligence Router
============================
GET  /contacts/{deal_id}              — Zoho contacts + Outlook personas
POST /contacts/{deal_id}/confirm      — Rep confirms or rejects a persona
DELETE /contacts/{deal_id}/persona/{email} — Remove a persona record
"""

import json
import base64
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "display_name": "Zoho User", "email": "", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


# ── Schemas ────────────────────────────────────────────────────────────────────

class ConfirmPersonaRequest(BaseModel):
    email: str
    status: str          # confirmed | rejected
    name: Optional[str] = None
    role: Optional[str] = None


# ── Demo data ──────────────────────────────────────────────────────────────────

def _demo_contacts(deal_id: str) -> dict:
    return {
        "zoho_contacts": [
            {"email": "sarah.chen@techcorp.com", "name": "Sarah Chen", "role": "Economic Buyer", "source": "zoho", "status": "confirmed"},
            {"email": "james.liu@techcorp.com",  "name": "James Liu",  "role": "Champion",        "source": "zoho", "status": "confirmed"},
        ],
        "potential_personas": [
            {
                "email": "mike.torres@techcorp.com",
                "display_name": "Mike Torres",
                "last_seen_at": "2026-03-08T14:22:00Z",
                "email_count": 3,
                "source": "outlook_discovered",
                "status": "pending",
            },
            {
                "email": "legal@techcorp.com",
                "display_name": "",
                "last_seen_at": "2026-03-06T09:10:00Z",
                "email_count": 1,
                "source": "outlook_discovered",
                "status": "pending",
            },
        ],
        "confirmed_personas": [],
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/contacts/{deal_id}")
async def get_deal_contacts(
    deal_id: str,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)

    if _is_demo(session):
        return _demo_contacts(deal_id)

    from database.connection import AsyncSessionLocal
    from services.contact_intelligence import get_deal_contacts as _get

    zoho_token = session.get("access_token", "")
    user_key = session.get("email") or session.get("user_id") or "default"

    # Try with DB; degrade gracefully
    try:
        async with AsyncSessionLocal() as db:
            return await _get(deal_id, zoho_token, user_key, db)
    except Exception:
        return await _get(deal_id, zoho_token, user_key, db=None)


@router.post("/contacts/{deal_id}/confirm")
async def confirm_persona(
    deal_id: str,
    body: ConfirmPersonaRequest,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)

    if _is_demo(session):
        return {"success": True, "email": body.email, "status": body.status}

    if body.status not in ("confirmed", "rejected"):
        raise HTTPException(status_code=400, detail="status must be 'confirmed' or 'rejected'")

    confirmed_by = session.get("email") or session.get("user_id") or "unknown"

    try:
        from database.connection import AsyncSessionLocal
        from services.contact_intelligence import confirm_persona as _confirm
        async with AsyncSessionLocal() as db:
            await _confirm(deal_id, body.email, body.status, confirmed_by, db)
        return {"success": True, "email": body.email, "status": body.status}
    except Exception as e:
        logger.error("confirm_persona failed deal=%s email=%s: %s", deal_id, body.email, e)
        raise HTTPException(status_code=500, detail="Failed to update persona status")


@router.delete("/contacts/{deal_id}/persona/{email:path}")
async def delete_persona(
    deal_id: str,
    email: str,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)

    if _is_demo(session):
        return {"deleted": True}

    try:
        from database.connection import AsyncSessionLocal
        from database.models import DealPersona
        from sqlalchemy import delete
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(DealPersona).where(
                    DealPersona.deal_zoho_id == deal_id,
                    DealPersona.email == email.lower(),
                )
            )
            await db.commit()
        return {"deleted": True}
    except Exception as e:
        logger.error("delete_persona failed deal=%s email=%s: %s", deal_id, email, e)
        raise HTTPException(status_code=500, detail="Failed to delete persona")
