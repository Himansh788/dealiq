from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional, List
import base64
import json
from datetime import datetime, timezone
from services.zoho_client import fetch_deals, map_zoho_deal
from services.health_scorer import score_deal_from_zoho
from services.demo_data import SIMULATED_DEALS
from models.schemas import Deal, DealList, PipelineMetrics, DealHealthResult

router = APIRouter()

# ── Smart Filter Config ────────────────────────────────────────────────────────
# Stages that represent dead/done deals — excluded from dashboard entirely
EXCLUDED_STAGES = {
    "Closed Won",
    "Closed Lost",
    "Evaluation Failed",
    "Duplicate",
    "Juniper Validated",
}


def get_current_quarter_range() -> tuple[datetime, datetime]:
    """Returns (quarter_start, quarter_end) in UTC for the current calendar quarter."""
    now = datetime.now(timezone.utc)
    quarter = (now.month - 1) // 3          # 0=Q1, 1=Q2, 2=Q3, 3=Q4
    quarter_start_month = quarter * 3 + 1   # 1, 4, 7, 10
    quarter_start = datetime(now.year, quarter_start_month, 1, tzinfo=timezone.utc)

    if quarter == 3:
        quarter_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        quarter_end = datetime(now.year, quarter_start_month + 3, 1, tzinfo=timezone.utc)

    return quarter_start, quarter_end


def is_active_deal(raw: dict, quarter_start: datetime, quarter_end: datetime) -> bool:
    """
    Returns True if the deal should appear on the dashboard.

    Rules:
      1. Stage must NOT be in EXCLUDED_STAGES
      2. closing_date must fall within the current quarter
         - We allow up to 30 days BEFORE quarter start (overdue deals still need action)
         - Deals with no closing_date are included (better to show than silently hide)
    """
    from datetime import timedelta

    stage = raw.get("stage", "")
    if stage in EXCLUDED_STAGES:
        return False

    closing_date_raw = raw.get("closing_date")
    if closing_date_raw:
        try:
            cd = datetime.strptime(str(closing_date_raw)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            overdue_cutoff = quarter_start - timedelta(days=30)  # grace window for overdue
            if cd < overdue_cutoff:
                return False   # too stale, past quarter started
            if cd > quarter_end:
                return False   # closing date beyond current quarter
        except (ValueError, TypeError):
            pass  # unparseable date → include the deal

    return True


# ── Auth Helpers ───────────────────────────────────────────────────────────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.replace("Bearer ", "")
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


# ── Zoho Full Fetch ────────────────────────────────────────────────────────────

async def _fetch_all_zoho_deals(access_token: str) -> list:
    """
    Fetch all deals from Zoho. Uses per_page=200 to minimize round trips.
    Safety cap at 10 pages (2000 deals).
    """
    all_deals = []
    page = 1
    while True:
        raw = await fetch_deals(access_token, page=page, per_page=200)
        if not raw:
            break
        all_deals.extend([map_zoho_deal(r) for r in raw])
        if len(raw) < 200:
            break
        page += 1
        if page > 10:
            break
    return all_deals


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_model=DealList)
async def list_deals(
    authorization: str = Header(...),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=200, le=500),
):
    """
    Returns active current-quarter deals only.
    Excludes dead stages. Sorted worst health first.
    total reflects filtered count so frontend knows when to stop paginating.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)
    quarter_start, quarter_end = get_current_quarter_range()

    if simulated:
        raw_deals = SIMULATED_DEALS
    else:
        try:
            raw_deals = await _fetch_all_zoho_deals(session["access_token"])
        except Exception:
            raw_deals = SIMULATED_DEALS
            simulated = True

    # ── Filter ────────────────────────────────────────────────────────────────
    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]

    # ── Score ─────────────────────────────────────────────────────────────────
    scored: List[Deal] = []
    for raw in active_raw:
        result = score_deal_from_zoho(raw)
        scored.append(Deal(
            id=raw["id"],
            name=raw["name"],
            stage=raw["stage"],
            amount=raw.get("amount"),
            closing_date=raw.get("closing_date"),
            account_name=raw.get("account_name"),
            owner=raw.get("owner"),
            last_activity_time=raw.get("last_activity_time"),
            created_time=raw.get("created_time"),
            probability=raw.get("probability"),
            health_score=result.total_score,
            health_label=result.health_label,
            next_step=raw.get("next_step"),
        ))

    scored.sort(key=lambda d: d.health_score or 0)

    real_total = len(scored)
    start = (page - 1) * per_page
    page_deals = scored[start: start + per_page]

    return DealList(deals=page_deals, total=real_total, simulated=simulated)


@router.get("/metrics", response_model=PipelineMetrics)
async def get_pipeline_metrics(authorization: str = Header(...)):
    """
    Summary cards use the SAME active-deal filter so numbers always match the table.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)
    quarter_start, quarter_end = get_current_quarter_range()

    if simulated:
        raw_deals = SIMULATED_DEALS
    else:
        try:
            raw_deals = await _fetch_all_zoho_deals(session["access_token"])
        except Exception:
            raw_deals = SIMULATED_DEALS

    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]

    counts = {"healthy": 0, "at_risk": 0, "critical": 0, "zombie": 0}
    total_value = 0.0
    scores = []
    action_needed = 0

    for raw in active_raw:
        result = score_deal_from_zoho(raw)
        label = result.health_label
        counts[label] = counts.get(label, 0) + 1
        scores.append(result.total_score)
        if raw.get("amount"):
            total_value += raw["amount"]
        if result.action_required:
            action_needed += 1

    avg = sum(scores) / len(scores) if scores else 0

    return PipelineMetrics(
        total_deals=len(active_raw),
        total_value=total_value,
        average_health_score=round(avg, 1),
        healthy_count=counts["healthy"],
        at_risk_count=counts["at_risk"],
        critical_count=counts["critical"],
        zombie_count=counts["zombie"],
        deals_needing_action=action_needed,
    )


