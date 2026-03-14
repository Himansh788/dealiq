"""
Dashboard Command Center Router
================================
GET /dashboard/today — composite endpoint returning everything the 3-zone dashboard needs
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helpers (same pattern as digest.py) ──────────────────────────────────

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


# ── GET /dashboard/today ─────────────────────────────────────────────────────

@router.get("/today")
async def get_dashboard_today(authorization: str = Header(...)):
    """
    Composite endpoint that returns everything the dashboard command center needs:
    - focus: stats for the top bar (actions remaining, revenue at risk, next meeting)
    - actions: daily digest tasks with deal intelligence from ai_cache
    - completed_today: tasks completed today
    - calendar: today's upcoming meetings from Outlook
    - intelligence: pipeline pulse, declining deals, untouched deals, weekly progress
    """
    session = _decode_session(authorization)
    user_key = _user_key(session)
    simulated = _is_demo(session)

    # ── 1. Get digest (tasks + untouched deals) ──────────────────────────────
    digest = {}
    try:
        from routers.digest import get_today_digest
        digest = await get_today_digest(authorization)
    except Exception as e:
        logger.warning("dashboard: digest fetch failed: %s", e)
        digest = {"tasks": [], "untouched_deals": [], "progress": {"completed": 0, "total": 0}}

    tasks = digest.get("tasks", [])
    untouched = digest.get("untouched_deals", [])
    progress = digest.get("progress", {"completed": 0, "total": 0})

    # ── 2. Enrich tasks with deal intelligence from ai_cache ─────────────────
    enriched_tasks = []
    for task in tasks:
        deal_id = task.get("deal_id", "")
        intelligence = {}
        try:
            from services.ai_cache import get_all_analyses_for_deal
            cached = await get_all_analyses_for_deal(deal_id)
            if cached:
                health = cached.get("health_analysis", {})
                nba = cached.get("nba", {})
                intelligence = {
                    "health_summary": health.get("text", ""),
                    "nba_summary": nba.get("text", ""),
                    "has_cached_analysis": True,
                }
        except Exception:
            pass

        enriched_tasks.append({
            **task,
            "deal_intelligence": intelligence,
        })

    # Split into active vs completed
    active_tasks = [t for t in enriched_tasks if not t.get("is_completed")]
    completed_tasks = [t for t in enriched_tasks if t.get("is_completed")]

    # ── 3. Get pipeline metrics ──────────────────────────────────────────────
    metrics = {}
    try:
        from routers.deals import _fetch_all_zoho_deals
        from services.health_scorer import score_deal_from_zoho
        from services.demo_data import SIMULATED_DEALS

        if simulated:
            raw_deals = [dict(d) for d in SIMULATED_DEALS]
        else:
            try:
                raw_deals = await asyncio.wait_for(
                    _fetch_all_zoho_deals(session["access_token"]),
                    timeout=60.0,
                )
            except Exception:
                raw_deals = [dict(d) for d in SIMULATED_DEALS]

        # Compute basic metrics
        total_value = sum(float(d.get("Amount") or d.get("amount") or 0) for d in raw_deals)
        health_scores = []
        declining_deals = []

        for d in raw_deals:
            try:
                result = score_deal_from_zoho(d)
                score = result.total_score
                label = result.health_label
                health_scores.append(score)

                # Track deals with low scores as "declining"
                if label in ("critical", "zombie") and float(d.get("amount") or d.get("Amount") or 0) > 0:
                    declining_deals.append({
                        "deal_id": d.get("id") or d.get("id", ""),
                        "deal_name": d.get("Deal_Name") or d.get("deal_name") or "",
                        "amount": float(d.get("Amount") or d.get("amount") or 0),
                        "health_score": score,
                        "health_label": label,
                        "stage": d.get("Stage") or d.get("stage") or "",
                    })
            except Exception:
                pass

        avg_health = round(sum(health_scores) / len(health_scores)) if health_scores else 50
        declining_deals.sort(key=lambda x: x["health_score"])

        # Revenue at risk = sum of amounts for critical/zombie deals
        revenue_at_risk = sum(d["amount"] for d in declining_deals)

        metrics = {
            "pipeline_health": avg_health,
            "pipeline_value": total_value,
            "total_deals": len(raw_deals),
            "deals_declining": declining_deals[:5],
            "revenue_at_risk": revenue_at_risk,
        }
    except Exception as e:
        logger.warning("dashboard: metrics computation failed: %s", e)
        metrics = {
            "pipeline_health": 50,
            "pipeline_value": 0,
            "total_deals": 0,
            "deals_declining": [],
            "revenue_at_risk": 0,
        }

    # ── 4. Get today's calendar from Outlook ─────────────────────────────────
    calendar_events = []
    next_meeting = None
    if not simulated:
        try:
            from routers.ms_auth import get_user_token
            from services.outlook_client import get_upcoming_meetings
            tok = await get_user_token(user_key)
            if tok and tok.get("access_token"):
                events = await get_upcoming_meetings(tok["access_token"])
                now = datetime.now(timezone.utc)
                for ev in (events or []):
                    start_str = ev.get("start", {}).get("dateTime", "")
                    calendar_events.append({
                        "subject": ev.get("subject", "Meeting"),
                        "start": start_str,
                        "deal_id": ev.get("deal_id"),
                        "teams_link": ev.get("onlineMeeting", {}).get("joinUrl") if ev.get("isOnlineMeeting") else None,
                        "web_link": ev.get("webLink", ""),
                    })
                # Next meeting = first future event
                if calendar_events:
                    next_meeting = calendar_events[0]
        except Exception as e:
            logger.debug("dashboard: calendar fetch failed: %s", e)

    # ── 5. Build response ────────────────────────────────────────────────────
    return {
        "focus": {
            "actions_remaining": progress["total"] - progress["completed"],
            "actions_total": progress["total"],
            "actions_completed": progress["completed"],
            "deals_needing_attention": len(untouched),
            "revenue_at_risk": metrics.get("revenue_at_risk", 0),
            "next_meeting": next_meeting,
        },
        "actions": active_tasks,
        "completed_today": completed_tasks,
        "calendar": calendar_events,
        "intelligence": {
            "pipeline_health": metrics.get("pipeline_health", 50),
            "pipeline_value": metrics.get("pipeline_value", 0),
            "total_deals": metrics.get("total_deals", 0),
            "deals_declining": metrics.get("deals_declining", []),
            "untouched_deals": untouched[:5],
            "weekly_progress": {
                "actions_completed": progress["completed"],
                "actions_total": progress["total"],
            },
        },
        "simulated": simulated or digest.get("simulated", False),
    }
