from fastapi import APIRouter, Depends, Header, HTTPException, Query
from typing import Any, Optional, List, Union
from pydantic import BaseModel
import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from groq import AsyncGroq
import httpx

# ── Redis cache layer (falls back to in-memory if Redis unavailable) ──────────
from services.cache import (
    cache_get, cache_set, cache_delete_pattern, cache_key as _rkey,
    TTL_HEALTH_SCORES, TTL_PIPELINE_METRICS,
)

# ── In-memory fallback cache for health scores (used when Redis is unavailable)
_health_cache: dict = {}  # deal_id -> (result, expires_at)
_HEALTH_CACHE_TTL = TTL_HEALTH_SCORES

# ── Pipeline metrics + AI summary shared cache ────────────────────────────────
# Per key: {"metrics": PipelineMetrics, "summary": str, "expires_at": float}
_pipeline_cache: dict[str, dict] = {}
_PIPELINE_CACHE_TTL = TTL_PIPELINE_METRICS
_PIPELINE_REFRESHING: set[str] = set()  # guard against duplicate concurrent refreshes

logger = logging.getLogger(__name__)
from database import get_db
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
            if cd > quarter_end + timedelta(days=90):
                return False   # closing date more than one quarter ahead
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
        raw["contact_count"] = 1
        raw["contact_roles"] = []
        raw["economic_buyer_engaged"] = False

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