@router.get("/{deal_id}/health", response_model=DealHealthResult)
async def get_deal_health(deal_id: str, authorization: str = Header(...)):
    """Get full health score breakdown for a single deal."""
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        try:
            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            raw_list = [r for r in all_deals if r.get("id") == deal_id]
            if not raw_list:
                raise HTTPException(status_code=404, detail="Deal not found in Zoho CRM")
            raw = raw_list[0]
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return score_deal_from_zoho(raw)


@router.get("/{deal_id}/timeline")
async def get_deal_timeline(deal_id: str, authorization: str = Header(...)):
    """Build a full activity timeline for a deal."""
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    from services.deal_timeline import build_timeline, generate_timeline_narrative
    from datetime import timedelta

    if simulated:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raw_list = [SIMULATED_DEALS[0]]
        raw = raw_list[0]

        now = datetime.now(timezone.utc)
        demo_notes = [
            {
                "Note_Title": "Discovery call completed",
                "Note_Content": "Buyer confirmed budget approved. Key stakeholder is CTO. Main pain: reporting takes 3 days manually.",
                "Created_Time": (now - timedelta(days=32)).isoformat(),
            },
            {
                "Note_Title": "Demo delivered",
                "Note_Content": "Live demo went well. Buyer asked about API integration. Promised to follow up with technical spec.",
                "Created_Time": (now - timedelta(days=18)).isoformat(),
            },
            {
                "Note_Title": "Proposal sent",
                "Note_Content": "Sent proposal for $84K annual plan. Buyer said they'd review with finance team this week.",
                "Created_Time": (now - timedelta(days=12)).isoformat(),
            },
        ]
        demo_activities = [
            {
                "Subject": "Intro call",
                "$se_module": "Calls",
                "Status": "Completed",
                "Created_Time": (now - timedelta(days=38)).isoformat(),
            },
            {
                "Subject": "Follow-up email re: pricing",
                "$se_module": "Emails",
                "Status": "Sent",
                "Created_Time": (now - timedelta(days=8)).isoformat(),
            },
        ]
        notes, activities = demo_notes, demo_activities
    else:
        try:
            from services.zoho_client import fetch_deal_notes, fetch_deal_activities
            import asyncio

            notes, activities = await asyncio.gather(
                fetch_deal_notes(session["access_token"], deal_id),
                fetch_deal_activities(session["access_token"], deal_id),
                return_exceptions=True,
            )
            if isinstance(notes, Exception):
                notes = []
            if isinstance(activities, Exception):
                activities = []

            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            raw_list = [r for r in all_deals if r.get("id") == deal_id]
            raw = raw_list[0] if raw_list else {}
        except Exception as e:
            return {"error": str(e), "events": [], "signals": [], "narrative": ""}

    timeline = build_timeline(raw, notes, activities)
    narrative = await generate_timeline_narrative(
        deal_name=raw.get("name", "This deal"),
        stage=raw.get("stage", "Unknown"),
        amount=float(raw.get("amount") or 0),
        health_label=raw.get("health_label", "unknown"),
        timeline=timeline,
    )
    timeline["narrative"] = narrative
    timeline["deal_name"] = raw.get("name", "")
    timeline["stage"] = raw.get("stage", "")
    timeline["closing_date"] = raw.get("closing_date", "")
    timeline["amount"] = raw.get("amount", 0)

    return timeline