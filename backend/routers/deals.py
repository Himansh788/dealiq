from fastapi import APIRouter, Header, HTTPException, Query
from typing import Optional, List
import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from services.zoho_client import (
    fetch_deals, map_zoho_deal, fetch_single_deal, search_deals,
    fetch_deal_activities_closed, fetch_deal_contact_roles, fetch_deal_emails,
)
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


# ── Deal Enrichment ────────────────────────────────────────────────────────────

def _enrich_deal(raw: dict, activities: dict = None, contact_roles: list = None) -> dict:
    """Add computed time-based and real activity/contact fields to a raw mapped deal dict.

    activities   — output of fetch_deal_activities_closed: {"tasks": [...], "meetings": [...]}
    contact_roles — output of fetch_deal_contact_roles: [{name, role, email}, ...]

    When real data is not provided (dashboard list calls that can't afford per-deal API calls),
    we fall back to probability-based proxies so existing callers keep working unchanged.
    """
    def _days_since(dt_str):
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).days
        except Exception:
            return None

    # Use modified_time as proxy for stage-change time (a stage change always bumps modified_time).
    # Falls back to last_activity_time then created_time if modified_time is absent.
    raw["days_in_stage"] = _days_since(
        raw.get("modified_time") or raw.get("last_activity_time") or raw.get("created_time")
    )
    raw["last_activity_days"] = _days_since(raw.get("last_activity_time"))
    raw["days_since_buyer_response"] = raw["last_activity_days"]

    # ── Activity data ──────────────────────────────────────────────────────────
    if activities is not None:
        closed_tasks = activities.get("tasks", [])
        closed_meetings = activities.get("meetings", [])
        raw["activity_count_30d"] = len(closed_tasks) + len(closed_meetings)
        raw["has_completed_meeting"] = len(closed_meetings) > 0
        raw["closed_tasks"] = closed_tasks
        raw["closed_meetings"] = closed_meetings
    else:
        prob = raw.get("probability", 0) or 0
        if prob >= 90:    raw["activity_count_30d"] = 5
        elif prob >= 50:  raw["activity_count_30d"] = 3
        elif prob >= 20:  raw["activity_count_30d"] = 2
        else:             raw["activity_count_30d"] = 1
        raw["has_completed_meeting"] = False
        raw["closed_tasks"] = []
        raw["closed_meetings"] = []

    # ── Contact role data ──────────────────────────────────────────────────────
    if contact_roles is not None:
        raw["contact_count"] = len(contact_roles)
        raw["contact_roles"] = contact_roles
        economic_titles = {"economic buyer", "decision maker", "approver", "ceo", "cfo", "cto",
                           "vp", "vice president", "director", "executive", "owner", "president"}
        raw["economic_buyer_engaged"] = any(
            any(kw in (c.get("role") or "").lower() for kw in economic_titles)
            for c in contact_roles
        )
    else:
        prob = raw.get("probability", 0) or 0
        raw["contact_count"] = 2 if prob >= 30 else 1
        raw["contact_roles"] = []
        raw["economic_buyer_engaged"] = prob >= 70

    raw["discount_mention_count"] = 0
    return raw


def build_deal_context(raw: dict) -> str:
    """
    Build a compact deal-level context string from mapped deal fields.
    Injected into every AI prompt so the model knows the buyer's pain point,
    deal type, region, and team — not just name/stage/amount.
    """
    lines = []

    if raw.get("description"):
        lines.append(f"BUYER PAIN POINT: {raw['description']}")

    if raw.get("deal_type"):
        lines.append(f"Deal Type: {raw['deal_type']}")

    region_parts = [raw.get("geo_region", ""), raw.get("country", ""), raw.get("city", "")]
    region = " | ".join(p for p in region_parts if p)
    if region:
        lines.append(f"Region: {region}")

    if raw.get("contact_name"):
        lines.append(f"Primary Contact: {raw['contact_name']}")

    if raw.get("no_of_booking_per_month"):
        lines.append(f"Bookings/Month: {raw['no_of_booking_per_month']}")

    if raw.get("expected_revenue"):
        lines.append(f"Expected Revenue: ${raw['expected_revenue']:,.0f}")

    if raw.get("inside_sales_rep") and str(raw.get("inside_sales_rep", "")).upper() not in ("NA", "N/A", "NONE", ""):
        lines.append(f"Inside Sales Rep: {raw['inside_sales_rep']}")

    if raw.get("lost_reason"):
        lines.append(f"Lost/Kill Reason on File: {raw['lost_reason']}")

    return "\n".join(lines) if lines else ""


