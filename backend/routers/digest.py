"""
Daily Digest Router
===================
GET  /digest/today            — today's digest for the authed rep
POST /digest/complete/{id}    — mark a task done / undone
GET  /digest/preferences      — get user digest preferences
PUT  /digest/preferences      — update user digest preferences
POST /digest/send-email       — manually trigger the digest email
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from services.daily_digest_service import build_digest
from services.demo_data import SIMULATED_DEALS

logger = logging.getLogger(__name__)
router = APIRouter()

CLOSED_STAGES = {"Closed Won", "Closed Lost", "Lost", "Won", "Dead"}


# --------------------------------------------------------------------------- #
# Auth helpers
# --------------------------------------------------------------------------- #

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _user_key(session: dict) -> str:
    return session.get("user_id") or session.get("email") or "zoho_user"


def _days_since(dt_str: Optional[str]) -> Optional[int]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Pydantic schemas
# --------------------------------------------------------------------------- #

class PreferencesUpdate(BaseModel):
    digest_time: str | None = None
    digest_email_enabled: bool | None = None
    digest_language: str | None = None
    email_address: str | None = None
    timezone: str | None = None


# --------------------------------------------------------------------------- #
# Deal preparation — no extra API calls, just filter + score
# --------------------------------------------------------------------------- #

def _prepare_deals(raw_deals: list[dict]) -> list[dict]:
    """
    Filter and score deals using only the data already in the bulk Zoho fetch.
    No extra API calls. Returns deals touched in the last 60 days, non-closed.
    """
    from services.health_scorer import score_deal_from_zoho

    active: list[dict] = []
    for d in raw_deals:
        if (d.get("stage") or "") in CLOSED_STAGES:
            continue
        days = _days_since(d.get("last_activity_time")) or _days_since(d.get("modified_time"))
        if days is not None and days > 60:
            continue
        try:
            result = score_deal_from_zoho(d)
            d["health_score"] = result.total_score
            d["health_label"] = result.health_label
        except Exception:
            d.setdefault("health_score", 50)
            d.setdefault("health_label", "at_risk")
        active.append(d)

    # Safety fallback: if every deal is older than 60 days, return all non-closed
    if not active:
        for d in raw_deals:
            if (d.get("stage") or "") in CLOSED_STAGES:
                continue
            try:
                result = score_deal_from_zoho(d)
                d["health_score"] = result.total_score
                d["health_label"] = result.health_label
            except Exception:
                d.setdefault("health_score", 50)
                d.setdefault("health_label", "at_risk")
            active.append(d)

    return active


# --------------------------------------------------------------------------- #
# GET /digest/today
# --------------------------------------------------------------------------- #

@router.get("/today")
async def get_today_digest(authorization: str = Header(...)):
    session = _decode_session(authorization)
    simulated = _is_demo(session)
    user_key = _user_key(session)
    today = date.today().isoformat()

    # Load + prepare deals
    if simulated:
        deals = _prepare_deals([dict(d) for d in SIMULATED_DEALS])
    else:
        try:
            from routers.deals import _fetch_all_zoho_deals
            raw = await asyncio.wait_for(
                _fetch_all_zoho_deals(session["access_token"]),
                timeout=12.0,
            )
            deals = _prepare_deals(raw)
        except asyncio.TimeoutError:
            logger.warning("digest: Zoho fetch timed out — falling back to demo data")
            deals = _prepare_deals([dict(d) for d in SIMULATED_DEALS])
            simulated = True
        except Exception as e:
            logger.warning("digest: Zoho fetch failed: %s — falling back to demo data", e)
            deals = _prepare_deals([dict(d) for d in SIMULATED_DEALS])
            simulated = True

    # Load persisted completion state for today from DB
    existing_tasks: list[dict] = []
    try:
        from database.connection import get_db
        from database.models import DigestTask
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                break
            rows = (await db.execute(
                select(DigestTask)
                .where(DigestTask.user_key == user_key, DigestTask.date == today)
                .order_by(DigestTask.sort_order)
            )).scalars().all()
            existing_tasks = [
                {
                    "id": r.id,
                    "deal_id": r.deal_id,
                    "task_type": r.task_type,
                    "is_completed": r.is_completed,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in rows
            ]
            break
    except Exception as e:
        logger.debug("DB not available for digest tasks: %s", e)

    digest = build_digest(deals, existing_tasks or None)

    # Persist freshly-generated tasks (only on first load of the day)
    if not existing_tasks:
        try:
            from database.connection import get_db
            from database.models import DigestTask
            async for db in get_db():
                if db is None:
                    break
                for task in digest["tasks"]:
                    db.add(DigestTask(
                        id=task["id"],
                        user_key=user_key,
                        date=today,
                        deal_id=task["deal_id"],
                        deal_name=task["deal_name"],
                        company=task.get("company") or "",
                        stage=task.get("stage") or "",
                        amount=task.get("amount"),
                        task_type=task["task_type"],
                        task_text=task["task_text"],
                        reason=task.get("reason") or "",
                        is_completed=False,
                        sort_order=task["sort_order"],
                    ))
                await db.commit()
                break
        except Exception as e:
            logger.debug("Could not persist digest tasks: %s", e)

    digest["simulated"] = simulated
    return digest


# --------------------------------------------------------------------------- #
# POST /digest/complete/{task_id}
# --------------------------------------------------------------------------- #

@router.post("/complete/{task_id}")
async def complete_task(task_id: str, authorization: str = Header(...)):
    session = _decode_session(authorization)
    user_key = _user_key(session)

    try:
        from database.connection import get_db
        from database.models import DigestTask
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                return {"ok": True, "persisted": False}
            task = (await db.execute(
                select(DigestTask).where(
                    DigestTask.id == task_id,
                    DigestTask.user_key == user_key,
                )
            )).scalar_one_or_none()
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
            task.is_completed = not task.is_completed
            task.completed_at = datetime.now(timezone.utc) if task.is_completed else None
            await db.commit()
            return {"ok": True, "is_completed": task.is_completed, "persisted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("DB error toggling task %s: %s", task_id, e)
        return {"ok": True, "persisted": False}


# --------------------------------------------------------------------------- #
# GET /digest/preferences
# --------------------------------------------------------------------------- #

@router.get("/preferences")
async def get_preferences(authorization: str = Header(...)):
    session = _decode_session(authorization)
    user_key = _user_key(session)

    try:
        from database.connection import get_db
        from database.models import UserPreferences
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                break
            prefs = (await db.execute(
                select(UserPreferences).where(UserPreferences.user_key == user_key)
            )).scalar_one_or_none()
            if prefs:
                return {
                    "digest_time": prefs.digest_time,
                    "digest_email_enabled": prefs.digest_email_enabled,
                    "digest_language": prefs.digest_language,
                    "email_address": prefs.email_address,
                    "timezone": prefs.timezone,
                }
            break
    except Exception as e:
        logger.debug("DB not available for preferences: %s", e)

    return {
        "digest_time": "09:00",
        "digest_email_enabled": True,
        "digest_language": "en",
        "email_address": None,
        "timezone": "UTC",
    }


# --------------------------------------------------------------------------- #
# PUT /digest/preferences
# --------------------------------------------------------------------------- #

@router.put("/preferences")
async def update_preferences(body: PreferencesUpdate, authorization: str = Header(...)):
    session = _decode_session(authorization)
    user_key = _user_key(session)

    try:
        from database.connection import get_db
        from database.models import UserPreferences
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                return {"ok": True, "persisted": False}
            prefs = (await db.execute(
                select(UserPreferences).where(UserPreferences.user_key == user_key)
            )).scalar_one_or_none()
            if not prefs:
                prefs = UserPreferences(user_key=user_key)
                db.add(prefs)
            if body.digest_time is not None:
                prefs.digest_time = body.digest_time
            if body.digest_email_enabled is not None:
                prefs.digest_email_enabled = body.digest_email_enabled
            if body.digest_language is not None:
                prefs.digest_language = body.digest_language
            if body.email_address is not None:
                prefs.email_address = body.email_address
            if body.timezone is not None:
                prefs.timezone = body.timezone
            await db.commit()
            return {"ok": True, "persisted": True}
    except Exception as e:
        logger.warning("Could not save preferences for %s: %s", user_key, e)
        return {"ok": True, "persisted": False}


# --------------------------------------------------------------------------- #
# POST /digest/send-email
# --------------------------------------------------------------------------- #

@router.post("/send-email")
async def send_digest_email_now(authorization: str = Header(...)):
    session = _decode_session(authorization)
    user_key = _user_key(session)

    to_email: str | None = None
    try:
        from database.connection import get_db
        from database.models import UserPreferences
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                break
            prefs = (await db.execute(
                select(UserPreferences).where(UserPreferences.user_key == user_key)
            )).scalar_one_or_none()
            if prefs:
                to_email = prefs.email_address
            break
    except Exception:
        pass

    to_email = to_email or session.get("email")
    if not to_email:
        raise HTTPException(
            status_code=400,
            detail="No email address configured. Set it in Digest preferences.",
        )

    digest_data = await get_today_digest(authorization)
    from services.digest_email import send_digest_email
    ok = await send_digest_email(to_email, digest_data, rep_name=session.get("name") or "")
    return {"ok": ok, "sent_to": to_email if ok else None}


# --------------------------------------------------------------------------- #
# GET /digest/tasks/{task_id}/execution
# --------------------------------------------------------------------------- #

@router.get("/tasks/{task_id}/execution")
async def get_task_execution(
    task_id: str,
    authorization: str = Header(...),
    # Optional fallback context — used when task isn't in DB yet
    deal_name: str | None = None,
    company: str | None = None,
    stage: str | None = None,
    task_type: str | None = None,
    task_text: str | None = None,
):
    """
    Lazily generate execution payload (AI draft, call script, etc.) for one task.
    Called when a rep expands a task card on the digest page.
    Accepts optional query params as fallback context if task isn't in DB.
    """
    session = _decode_session(authorization)
    user_key = _user_key(session)
    simulated = _is_demo(session)

    # Load task from DB to get full context
    task_data: dict | None = None
    try:
        from database.connection import get_db
        from database.models import DigestTask
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                break
            row = (await db.execute(
                select(DigestTask).where(
                    DigestTask.id == task_id,
                    DigestTask.user_key == user_key,
                )
            )).scalar_one_or_none()
            if row:
                task_data = {
                    "id": row.id,
                    "deal_id": row.deal_id,
                    "deal_name": row.deal_name,
                    "company": row.company or "",
                    "stage": row.stage or "",
                    "amount": float(row.amount) if row.amount else None,
                    "amount_fmt": "",
                    "task_type": row.task_type,
                    "task_text": row.task_text,
                    "reason": row.reason or "",
                }
                # Format amount
                if row.amount:
                    v = float(row.amount)
                    if v >= 1_000_000:
                        task_data["amount_fmt"] = f"${v/1_000_000:.1f}M"
                    elif v >= 1_000:
                        task_data["amount_fmt"] = f"${round(v/1_000)}K"
                    else:
                        task_data["amount_fmt"] = f"${round(v)}"
            break
    except Exception as e:
        logger.debug("get_task_execution: DB load failed: %s", e)

    # If DB unavailable or task not persisted yet, build a minimal context from
    # the query params the frontend can supply, then fall back to a generic stub.
    # Never return 404 — execution content can still be generated without DB data.
    if not task_data:
        task_data = {
            "id": task_id,
            "deal_id": task_id,
            "deal_name": deal_name or "Unknown deal",
            "company": company or "",
            "stage": stage or "",
            "amount": None,
            "amount_fmt": "",
            "task_type": task_type or "email",
            "task_text": task_text or "Follow up on this deal",
            "reason": "",
        }

    # Check if Outlook is connected for this user
    outlook_connected = False
    if not simulated:
        try:
            from routers.ms_auth import get_user_token
            tok = await get_user_token(user_key)
            outlook_connected = bool(tok and tok.get("access_token"))
        except Exception:
            pass

    from services.task_execution_service import generate_execution
    execution = await generate_execution(task_data, outlook_connected=outlook_connected)

    return {"task_id": task_id, "execution": execution}


# --------------------------------------------------------------------------- #
# POST /digest/tasks/{task_id}/execute
# --------------------------------------------------------------------------- #

class ExecuteTaskBody(BaseModel):
    action: str          # "send_email" | "schedule_meeting" | "log_call" | "mark_sent" | "send_resources"
    # Email / resources
    subject: str | None = None
    body_html: str | None = None
    to: list[dict] | None = None
    cc: list[dict] | None = None
    # Meeting
    start_iso: str | None = None
    duration_minutes: int | None = None
    attendees: list[dict] | None = None
    # Call
    outcome: str | None = None
    notes: str | None = None


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str, body: ExecuteTaskBody, authorization: str = Header(...)):
    """
    Execute a task action: send email, schedule meeting, log call, etc.
    Marks the task as complete on success and optionally syncs to Zoho CRM.
    """
    session = _decode_session(authorization)
    user_key = _user_key(session)
    simulated = _is_demo(session)

    # Demo mode — just mark complete, no actual send
    if simulated:
        return {"ok": True, "action": body.action, "simulated": True}

    result: dict = {"ok": False, "action": body.action}

    # Get Outlook token
    outlook_token: str | None = None
    try:
        from routers.ms_auth import get_user_token
        tok = await get_user_token(user_key)
        outlook_token = tok.get("access_token") if tok else None
    except Exception:
        pass

    # Load task for deal_id and CRM context
    deal_id: str = ""
    try:
        from database.connection import get_db
        from database.models import DigestTask
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                break
            row = (await db.execute(
                select(DigestTask).where(
                    DigestTask.id == task_id,
                    DigestTask.user_key == user_key,
                )
            )).scalar_one_or_none()
            if row:
                deal_id = row.deal_id
            break
    except Exception as e:
        logger.debug("execute_task: DB load failed: %s", e)

    # --- Perform the action ---

    if body.action == "send_email" or body.action == "send_resources":
        if not outlook_token:
            raise HTTPException(status_code=400, detail="Outlook not connected — cannot send email")
        from services.outlook_client import send_email
        send_result = await send_email(
            access_token=outlook_token,
            to=body.to or [],
            cc=body.cc or [],
            subject=body.subject or "(no subject)",
            body_html=body.body_html or "",
        )
        result.update(send_result)
        if send_result.get("success"):
            result["ok"] = True
            # Log to Zoho CRM
            if deal_id and session.get("access_token"):
                try:
                    from services.zoho_writer import create_meeting_note
                    await create_meeting_note(
                        deal_id=deal_id,
                        token=session["access_token"],
                        note_content=f"[DealIQ Digest] Email sent: {body.subject}",
                    )
                except Exception as e:
                    logger.debug("execute_task: Zoho note failed: %s", e)

    elif body.action == "schedule_meeting":
        if not outlook_token:
            raise HTTPException(status_code=400, detail="Outlook not connected — cannot create calendar event")
        from services.outlook_client import create_calendar_event
        cal_result = await create_calendar_event(
            access_token=outlook_token,
            subject=body.subject or "Vervotech — next steps",
            attendees=body.attendees or [],
            start_iso=body.start_iso or "",
            duration_minutes=body.duration_minutes or 30,
            body_html=body.body_html or "",
        )
        result.update(cal_result)
        if cal_result.get("success"):
            result["ok"] = True

    elif body.action in ("log_call", "mark_sent"):
        # These are manual confirmations — just mark complete
        result["ok"] = True
        if body.notes and deal_id and session.get("access_token") and not simulated:
            try:
                from services.zoho_writer import create_meeting_note
                await create_meeting_note(
                    deal_id=deal_id,
                    token=session["access_token"],
                    note_content=f"[DealIQ Digest] {body.action}: {body.notes}",
                )
            except Exception as e:
                logger.debug("execute_task: Zoho note for %s failed: %s", body.action, e)

    else:
        result["ok"] = True  # Unknown action — optimistically succeed

    # Mark task complete in DB if action succeeded
    if result["ok"]:
        try:
            from database.connection import get_db
            from database.models import DigestTask
            from sqlalchemy import select
            async for db in get_db():
                if db is None:
                    break
                row = (await db.execute(
                    select(DigestTask).where(
                        DigestTask.id == task_id,
                        DigestTask.user_key == user_key,
                    )
                )).scalar_one_or_none()
                if row:
                    row.is_completed = True
                    row.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                break
        except Exception as e:
            logger.debug("execute_task: DB complete failed: %s", e)

    return result


# --------------------------------------------------------------------------- #
# POST /digest/tasks/{task_id}/skip
# --------------------------------------------------------------------------- #

class SkipTaskBody(BaseModel):
    reason: str | None = None


@router.post("/tasks/{task_id}/skip")
async def skip_task(task_id: str, body: SkipTaskBody, authorization: str = Header(...)):
    """Mark a task as skipped (treated as complete with a skip note)."""
    session = _decode_session(authorization)
    user_key = _user_key(session)

    try:
        from database.connection import get_db
        from database.models import DigestTask
        from sqlalchemy import select
        async for db in get_db():
            if db is None:
                return {"ok": True, "persisted": False}
            row = (await db.execute(
                select(DigestTask).where(
                    DigestTask.id == task_id,
                    DigestTask.user_key == user_key,
                )
            )).scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail="Task not found")
            row.is_completed = True
            row.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"ok": True, "persisted": True, "skipped": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("skip_task: DB failed: %s", e)
        return {"ok": True, "persisted": False}
