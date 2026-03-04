import asyncio
import base64
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Auth helpers (same pattern as activities.py) ──────────────────────────────

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


# ── Demo warning fixtures ─────────────────────────────────────────────────────
#
# Mapped by sim_ID. Covers all 6 demo deals with a realistic spread:
#   sim_001 Acme Corp        → healthy, no warnings
#   sim_002 TechStart (TechNova) → NO_NEXT_STEP only
#   sim_003 GlobalRetail     → STAGE_STUCK (28d) + COMMIT_RISK
#   sim_004 FinanceFlow      → GONE_SILENT (14d) + NO_NEXT_STEP + SINGLE_THREADED
#   sim_005 HealthTech (Innovate Inc) → SINGLE_THREADED + GONE_SILENT (7d)
#   sim_006 LogiCo (StartupX) → STAGE_STUCK (22d)

DEMO_WARNINGS: dict[str, dict] = {
    "sim_001": {
        "warnings": [],
        "warning_count": 0,
        "has_critical": False,
    },
    "sim_002": {
        "warnings": [
            {
                "warning_id": "NO_NEXT_STEP",
                "title": "No Next Step",
                "description": "No scheduled meeting, task, or follow-up defined for this deal.",
                "severity": "high",
                "suggested_action": "Schedule a follow-up call or send a check-in email with a clear ask.",
            }
        ],
        "warning_count": 1,
        "has_critical": False,
    },
    "sim_003": {
        "warnings": [
            {
                "warning_id": "STAGE_STUCK",
                "title": "Stage Stuck",
                "description": "This deal has not advanced to a new stage in 28 days.",
                "severity": "critical",
                "suggested_action": "Identify the blocker — budget, timeline, or stakeholder alignment. Address directly in next call.",
            },
            {
                "warning_id": "COMMIT_RISK",
                "title": "Commit Risk",
                "description": "Deal is marked as committed but health score is below 60.",
                "severity": "critical",
                "suggested_action": "Re-evaluate forecast category. Either address root health issues or move to Best Case.",
            },
        ],
        "warning_count": 2,
        "has_critical": True,
    },
    "sim_004": {
        "warnings": [
            {
                "warning_id": "GONE_SILENT",
                "title": "Gone Silent",
                "description": "No buyer response or inbound engagement in 14 days.",
                "severity": "critical",
                "suggested_action": "Send a re-engagement email referencing your last conversation. Try a different contact if available.",
            },
            {
                "warning_id": "NO_NEXT_STEP",
                "title": "No Next Step",
                "description": "No scheduled meeting, task, or follow-up defined for this deal.",
                "severity": "high",
                "suggested_action": "Define a concrete next step and add it as a task in the CRM.",
            },
            {
                "warning_id": "SINGLE_THREADED",
                "title": "Single Threaded",
                "description": "Only one contact is engaged on this deal — high dependency risk.",
                "severity": "high",
                "suggested_action": "Identify and engage a second stakeholder — ask your champion for an intro.",
            },
        ],
        "warning_count": 3,
        "has_critical": True,
    },
    "sim_005": {
        "warnings": [
            {
                "warning_id": "SINGLE_THREADED",
                "title": "Single Threaded",
                "description": "Only one contact is engaged on this deal — high dependency risk.",
                "severity": "high",
                "suggested_action": "Ask your champion to introduce you to the economic buyer or a second stakeholder.",
            },
            {
                "warning_id": "GONE_SILENT",
                "title": "Gone Silent",
                "description": "No buyer response or inbound engagement in 7 days.",
                "severity": "high",
                "suggested_action": "Follow up with a value-add touchpoint — share a relevant case study or ROI insight.",
            },
        ],
        "warning_count": 2,
        "has_critical": False,
    },
    "sim_006": {
        "warnings": [
            {
                "warning_id": "STAGE_STUCK",
                "title": "Stage Stuck",
                "description": "This deal has not advanced to a new stage in 22 days.",
                "severity": "high",
                "suggested_action": "Review deal history and identify what's preventing stage progression. Book a discovery call to re-qualify.",
            }
        ],
        "warning_count": 1,
        "has_critical": False,
    },
}

_EMPTY_WARNINGS = {"warnings": [], "warning_count": 0, "has_critical": False}