async def get_fully_enriched_deal(access_token: str, deal_id: str) -> dict:
    """
    Single entry point for fetching a deal with ALL context needed by AI endpoints.

    - Fetches exactly ONE deal (no more 200-deal list scans)
    - Fetches activities, contact roles, and emails in parallel
    - Enriches the deal dict with real CRM data (replaces probability proxies)
    - Stores _emails_raw for callers to format into email_context

    Raises HTTP 404 if the deal is not found.
    """
    raw = await fetch_single_deal(access_token, deal_id)
    if not raw:
        raise HTTPException(status_code=404, detail="Deal not found")

    activities, contact_roles, emails = await asyncio.gather(
        fetch_deal_activities_closed(access_token, deal_id),
        fetch_deal_contact_roles(access_token, deal_id),
        fetch_deal_emails(access_token, deal_id),
        return_exceptions=True,
    )
    if isinstance(activities, Exception):
        activities = {}
    if isinstance(contact_roles, Exception):
        contact_roles = []
    if isinstance(emails, Exception):
        emails = []

    raw = _enrich_deal(raw, activities=activities, contact_roles=contact_roles)
    raw["_emails_raw"] = emails
    return raw


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
    per_page: int = Query(default=15, le=200),
    search: Optional[str] = Query(default=None, max_length=200),
):
    """
    Returns active current-quarter deals, paginated.
    When search is provided, queries Zoho's search criteria API by Deal_Name.
    total, total_pages, has_next, has_prev let the frontend render pagination correctly.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)
    quarter_start, quarter_end = get_current_quarter_range()

    more_records_from_zoho = False  # only relevant for server-side search path

    if search:
        # ── Server-side search path ──────────────────────────────────────────
        token = session.get("access_token", "")
        logger.info(
            "list_deals search: token_present=%s search=%r page=%d simulated=%s",
            bool(token), search, page, simulated,
        )

        if simulated:
            term = search.lower()
            raw_deals = [
                r for r in SIMULATED_DEALS
                if term in (r.get("name") or "").lower()
                or term in (r.get("account_name") or "").lower()
            ]
        else:
            try:
                records, more_records_from_zoho = await search_deals(
                    token, search, page=page, per_page=per_page
                )
                raw_deals = [map_zoho_deal(r) for r in records]
                logger.info("list_deals search: zoho returned %d records more_records=%s", len(raw_deals), more_records_from_zoho)
            except Exception as exc:
                logger.error("list_deals search: zoho search failed: %s", exc, exc_info=True)
                raise HTTPException(status_code=502, detail=f"Zoho search failed: {exc}")

        # Search results are NOT filtered by quarter/stage — user is searching by name
        # and expects to find any matching deal regardless of close date.
        active_raw = raw_deals

        # Score and enrich
        scored: List[Deal] = []
        for raw in active_raw:
            _enrich_deal(raw)
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
                days_in_stage=raw.get("days_in_stage"),
                next_step=raw.get("next_step"),
            ))
        scored.sort(key=lambda d: d.health_score or 0)

        # Zoho search doesn't return total count — approximate from known info
        count_this_page = len(scored)
        if simulated:
            real_total = count_this_page
            total_pages = max(1, -(-real_total // per_page))  # ceiling div
            has_next = False
        else:
            # Best estimate: pages seen so far + (1 more if Zoho says more_records)
            min_total = (page - 1) * per_page + count_this_page
            real_total = min_total + (per_page if more_records_from_zoho else 0)
            total_pages = max(page, page + (1 if more_records_from_zoho else 0))
            has_next = more_records_from_zoho

        return DealList(
            deals=scored,
            total=real_total,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=page > 1,
            simulated=simulated,
        )

    # ── Full pipeline list path (no search) ───────────────────────────────────
    if simulated:
        raw_deals = SIMULATED_DEALS
    else:
        try:
            raw_deals = await _fetch_all_zoho_deals(session["access_token"])
        except Exception:
            raw_deals = SIMULATED_DEALS
            simulated = True

    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]

    scored_all: List[Deal] = []
    for raw in active_raw:
        _enrich_deal(raw)
        result = score_deal_from_zoho(raw)
        scored_all.append(Deal(
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
            days_in_stage=raw.get("days_in_stage"),
            next_step=raw.get("next_step"),
        ))

    scored_all.sort(key=lambda d: d.health_score or 0)

    real_total = len(scored_all)
    total_pages = max(1, -(-real_total // per_page))  # ceiling div
    start = (page - 1) * per_page
    page_deals = scored_all[start: start + per_page]

    return DealList(
        deals=page_deals,
        total=real_total,
        total_pages=total_pages,
        has_next=(page * per_page) < real_total,
        has_prev=page > 1,
        simulated=simulated,
    )


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
    demo = _is_demo(session) or deal_id.startswith("sim_")

    if demo:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        try:
            raw = await get_fully_enriched_deal(session["access_token"], deal_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Fetch activity bundle — async, non-blocking, failure-safe
    activity_data = None
    if demo:
        from services.demo_data import get_demo_activity_data
        activity_data = get_demo_activity_data(deal_id)
    else:
        try:
            from services.zoho_client import get_all_activity_for_deal
            activity_data = await get_all_activity_for_deal(session["access_token"], deal_id)
        except Exception as e:
            logger.warning("Activity fetch failed deal=%s: %s", deal_id, e)

    # Fetch timeline analysis — non-blocking, graceful fallback
    timeline_analysis = {}
    if demo:
        from services.demo_data import get_demo_timeline
        from services.timeline_analyzer import analyze_timeline
        demo_tl = get_demo_timeline(deal_id)
        timeline_analysis = analyze_timeline(demo_tl.get("timeline", []))
    else:
        try:
            from services.zoho_client import fetch_deal_timeline
            from services.timeline_analyzer import analyze_timeline
            raw_tl = await fetch_deal_timeline(session["access_token"], deal_id)
            timeline_analysis = analyze_timeline(raw_tl.get("timeline", []))
        except Exception as e:
            logger.warning("Timeline fetch failed deal=%s: %s", deal_id, e)

    # Score with best available signals
    if activity_data and activity_data.get("summary") and timeline_analysis.get("total_entries"):
        from services.health_scorer import score_deal_with_timeline
        return score_deal_with_timeline(raw, activity_data, timeline_analysis)

    if activity_data and activity_data.get("summary"):
        from services.health_scorer import score_deal_with_activities
        return score_deal_with_activities(raw, activity_data)

    return score_deal_from_zoho(raw)


@router.get("/{deal_id}/timeline")
async def get_deal_timeline(deal_id: str, authorization: str = Header(...)):
    """
    Build a full activity timeline for a deal.

    Sources (merged in priority order):
    1. Zoho v9 Timelines API — stage changes with colour codes, email events, revenue changes
    2. Zoho notes + activities (existing build_timeline logic)

    Falls back gracefully: if v9 fails, existing data still renders.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session) or deal_id.startswith("sim_")

    from services.deal_timeline import build_timeline, generate_timeline_narrative
    from services.timeline_analyzer import analyze_timeline, enrich_timeline_events
    from datetime import timedelta

    if simulated:
        from services.demo_data import get_demo_timeline
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
        raw_timeline_data = get_demo_timeline(deal_id)

    else:
        from services.zoho_client import fetch_deal_notes, fetch_deal_activities, fetch_deal_timeline

        try:
            raw, notes, activities, raw_timeline_data = await asyncio.gather(
                fetch_single_deal(session["access_token"], deal_id),
                fetch_deal_notes(session["access_token"], deal_id),
                fetch_deal_activities(session["access_token"], deal_id),
                fetch_deal_timeline(session["access_token"], deal_id),
                return_exceptions=True,
            )
            if isinstance(raw, Exception) or raw is None:
                raw = {}
            if isinstance(notes, Exception):
                notes = []
            if isinstance(activities, Exception):
                activities = []
            if isinstance(raw_timeline_data, Exception):
                raw_timeline_data = {"timeline": []}
        except Exception as e:
            return {"error": str(e), "events": [], "signals": [], "narrative": ""}

    # Build base timeline from notes + activities
    base_timeline = build_timeline(raw, notes, activities)

    # Parse v9 timeline data
    v9_entries = raw_timeline_data.get("timeline", []) if isinstance(raw_timeline_data, dict) else []
    timeline_analysis = analyze_timeline(v9_entries)

    # Merge v9 events into base timeline events
    enriched_events = enrich_timeline_events(
        base_timeline["events"],
        timeline_analysis,
        v9_entries,
    )
    base_timeline["events"] = enriched_events
    base_timeline["total_events"] = len(enriched_events)

    # Add extra signals derived from v9 data
    v9_signals = []
    signals_data = timeline_analysis.get("deal_health_signals", {})
    if timeline_analysis.get("stage_progression"):
        latest_stage = timeline_analysis["stage_progression"][-1]
        if latest_stage["direction"] == "backward":
            v9_signals.append({
                "severity": "critical",
                "text": f"Stage regressed: {latest_stage['old_stage']} → {latest_stage['new_stage']}"
            })
        else:
            v9_signals.append({
                "severity": "good",
                "text": f"Stage advancing: → {latest_stage['new_stage']}"
            })

    days_email = timeline_analysis.get("days_since_last_email")
    if days_email is not None and days_email > 30:
        v9_signals.append({"severity": "critical", "text": f"No email sent in {days_email} days"})
    elif days_email is not None and days_email <= 7:
        v9_signals.append({"severity": "good", "text": f"Email sent {days_email}d ago"})

    ratio = signals_data.get("human_activity_ratio", 1.0)
    if ratio < 0.4 and timeline_analysis.get("total_entries", 0) > 3:
        v9_signals.append({"severity": "warning", "text": "Only automated emails sent — no human touch"})

    if signals_data.get("revenue_growing"):
        v9_signals.append({"severity": "good", "text": "Revenue growing — deal showing momentum"})

    # Prepend v9 signals (they're more accurate)
    base_timeline["signals"] = v9_signals + base_timeline.get("signals", [])

    # Generate narrative
    narrative = await generate_timeline_narrative(
        deal_name=raw.get("name", "This deal"),
        stage=raw.get("stage", "Unknown"),
        amount=float(raw.get("amount") or 0),
        health_label=raw.get("health_label", "unknown"),
        timeline=base_timeline,
    )

    base_timeline["narrative"] = narrative
    base_timeline["deal_name"] = raw.get("name", "")
    base_timeline["stage"] = raw.get("stage", "")
    base_timeline["closing_date"] = raw.get("closing_date", "")
    base_timeline["amount"] = raw.get("amount", 0)

    # Include timeline intelligence summary for frontend
    base_timeline["timeline_intelligence"] = {
        "stage_progression": timeline_analysis.get("stage_progression", []),
        "last_email_sent": timeline_analysis.get("last_email_sent"),
        "last_email_subject": timeline_analysis.get("last_email_subject"),
        "days_since_last_email": timeline_analysis.get("days_since_last_email"),
        "revenue_changes": timeline_analysis.get("revenue_changes", []),
        "automation_count": timeline_analysis.get("automation_entries", 0),
        "human_count": timeline_analysis.get("human_entries", 0),
        "deal_health_signals": signals_data,
    }

    return base_timeline