@router.get("/filter-options")
async def get_filter_options(
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """
    Returns all unique owners and stages across all active current-quarter deals.
    Used to populate filter dropdowns on the dashboard.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)
    quarter_start, quarter_end = get_current_quarter_range()

    if simulated:
        raw_deals = SIMULATED_DEALS
    else:
        from services.deal_db import get_cached_deals
        user_email = session.get("email", "")
        cached, _ = await get_cached_deals(db, user_email)
        if cached is not None:
            raw_deals = cached
        else:
            try:
                raw_deals = await _fetch_all_zoho_deals(session["access_token"])
            except Exception:
                raw_deals = SIMULATED_DEALS

    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]

    owners = sorted({str(r.get("owner") or "") for r in active_raw if r.get("owner")})
    stages = sorted({str(r.get("stage") or "") for r in active_raw if r.get("stage")})

    return {"owners": owners, "stages": stages}


@router.get("/debug/zoho-test")
async def debug_zoho_test(
    authorization: str = Header(default=""),
):
    """
    Diagnostic endpoint — checks whether the current session can reach Zoho
    and returns a sample of what deal data looks like.
    Safe to call at any time; never modifies data.
    """
    session = _decode_session(authorization)

    if _is_demo(session):
        return {
            "mode": "demo",
            "message": "You're in demo mode. Connect Zoho CRM to see real data.",
            "demo_deals_available": True,
        }

    access_token = session.get("access_token", "")
    try:
        raw_deals = await fetch_deals(access_token, page=1, per_page=5)
        deals = [map_zoho_deal(r) for r in raw_deals] if raw_deals else []
        first = deals[0] if deals else None
        return {
            "mode": "zoho_live",
            "deals_fetched": len(deals),
            "sample_deal": first,
            "zoho_fields_available": list(first.keys()) if first else [],
            "error": None,
        }
    except Exception as e:
        return {
            "mode": "zoho_live",
            "deals_fetched": 0,
            "sample_deal": None,
            "zoho_fields_available": [],
            "error": str(e),
        }


@router.get("/", response_model=DealList)
async def list_deals(
    authorization: str = Header(...),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=15, le=200),
    search: Optional[str] = Query(default=None, max_length=200),
    health_label: Optional[str] = Query(default=None),
    owner: Optional[str] = Query(default=None, max_length=200),
    stage: Optional[str] = Query(default=None, max_length=200),
    db=Depends(get_db),
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
            except httpx.HTTPStatusError as exc:
                logger.warning("list_deals search: zoho %s — %s", exc.response.status_code, exc.response.text[:300])
                if exc.response.status_code == 400:
                    raise HTTPException(status_code=400, detail="Search query invalid, try a simpler term")
                raise HTTPException(status_code=502, detail=f"Zoho search failed: {exc.response.status_code}")
            except Exception as exc:
                logger.error("list_deals search: unexpected error: %s", exc, exc_info=True)
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
    # Helper: run a DB write in a fresh session so it's safe to fire as a
    # background task.  The request-scoped `db` is closed before background
    # tasks execute; they must own their session lifetime.
    async def _bg_write(coro_fn, *args, **kwargs):
        from database.connection import AsyncSessionLocal
        if AsyncSessionLocal is None:
            return
        try:
            async with AsyncSessionLocal() as new_db:
                await coro_fn(new_db, *args, **kwargs)
                await new_db.commit()
        except Exception as exc:
            logger.warning("Background DB write failed: %s", exc)

    cache_meta: dict = {}
    if simulated:
        raw_deals = SIMULATED_DEALS
    else:
        from services.deal_db import get_cached_deals, upsert_deals
        from services.cache_manager import get_cache_status
        user_email = session.get("email", "")
        cached, cache_meta = await get_cached_deals(db, user_email)

        if cached is not None:
            raw_deals = cached
            # Background sync if >30% stale — user gets fresh data silently
            if cache_meta.get("needs_background_sync"):
                access_token = session["access_token"]
                async def _bg_sync():
                    try:
                        fresh = await _fetch_all_zoho_deals(access_token)
                        await _bg_write(upsert_deals, fresh, user_email)
                    except Exception as exc:
                        logger.warning("Background sync failed: %s", exc)
                asyncio.create_task(_bg_sync())
        else:
            # No rows at all — blocking Zoho fetch on first load
            try:
                raw_deals = await _fetch_all_zoho_deals(session["access_token"])
                # Write in background so response isn't blocked; own session
                asyncio.create_task(_bg_write(upsert_deals, raw_deals, user_email))
                cache_meta = get_cache_status(datetime.now(timezone.utc), "deals")
                cache_meta["source"] = "zoho"
            except Exception:
                raw_deals = SIMULATED_DEALS
                simulated = True

    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]

    # Score all deals and collect health results for batch persistence
    health_results: dict = {}
    scored_all: List[Deal] = []
    for raw in active_raw:
        _enrich_deal(raw)
        result = score_deal_from_zoho(raw)
        zoho_id = str(raw.get("id") or "")
        if zoho_id:
            health_results[zoho_id] = result
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

    # Fetch trends using the live request session (read — session is still open here)
    # Then persist scores in background with a fresh session
    if not simulated and health_results and db is not None:
        from services.score_db import persist_health_score, batch_get_trends

        # Read: inline, session is open
        trends = await batch_get_trends(db, list(health_results.keys()))

        # Write: background task with its own session
        captured_results = dict(health_results)
        async def _persist_scores():
            from database.connection import AsyncSessionLocal
            if AsyncSessionLocal is None:
                return
            try:
                async with AsyncSessionLocal() as new_db:
                    for zid, hr in captured_results.items():
                        await persist_health_score(new_db, zid, hr)
                    # persist_health_score commits per row; final commit is a no-op
            except Exception as exc:
                logger.warning("Score persist background task failed: %s", exc)
        asyncio.create_task(_persist_scores())

        for deal in scored_all:
            deal.score_trend = trends.get(deal.id)
    else:
        trends = {}

    scored_all.sort(key=lambda d: d.health_score or 0)

    # Server-side filtering by health_label, owner, stage
    if health_label and health_label != "all":
        scored_all = [d for d in scored_all if d.health_label == health_label]
    if owner and owner != "all":
        scored_all = [d for d in scored_all if (d.owner or "") == owner]
    if stage and stage != "all":
        scored_all = [d for d in scored_all if (d.stage or "") == stage]

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
        cache_meta=cache_meta or None,
    )


async def _compute_pipeline_data(access_token: str, is_demo: bool) -> dict:
    """
    Core computation: score all active deals + call Groq for AI summary.
    Returns a dict ready to be stored in _pipeline_cache.
    Never raises — falls back gracefully so the cache always gets a value.
    """
    quarter_start, quarter_end = get_current_quarter_range()

    if is_demo:
        raw_deals = SIMULATED_DEALS
    else:
        try:
            raw_deals = await _fetch_all_zoho_deals(access_token)
        except Exception:
            raw_deals = SIMULATED_DEALS

    active_raw = [r for r in raw_deals if is_active_deal(r, quarter_start, quarter_end)]
    counts: dict[str, int] = {"healthy": 0, "at_risk": 0, "critical": 0, "zombie": 0}
    total_value = 0.0
    scores: list[float] = []
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
    total = len(active_raw)

    metrics = PipelineMetrics(
        total_deals=total,
        total_value=total_value,
        average_health_score=round(avg, 1),
        healthy_count=counts["healthy"],
        at_risk_count=counts["at_risk"],
        critical_count=counts["critical"],
        zombie_count=counts["zombie"],
        deals_needing_action=action_needed,
    )

    # AI summary — single Groq call, stored alongside metrics so /pipeline-summary
    # never re-fetches or re-scores deals.
    prompt = (
        f"Pipeline snapshot: {total} active deals, avg health {avg:.1f}/100, "
        f"{counts['healthy']} healthy, {counts['at_risk']} at risk, "
        f"{counts['critical'] + counts['zombie']} critical, "
        f"${total_value:,.0f} total value, {action_needed} need immediate action.\n\n"
        "Write exactly 2 concise sentences (no bullet points, no markdown) summarising "
        "the pipeline health for a sales leader. Be direct and actionable. "
        "First sentence: overall state. Second sentence: top priority action."
    )
    try:
        groq_client = AsyncGroq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = await groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.4,
        )
        summary = resp.choices[0].message.content.strip()
    except Exception as exc:
        logger.warning("Pipeline summary AI call failed: %s", exc)
        summary = (
            f"Your pipeline of {total} deals averages {avg:.0f}/100 health with "
            f"{counts['critical'] + counts['zombie']} deals in critical state. "
            f"Prioritise the {action_needed} deals needing immediate action to protect revenue."
        )

    return {
        "metrics": metrics,
        "summary": summary,
        "expires_at": time.monotonic() + _PIPELINE_CACHE_TTL,
    }


async def _get_pipeline_cached(cache_key: str, access_token: str, is_demo: bool) -> dict:
    """
    Stale-while-revalidate:
    1. Cache miss → compute synchronously, store, return.
    2. Cache hit + fresh → return immediately.
    3. Cache hit + stale → return stale immediately, kick off background refresh.
    """
    entry = _pipeline_cache.get(cache_key)
    now = time.monotonic()

    if entry is None:
        # Cold start — must compute before we can respond
        data = await _compute_pipeline_data(access_token, is_demo)
        _pipeline_cache[cache_key] = data
        return data

    if now < entry["expires_at"]:
        # Fresh — serve immediately
        return entry

    # Stale — serve immediately and refresh in background
    if cache_key not in _PIPELINE_REFRESHING:
        _PIPELINE_REFRESHING.add(cache_key)

        async def _refresh():
            try:
                data = await _compute_pipeline_data(access_token, is_demo)
                _pipeline_cache[cache_key] = data
            except Exception as exc:
                logger.warning("Background pipeline cache refresh failed for %s: %s", cache_key, exc)
            finally:
                _PIPELINE_REFRESHING.discard(cache_key)

        asyncio.create_task(_refresh())

    return entry


@router.get("/metrics", response_model=PipelineMetrics)
async def get_pipeline_metrics(authorization: str = Header(...)):
    """
    Summary cards — cached 5 min with stale-while-revalidate background refresh.
    Numbers always match the pipeline table (same active-deal filter).
    """
    session = _decode_session(authorization)
    is_demo = _is_demo(session)
    cache_key = "demo" if is_demo else f"metrics:{session.get('user_id', 'zoho')}"
    entry = await _get_pipeline_cached(cache_key, session.get("access_token", ""), is_demo)
    return entry["metrics"]


@router.get("/pipeline-summary")
async def get_pipeline_summary(authorization: str = Header(...)):
    """
    2-sentence AI pipeline summary for the CEO/sales-rep card.
    Reads from the same cache entry as /metrics — no extra deal fetch or Groq call.
    """
    session = _decode_session(authorization)
    is_demo = _is_demo(session)
    cache_key = "demo" if is_demo else f"metrics:{session.get('user_id', 'zoho')}"
    entry = await _get_pipeline_cached(cache_key, session.get("access_token", ""), is_demo)
    m: PipelineMetrics = entry["metrics"]
    return {"summary": entry["summary"], "avg_score": m.average_health_score, "total": m.total_deals}


@router.get("/{deal_id}/health", response_model=DealHealthResult)
async def get_deal_health(deal_id: str, authorization: str = Header(...)):
    """Get full health score breakdown for a single deal."""
    session = _decode_session(authorization)
    demo = _is_demo(session) or deal_id.startswith("sim_")

    # Cache check — skip cache for demo (fast anyway)
    if not demo:
        # Try Redis first
        redis_key = _rkey("health", deal_id)
        redis_cached = await cache_get(redis_key)
        if redis_cached:
            logger.debug("health redis cache hit deal=%s", deal_id)
            from models.schemas import DealHealthResult
            try:
                return DealHealthResult(**redis_cached)
            except Exception:
                pass  # fall through to recompute if deserialization fails

        # Fallback: in-memory cache
        mem_cached = _health_cache.get(deal_id)
        if mem_cached:
            result, expires_at = mem_cached
            if datetime.now(timezone.utc).timestamp() < expires_at:
                logger.debug("health mem cache hit deal=%s", deal_id)
                return result

    if demo:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        try:
            raw = await asyncio.wait_for(
                get_fully_enriched_deal(session["access_token"], deal_id),
                timeout=15,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Zoho timed out fetching deal data")
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
            activity_data = await asyncio.wait_for(
                get_all_activity_for_deal(session["access_token"], deal_id),
                timeout=15,
            )
        except (asyncio.TimeoutError, Exception) as e:
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
            raw_tl = await asyncio.wait_for(
                fetch_deal_timeline(session["access_token"], deal_id),
                timeout=10,
            )
            timeline_analysis = analyze_timeline(raw_tl.get("timeline", []))
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning("Timeline fetch failed deal=%s: %s", deal_id, e)

    # Fetch Outlook emails to enrich health signals when rep didn't BCC Zoho
    outlook_emails: list = []
    if not demo:
        try:
            from services.outlook_enrichment import get_enriched_emails
            user_key = session.get("email") or session.get("user_id") or "default"
            outlook_emails = await asyncio.wait_for(
                get_enriched_emails(deal_id, session["access_token"], user_key, limit=20),
                timeout=8,
            )
            logger.info("health: deal=%s outlook_emails=%d", deal_id, len(outlook_emails))
        except Exception as e:
            logger.warning("health: Outlook enrichment failed deal=%s: %s", deal_id, e)

    # Score with best available signals (Outlook emails patch the activity summary)
    if activity_data and activity_data.get("summary") and timeline_analysis.get("total_entries"):
        from services.health_scorer import score_deal_with_timeline, enrich_signal_details
        result = score_deal_with_timeline(raw, activity_data, timeline_analysis, outlook_emails=outlook_emails or None)
    elif activity_data and activity_data.get("summary"):
        from services.health_scorer import score_deal_with_activities, enrich_signal_details
        result = score_deal_with_activities(raw, activity_data, outlook_emails=outlook_emails or None)
    else:
        from services.health_scorer import enrich_signal_details
        result = score_deal_from_zoho(raw, outlook_emails=outlook_emails or None)

    # Enrich signal details with cross-signal context
    activity_summary = (activity_data or {}).get("summary", {})
    days_silent = (
        timeline_analysis.get("days_since_last_human_activity")
        or activity_summary.get("days_since_any_activity")
    )
    if isinstance(days_silent, int) and days_silent >= 999:
        days_silent = None
    contact_count = activity_summary.get("total_contacts") or raw.get("contact_count", 1)
    last_email_subject = timeline_analysis.get("last_email_subject")

    enriched_signals = enrich_signal_details(
        result.signals,
        days_silent=days_silent,
        contact_count=contact_count,
        last_email_subject=last_email_subject,
        stage_name=raw.get("stage"),
    )

    # Generate AI analysis (non-blocking — returns {} on failure)
    ai_analysis: dict = {}
    try:
        from services.deal_health_ai import generate_deal_health_analysis
        deal_age_days = None
        if raw.get("created_time"):
            try:
                created = datetime.fromisoformat(raw["created_time"].replace("Z", "+00:00"))
                deal_age_days = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass

        ai_analysis = await generate_deal_health_analysis(
            deal_name=raw.get("name", "Unknown"),
            deal_stage=raw.get("stage", "Unknown"),
            deal_amount=raw.get("amount"),
            deal_age_days=deal_age_days,
            deal_owner=raw.get("owner"),
            contact_name=raw.get("contact_name"),
            signals=enriched_signals,
            health_label=result.health_label,
            total_score=result.total_score,
            timeline_analysis=timeline_analysis,
            activity_summary=activity_summary,
        )
    except Exception as e:
        logger.warning("deal_health_ai call failed for %s: %s", deal_id, e)

    # Parse recommended_actions into RecommendedAction models
    from models.schemas import RecommendedAction
    recommended_actions = None
    if ai_analysis.get("recommended_actions"):
        try:
            recommended_actions = [
                RecommendedAction(**a) for a in ai_analysis["recommended_actions"]
            ]
        except Exception:
            recommended_actions = None

    result = result.model_copy(update={
        "signals": enriched_signals,
        "analysis_summary": ai_analysis.get("analysis_summary"),
        "key_risk": ai_analysis.get("key_risk"),
        "root_cause": ai_analysis.get("root_cause"),
        "deal_status_assessment": ai_analysis.get("deal_status_assessment"),
        "win_probability_estimate": ai_analysis.get("win_probability_estimate"),
        "escalation_needed": ai_analysis.get("escalation_needed"),
        "recommended_actions": recommended_actions,
    })

    # Store in cache (Redis + in-memory fallback)
    if not demo:
        redis_key = _rkey("health", deal_id)
        await cache_set(redis_key, result.model_dump(), ttl=_HEALTH_CACHE_TTL)
        _health_cache[deal_id] = (result, datetime.now(timezone.utc).timestamp() + _HEALTH_CACHE_TTL)

    return result


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


# ── DB-backed endpoints ────────────────────────────────────────────────────────

@router.post("/{deal_id}/refresh")
async def force_refresh_deal(
    deal_id: str,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Bypass the cache for a single deal and re-fetch it from Zoho."""
    session = _decode_session(authorization)
    if _is_demo(session):
        raise HTTPException(status_code=400, detail="Cannot refresh demo deals")
    # Invalidate → next list fetch will pick it up fresh
    from services.deal_db import invalidate_deal
    await invalidate_deal(db, deal_id)
    # Also fetch inline so the caller gets fresh data immediately
    try:
        raw = await fetch_single_deal(session["access_token"], deal_id)
        if raw:
            from services.deal_db import upsert_deals
            await upsert_deals(db, [raw], session.get("email", ""))
        from services.cache_manager import get_cache_status
        from datetime import datetime, timezone
        return {
            "refreshed": True,
            "deal_id": deal_id,
            "_cache": get_cache_status(datetime.now(timezone.utc), "deals"),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Zoho fetch failed: {exc}")


@router.post("/sync")
async def force_sync_deals(
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Force a full Zoho refresh, bypassing the 5-minute cache."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"synced": 0, "message": "Demo mode — no sync needed"}
    try:
        raw_deals = await _fetch_all_zoho_deals(session["access_token"])
        from services.deal_db import upsert_deals
        await upsert_deals(db, raw_deals, session.get("email", ""))
        return {"synced": len(raw_deals), "message": f"Synced {len(raw_deals)} deals"}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}")


@router.get("/{deal_id}/score-history")
async def get_score_history(
    deal_id: str,
    days: int = Query(default=30, ge=1, le=90),
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Return health score history for trend charts (newest first)."""
    _decode_session(authorization)
    from services.score_db import get_score_history
    return {"deal_id": deal_id, "history": await get_score_history(db, deal_id, days=days)}


@router.get("/{deal_id}/decisions")
async def get_deal_decisions(
    deal_id: str,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    """Return ACK decision history for a deal."""
    _decode_session(authorization)
    from services.decision_db import get_deal_decisions
    return {"deal_id": deal_id, "decisions": await get_deal_decisions(db, deal_id)}

# ── Inline CRM field editing ───────────────────────────────────────────────────

ALLOWED_DEAL_FIELDS = {"Stage", "Amount", "Closing_Date", "Description"}


class UpdateDealFieldBody(BaseModel):
    field: str
    value: Union[str, float, int, None]


@router.put("/{deal_id}/update")
async def update_deal_field(
    deal_id: str,
    body: UpdateDealFieldBody,
    authorization: str = Header(...),
):
    """Update a single CRM field on a Zoho deal. Allowed: Stage, Amount, Closing_Date, Description."""
    session = _decode_session(authorization)

    if body.field not in ALLOWED_DEAL_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"field must be one of: {', '.join(sorted(ALLOWED_DEAL_FIELDS))}",
        )

    # Demo mode — mock success without calling Zoho
    if _is_demo(session):
        return {"success": True, "updated_field": body.field, "new_value": body.value}

    try:
        from services.zoho_client import update_deal_field as zoho_update_field
        success = await zoho_update_field(
            deal_id, body.field, body.value, session.get("access_token", "")
        )
        if success:
            # Invalidate health + metrics caches for this deal so next load is fresh
            await cache_delete_pattern(_rkey("health", deal_id))
            await cache_delete_pattern("dealiq:metrics:*")
            # Also evict in-memory fallback
            _health_cache.pop(deal_id, None)
            return {"success": True, "updated_field": body.field, "new_value": body.value}
        return {"success": False, "error": "Zoho returned a non-SUCCESS code"}
    except Exception as e:
        return {"success": False, "error": str(e)}