# ── Rules-based warning computation for real Zoho deals ──────────────────────

def _compute_warnings(deal: dict) -> dict:
    """Derive warnings from mapped deal fields. No AI, no extra Zoho calls."""
    warnings = []

    # NO_NEXT_STEP
    next_step = (deal.get("next_step") or "").strip()
    if not next_step:
        warnings.append({
            "warning_id": "NO_NEXT_STEP",
            "title": "No Next Step",
            "description": "No scheduled meeting, task, or follow-up defined for this deal.",
            "severity": "high",
            "suggested_action": "Schedule a follow-up call or send a check-in email with a clear ask.",
        })

    # GONE_SILENT — based on last_activity_time, falling back to modified_time
    last_activity = deal.get("last_activity_time") or deal.get("modified_time")
    if last_activity:
        try:
            dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_silent = (now - dt).days
            if days_silent > 10:
                warnings.append({
                    "warning_id": "GONE_SILENT",
                    "title": "Gone Silent",
                    "description": f"No buyer response or inbound engagement in {days_silent} days.",
                    "severity": "critical" if days_silent > 14 else "high",
                    "suggested_action": "Send a re-engagement email referencing your last conversation.",
                })
        except Exception:
            pass

    # STAGE_STUCK — based on modified_time
    modified = deal.get("modified_time") or deal.get("last_modified")
    if modified:
        try:
            dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days_stuck = (now - dt).days
            if days_stuck > 21:
                warnings.append({
                    "warning_id": "STAGE_STUCK",
                    "title": "Stage Stuck",
                    "description": f"This deal has not advanced to a new stage in {days_stuck} days.",
                    "severity": "critical",
                    "suggested_action": "Identify the blocker — budget, timeline, or stakeholder alignment.",
                })
        except Exception:
            pass

    has_critical = any(w["severity"] == "critical" for w in warnings)
    return {"warnings": warnings, "warning_count": len(warnings), "has_critical": has_critical}


# ── Endpoints ─────────────────────────────────────────────────────────────────

# NOTE: /batch is defined BEFORE /{deal_id} so FastAPI matches it
# as a literal path segment, not as a deal_id wildcard.

class BatchWarningsRequest(BaseModel):
    deal_ids: list[str]


@router.post("/batch")
async def batch_deal_warnings(
    body: BatchWarningsRequest,
    authorization: str = Header(default=""),
):
    """
    Fetch warnings for up to 20 deals in a single request.
    Returns a dict keyed by deal_id.
    """
    if len(body.deal_ids) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 deal IDs per batch request")

    session = _decode_session(authorization)
    is_demo = _is_demo(session)

    result: dict[str, dict] = {}

    # Separate demo and real deal IDs
    demo_ids = [d for d in body.deal_ids if is_demo or d.startswith("sim_")]
    real_ids  = [d for d in body.deal_ids if not (is_demo or d.startswith("sim_"))]

    for deal_id in demo_ids:
        result[deal_id] = DEMO_WARNINGS.get(deal_id, _EMPTY_WARNINGS)

    if real_ids:
        from services.zoho_client import fetch_single_deal
        token = session.get("access_token", "")

        async def _fetch_one(deal_id: str) -> tuple[str, dict]:
            try:
                deal = await fetch_single_deal(token, deal_id)
                return deal_id, _compute_warnings(deal) if deal else _EMPTY_WARNINGS
            except Exception:
                return deal_id, _EMPTY_WARNINGS

        pairs = await asyncio.gather(*[_fetch_one(did) for did in real_ids])
        for deal_id, warnings in pairs:
            result[deal_id] = warnings

    return result


@router.get("/{deal_id}")
async def get_deal_warnings(
    deal_id: str,
    authorization: str = Header(default=""),
):
    """Return warnings for a single deal."""
    session = _decode_session(authorization)
    is_demo = _is_demo(session) or deal_id.startswith("sim_")

    if is_demo:
        return DEMO_WARNINGS.get(deal_id, _EMPTY_WARNINGS)

    from services.zoho_client import fetch_single_deal
    try:
        deal = await fetch_single_deal(session.get("access_token", ""), deal_id) or {}
    except Exception:
        return _EMPTY_WARNINGS

    return _compute_warnings(deal)
