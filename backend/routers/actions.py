"""
Actions router — today's prioritized action queue from the daily scan.

Async scan pattern:
  POST /actions/scan        → fires scan in background, returns {scan_id, status: "pending"}
  GET  /actions/scan/{id}   → poll for result: {status: "pending"|"completed"|"failed", actions: [...]}
  GET  /actions/today       → kept for backward compat (still works, just blocks)

Demo mode: returns DEMO_TODAY_ACTIONS when Authorization: Bearer DEMO_MODE.
"""

import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_db
from services.demo_data import DEMO_TODAY_ACTIONS
from services.daily_scanner import run_morning_scan

router = APIRouter()

_dismissed: set[str] = set()
_snoozed: set[str] = set()

# In-memory scan result store: scan_id → {status, actions, started_at, error}
_scan_results: dict[str, dict[str, Any]] = {}
_MAX_SCAN_AGE_SECONDS = 300  # expire entries after 5 min


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


def _prune_old_scans() -> None:
    now = datetime.now(timezone.utc).timestamp()
    stale = [k for k, v in _scan_results.items()
             if now - v.get("started_at", now) > _MAX_SCAN_AGE_SECONDS]
    for k in stale:
        del _scan_results[k]


async def _run_scan_background(scan_id: str, session: dict, db: AsyncSession | None) -> None:
    """Background coroutine — fetches deals and runs the morning scan."""
    try:
        from services.zoho_client import fetch_deals, map_zoho_deal
        try:
            raw_deals = await fetch_deals(session.get("access_token", ""), per_page=200)
            deals = [map_zoho_deal(r) for r in raw_deals]
        except Exception:
            deals = []

        actions = await run_morning_scan(deals, db, generate_drafts=False, session=session)
        filtered = [a for a in actions if a.get("deal_id") not in _dismissed]

        _scan_results[scan_id] = {
            **_scan_results[scan_id],
            "status": "completed",
            "actions": filtered,
            "total": len(filtered),
            "source": "live",
        }
    except Exception as exc:
        _scan_results[scan_id] = {
            **_scan_results[scan_id],
            "status": "failed",
            "error": str(exc),
            "actions": [],
            "total": 0,
        }


@router.post("/scan")
async def start_scan(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Kick off an async morning scan. Returns immediately with a scan_id.
    Poll GET /actions/scan/{scan_id} for results.
    Demo mode resolves instantly.
    """
    session = _decode_session(authorization)
    _prune_old_scans()

    scan_id = str(uuid.uuid4())

    if _is_demo(session):
        actions = [
            a for a in DEMO_TODAY_ACTIONS
            if a["id"] not in _dismissed and a["id"] not in _snoozed
        ]
        _scan_results[scan_id] = {
            "status": "completed",
            "actions": actions,
            "total": len(actions),
            "source": "demo",
            "started_at": datetime.now(timezone.utc).timestamp(),
        }
        return {"scan_id": scan_id, "status": "completed"}

    _scan_results[scan_id] = {
        "status": "pending",
        "started_at": datetime.now(timezone.utc).timestamp(),
    }

    # Fire and forget — does not block the response
    asyncio.create_task(_run_scan_background(scan_id, session, db))

    return {"scan_id": scan_id, "status": "pending"}


@router.get("/scan/{scan_id}")
async def get_scan_result(scan_id: str, authorization: str = Header(...)):
    """Poll scan status. Returns {status, actions, total, source} once completed."""
    _decode_session(authorization)

    result = _scan_results.get(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found or expired")

    return result


@router.get("/today")
async def get_today_actions(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """Synchronous fallback — kept for backward compatibility."""
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

    try:
        actions = await run_morning_scan(deals, db, generate_drafts=False, session=session)
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
