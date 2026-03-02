"""
Meeting router — post-call form submission, pending CRM updates, meeting history.
"""

import uuid
import base64
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from database.connection import get_db
from database.models import MeetingLog, PendingCrmUpdate
from services.demo_data import DEMO_PENDING_UPDATES, DEMO_MEETING_HISTORY, SIMULATED_DEALS
from services.post_meeting_service import process_post_meeting

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


# ── Schemas ───────────────────────────────────────────────────────────────────

class PostMeetingPayload(BaseModel):
    deal_id: str
    sentiment: str  # great / ok / concern
    topics_confirmed: list[str] = []
    quick_notes: str | None = None
    duration_minutes: int | None = None
    attendees: list[dict[str, Any]] = []
    calendar_event_id: str | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/prep/{deal_id}")
async def get_meeting_prep(
    deal_id: str,
    authorization: str = Header(...),
):
    """AI meeting prep brief — returns deal context and suggested talking points."""
    session = _decode_session(authorization)
    if _is_demo(session):
        deal = next((d for d in SIMULATED_DEALS if d["id"] == deal_id), None)
        if not deal:
            raise HTTPException(status_code=404, detail="Demo deal not found")
        return {
            "deal_id": deal_id,
            "deal_name": deal.get("name"),
            "brief": {
                "opening_hook": f"Follow up on the contract sent to {deal.get('account_name')} 3 days ago.",
                "key_risks": ["Legal review delay", "Multi-year pricing objection"],
                "suggested_questions": [
                    "Has your legal team completed the review?",
                    "What's the timeline for procurement sign-off?",
                ],
                "competitor_intel": "Prospect has mentioned competitor pricing twice.",
                "recommended_next_step": "Confirm contract signature by April 7 pricing deadline.",
            },
        }
    return {"deal_id": deal_id, "brief": {}, "message": "Connect Zoho for live meeting prep"}


@router.post("/ended")
async def submit_post_meeting(
    payload: PostMeetingPayload,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Submit post-call form, trigger AI processing, update CRM."""
    session = _decode_session(authorization)

    if _is_demo(session):
        deal = next((d for d in SIMULATED_DEALS if d["id"] == payload.deal_id), None) or {
            "id": payload.deal_id, "name": "Demo Deal", "stage": "Unknown", "amount": 0
        }
        access_token = None
    else:
        deal = {"id": payload.deal_id, "name": "Deal", "stage": "", "amount": 0}
        access_token = session.get("access_token")

    if db is None:
        return {
            "meeting_log_id": None,
            "ai_summary": "Meeting logged (DB not available — AI processing skipped).",
            "action_items": [],
            "crm_updates_made": [],
            "pending_updates_queued": 0,
            "note_created": False,
            "tasks_created": 0,
            "follow_up_email_draft": None,
        }

    meeting_log = MeetingLog(
        id=uuid.uuid4(),
        calendar_event_id=payload.calendar_event_id,
        deal_id=payload.deal_id,
        attendees=payload.attendees,
        duration_minutes=payload.duration_minutes,
        quick_notes=payload.quick_notes,
        sentiment=payload.sentiment,
        topics_confirmed=payload.topics_confirmed,
        created_at=datetime.now(timezone.utc),
    )

    return await process_post_meeting(
        meeting_log=meeting_log,
        deal=deal,
        access_token=access_token,
        db=db,
    )


@router.get("/pending-updates")
async def get_pending_updates(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """List PendingCrmUpdate rows awaiting rep approval."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"updates": DEMO_PENDING_UPDATES, "total": len(DEMO_PENDING_UPDATES)}

    if db is None:
        return {"updates": [], "total": 0}

    try:
        rows = await db.execute(
            select(PendingCrmUpdate)
            .where(PendingCrmUpdate.status == "pending")
            .order_by(PendingCrmUpdate.created_at.desc())
        )
        updates = rows.scalars().all()
    except Exception:
        return {"updates": [], "total": 0}

    return {
        "updates": [
            {
                "id": str(u.id),
                "deal_id": u.deal_id,
                "field_name": u.field_name,
                "old_value": u.old_value,
                "new_value": u.new_value,
                "confidence": u.confidence,
                "source": u.source,
                "created_at": u.created_at.isoformat(),
            }
            for u in updates
        ],
        "total": len(updates),
    }


@router.post("/approve-update/{update_id}")
async def approve_crm_update(
    update_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Rep approves a pending CRM update — applies it to Zoho."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"update_id": update_id, "status": "approved", "message": "Demo mode — no Zoho write"}

    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db.get(PendingCrmUpdate, uuid.UUID(update_id))
    if not row:
        raise HTTPException(status_code=404, detail="Pending update not found")

    access_token = session.get("access_token")
    if access_token:
        from services.zoho_writer import apply_pending_update
        try:
            await apply_pending_update(access_token, row)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Zoho write failed: {e}")

    await db.execute(
        update(PendingCrmUpdate)
        .where(PendingCrmUpdate.id == row.id)
        .values(status="approved")
    )
    await db.commit()
    return {"update_id": update_id, "status": "approved"}


@router.post("/reject-update/{update_id}")
async def reject_crm_update(
    update_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Rep rejects a pending CRM update."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"update_id": update_id, "status": "rejected"}

    if db is None:
        raise HTTPException(status_code=503, detail="Database not available")

    row = await db.get(PendingCrmUpdate, uuid.UUID(update_id))
    if not row:
        raise HTTPException(status_code=404, detail="Pending update not found")

    await db.execute(
        update(PendingCrmUpdate)
        .where(PendingCrmUpdate.id == row.id)
        .values(status="rejected")
    )
    await db.commit()
    return {"update_id": update_id, "status": "rejected"}


@router.get("/history/{deal_id}")
async def get_meeting_history(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Recent MeetingLog entries for a deal."""
    session = _decode_session(authorization)
    if _is_demo(session):
        history = DEMO_MEETING_HISTORY.get(deal_id, [])
        return {"deal_id": deal_id, "meetings": history, "total": len(history)}

    if db is None:
        return {"deal_id": deal_id, "meetings": [], "total": 0}

    try:
        rows = await db.execute(
            select(MeetingLog)
            .where(MeetingLog.deal_id == deal_id)
            .order_by(MeetingLog.created_at.desc())
            .limit(10)
        )
        meetings = rows.scalars().all()
    except Exception:
        return {"deal_id": deal_id, "meetings": [], "total": 0}
    return {
        "deal_id": deal_id,
        "meetings": [
            {
                "id": str(m.id),
                "sentiment": m.sentiment,
                "ai_summary": m.ai_summary,
                "action_items": m.action_items,
                "topics_confirmed": m.topics_confirmed,
                "duration_minutes": m.duration_minutes,
                "created_at": m.created_at.isoformat(),
            }
            for m in meetings
        ],
        "total": len(meetings),
    }
