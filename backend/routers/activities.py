from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import base64
import json
from datetime import datetime, timezone

from models.activity_schemas import ActivityFeedResponse, TeamActivitySummary
from services.activity_intelligence import get_deal_activity_feed, build_team_summary
from services.demo_data import SIMULATED_DEALS, SIMULATED_ACTIVITIES
from services.cache import cache_get, cache_set, cache_key as _ack, TTL_ACTIVITIES

router = APIRouter()


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


def _zoho_headers(session: dict) -> dict:
    return {"Authorization": f"Zoho-oauthtoken {session.get('access_token', '')}"}


def _deal_age_days(deal: dict) -> int:
    created = deal.get("created_time")
    if not created:
        return 30
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).days
    except Exception:
        return 30


@router.get("/team-summary", response_model=TeamActivitySummary)
async def get_team_activity_summary(
    authorization: str = Header(default=""),
):
    """
    Compute rep-level activity summary from deal data.
    Uses last_activity_time already on deal objects — no extra Zoho calls.
    Server-side cached for 5 minutes.
    """
    session = _decode_session(authorization)
    is_demo = _is_demo(session)

    # Redis cache — scoped by user email/id to prevent cross-tenant leakage
    _user = (session.get("email") or session.get("user_id") or "anon").replace(":", "_")
    _key = _ack("team_summary", "demo" if is_demo else _user)

    _cached = await cache_get(_key)
    if _cached is not None:
        return TeamActivitySummary(**_cached)

    if is_demo:
        deals = SIMULATED_DEALS
    else:
        from services.zoho_client import fetch_deals, map_zoho_deal
        try:
            raw_deals = await fetch_deals(session.get("access_token", ""))
            deals = [map_zoho_deal(d) for d in raw_deals]
        except Exception:
            raise HTTPException(status_code=502, detail="Failed to fetch deal data from Zoho")

    summary = build_team_summary(deals, is_demo=is_demo)
    await cache_set(_key, summary.model_dump(), ttl=TTL_ACTIVITIES)
    return summary


@router.get("/{deal_id}", response_model=ActivityFeedResponse)
async def get_activity_feed(
    deal_id: str,
    authorization: str = Header(default=""),
):
    """
    Return the activity feed and engagement intelligence for a single deal.
    Demo mode: uses SIMULATED_ACTIVITIES. Real mode: fetches from Zoho in parallel.
    """
    session = _decode_session(authorization)
    # Treat sim_xxx IDs as demo regardless of token — happens when browser retains
    # a demo deal ID after the user re-authenticates with real Zoho credentials.
    is_demo = _is_demo(session) or deal_id.startswith("sim_")

    if is_demo:
        # Find deal metadata for stage + age
        deal_meta = next((d for d in SIMULATED_DEALS if d["id"] == deal_id), None)
        stage = deal_meta.get("stage", "Unknown") if deal_meta else "Unknown"
        deal_age_days = _deal_age_days(deal_meta) if deal_meta else 30

        return await get_deal_activity_feed(
            deal_id=deal_id,
            access_token="",
            stage=stage,
            deal_age_days=deal_age_days,
            is_demo=True,
            demo_activities=SIMULATED_ACTIVITIES,
        )

    # Real mode — fetch deal metadata first for stage/age context
    # fetch_single_deal already returns a mapped deal (calls map_zoho_deal internally)
    from services.zoho_client import fetch_single_deal
    access_token = session.get("access_token", "")
    try:
        deal_meta = await fetch_single_deal(access_token, deal_id) or {}
    except Exception:
        deal_meta = {}

    stage = deal_meta.get("stage", "Unknown")
    deal_age_days = _deal_age_days(deal_meta)

    # Fetch Outlook emails to inject into the activity feed (ghost detection +
    # engagement velocity will see real cadence, not just what's in Zoho)
    outlook_emails: list = []
    try:
        from services.outlook_enrichment import get_enriched_emails
        user_key = session.get("email") or session.get("user_id") or "default"
        outlook_emails = await get_enriched_emails(deal_id, access_token, user_key, limit=30)
    except Exception as e:
        import logging as _log
        _log.getLogger(__name__).warning("activities: Outlook enrichment failed deal=%s: %s", deal_id, e)

    return await get_deal_activity_feed(
        deal_id=deal_id,
        access_token=access_token,
        stage=stage,
        deal_age_days=deal_age_days,
        is_demo=False,
        outlook_emails=outlook_emails or None,
    )
