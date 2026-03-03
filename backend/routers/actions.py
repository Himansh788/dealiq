"""
Actions router — today's prioritized action queue from the daily scan.
Demo mode: returns DEMO_TODAY_ACTIONS when Authorization: Bearer DEMO_MODE.
"""

import base64
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from services.demo_data import DEMO_TODAY_ACTIONS
from services.daily_scanner import run_morning_scan

router = APIRouter()

_dismissed: set[str] = set()
_snoozed: set[str] = set()


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


@router.get("/today")
async def get_today_actions(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Return today's prioritized action queue for the authenticated rep."""
    session = _decode_session(authorization)

    if _is_demo(session):
        actions = [
            a for a in DEMO_TODAY_ACTIONS
            if a["id"] not in _dismissed and a["id"] not in _snoozed
        ]
        return {"actions": actions, "total": len(actions), "source": "demo"}

    from services.zoho_client import fetch_deals, map_zoho_deal
    try:
        raw_deals = await fetch_deals(session.get("access_token", ""), per_page=200)
        deals = [map_zoho_deal(r) for r in raw_deals]
    except Exception:
        deals = []

    if db is None:
        return {"actions": [], "total": 0, "source": "live", "message": "Database not available"}

    try:
        actions = await run_morning_scan(deals, db, generate_drafts=False)
    except Exception:
        actions = []
    filtered = [a for a in actions if a.get("deal_id") not in _dismissed]
    return {"actions": filtered, "total": len(filtered), "source": "live"}


@router.post("/{action_id}/execute")
async def execute_action(
    action_id: str,
    payload: dict,
    authorization: str = Header(...),
):
    _decode_session(authorization)
    _dismissed.add(action_id)
    return {"action_id": action_id, "status": "executed"}


@router.post("/{action_id}/dismiss")
async def dismiss_action(
    action_id: str,
    authorization: str = Header(...),
):
    _decode_session(authorization)
    _dismissed.add(action_id)
    return {"action_id": action_id, "status": "dismissed"}


@router.post("/{action_id}/snooze")
async def snooze_action(
    action_id: str,
    authorization: str = Header(...),
):
    _decode_session(authorization)
    _snoozed.add(action_id)
    return {"action_id": action_id, "status": "snoozed"}
