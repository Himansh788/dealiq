from fastapi import APIRouter, Header, HTTPException, Query
import asyncio
import base64
import json
from typing import Optional
from datetime import datetime, timezone, timedelta


def get_current_quarter_label() -> str:
    """Returns e.g. 'Q1 2026' based on current UTC date."""
    now = datetime.utcnow()
    quarter = (now.month - 1) // 3 + 1
    return f"Q{quarter} {now.year}"
from pydantic import BaseModel
from services.forecast import compute_forecast
from services.ai_forecast_narrative import (
    generate_pipeline_narrative,
    generate_rep_coaching,
    generate_rescue_priorities,
    generate_rep_health_pattern,
)
from services.demo_data import SIMULATED_DEALS, DEMO_FORECAST_SUBMISSIONS, DEMO_FORECAST_QUOTA

router = APIRouter()

CLOSED_STAGES = {"Closed Won", "Closed Lost", "closed won", "closed lost"}


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


def _days_since(dt_str) -> Optional[int]:
    if not dt_str:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _enrich_and_score(raw: dict) -> dict:
    created = raw.get("created_time")
    last_activity = raw.get("last_activity_time")
    raw["days_in_stage"] = _days_since(created)
    raw["last_activity_days"] = _days_since(last_activity)
    raw["days_since_buyer_response"] = _days_since(last_activity)

    prob = raw.get("probability", 0) or 0
    if prob >= 90:    raw["activity_count_30d"] = 5
    elif prob >= 50:  raw["activity_count_30d"] = 3
    elif prob >= 20:  raw["activity_count_30d"] = 2
    else:             raw["activity_count_30d"] = 1

    raw["economic_buyer_engaged"] = prob >= 70
    raw["contact_count"] = 2 if prob >= 30 else 1
    raw["discount_mention_count"] = 0

    from services.health_scorer import score_deal_from_zoho
    result = score_deal_from_zoho(raw)
    raw["health_score"] = result.total_score
    raw["health_label"] = result.health_label
    return raw


@router.get("")
async def get_forecast(
    authorization: str = Header(...),
    include_closed: bool = Query(default=False),
    ai_insights: bool = Query(default=True),   # can disable for fast debug
):
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        raw_deals = list(SIMULATED_DEALS)
    else:
        try:
            from routers.deals import _fetch_all_zoho_deals
            raw_deals = await _fetch_all_zoho_deals(session["access_token"])
        except Exception:
            raw_deals = list(SIMULATED_DEALS)
            simulated = True

    if not include_closed:
        raw_deals = [d for d in raw_deals if d.get("stage") not in CLOSED_STAGES]

    seen, unique = set(), []
    for d in raw_deals:
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)

    scored = [_enrich_and_score(d) for d in unique]
    result = compute_forecast(scored, simulated=simulated)

    # Serialise by_rep for both the response and AI calls
    by_rep_dicts = [
        {
            "name": r.name,
            "deal_count": r.deal_count,
            "total_pipeline": r.total_pipeline,
            "crm_forecast": r.crm_forecast,
            "dealiq_forecast": r.dealiq_forecast,
            "avg_health_score": r.avg_health_score,
            "healthy_count": r.healthy_count,
            "at_risk_count": r.at_risk_count,
            "critical_count": r.critical_count,
            "zombie_count": r.zombie_count,
            "overconfidence_gap": r.overconfidence_gap,
            "top_deal": r.top_deal,
            "deals_by_health": r.deals_by_health,
        }
        for r in result.by_rep
    ]

    forecast_dict = {
        "total_pipeline": result.total_pipeline,
        "crm_forecast": result.crm_forecast,
        "dealiq_realistic": result.dealiq_realistic,
        "dealiq_optimistic": result.dealiq_optimistic,
        "dealiq_conservative": result.dealiq_conservative,
        "forecast_gap": result.forecast_gap,
        "gap_percentage": result.gap_percentage,
        "this_month_crm": result.this_month_crm,
        "this_month_dealiq": result.this_month_dealiq,
        "this_month_gap": result.this_month_gap,
        "deals_closing_this_month": result.deals_closing_this_month,
        "at_risk_this_month": result.at_risk_this_month,
        "by_rep": by_rep_dicts,
        "by_month": [
            {
                "month": m.month,
                "month_key": m.month_key,
                "deals_closing": m.deals_closing,
                "crm_value": m.crm_value,
                "dealiq_value": m.dealiq_value,
                "deals": m.deals,
            }
            for m in result.by_month
        ],
        "overforecasted_deals": result.overforecasted_deals,
        "rescue_opportunities": result.rescue_opportunities,
        "already_dead": result.already_dead,
        "total_rescue_potential": result.total_rescue_potential,
        "total_deals_analysed": result.total_deals_analysed,
        "simulated": result.simulated,
        "generated_at": result.generated_at,
    }

    # ── AI Intelligence layer — all calls run in parallel ─────────────────────
    ai = {"narrative": None, "rep_coaching": {}, "rescue_priorities": None}

    if ai_insights:
        try:
            # 1. Pipeline narrative + rescue priorities run in parallel
            narrative_task = generate_pipeline_narrative(forecast_dict)
            rescue_task = generate_rescue_priorities(
                result.rescue_opportunities,
                result.total_pipeline,
                result.this_month_gap,
            )

            # 2. Rep coaching — cap at 5 reps to limit parallel calls
            top_reps = by_rep_dicts[:5]
            coaching_tasks = [generate_rep_coaching(rep) for rep in top_reps]

            # Fire everything at once with a hard 60s timeout
            all_results = await asyncio.wait_for(
                asyncio.gather(
                    narrative_task,
                    rescue_task,
                    *coaching_tasks,
                    return_exceptions=True,
                ),
                timeout=60,
            )

            ai["narrative"] = all_results[0] if not isinstance(all_results[0], Exception) else None
            ai["rescue_priorities"] = all_results[1] if not isinstance(all_results[1], Exception) else None

            for i, rep in enumerate(top_reps):
                coaching = all_results[2 + i]
                if not isinstance(coaching, Exception):
                    ai["rep_coaching"][rep["name"]] = coaching

        except asyncio.TimeoutError:
            ai["error"] = "AI analysis timed out — pipeline data is accurate, narratives unavailable"
        except Exception as e:
            ai["error"] = str(e)

    forecast_dict["ai"] = ai
    return forecast_dict


# ── Separate endpoint for drill-down pattern analysis ────────────────────────
# Called lazily when user clicks a health badge — not on page load

@router.post("/rep-pattern")
async def get_rep_pattern(
    body: dict,
    authorization: str = Header(...),
):
    """
    Called when user clicks a health badge on a rep card.
    Returns AI pattern analysis for that specific group of deals.
    """
    _decode_session(authorization)  # just validate auth

    rep_name = body.get("rep_name", "")
    health_label = body.get("health_label", "")
    deals = body.get("deals", [])

    if not deals:
        return {"generated": False, "pattern": "", "insight": "No deals to analyse.", "action": ""}

    result = await generate_rep_health_pattern(rep_name, health_label, deals)
    return result


# ── Forecast Board — in-memory stores ─────────────────────────────────────────
#
# All state keyed by session token.  Ephemeral — resets on server restart,
# which is fine for an MVP; a DB layer can be added later.

_forecast_categories: dict = {}   # { token: { deal_id: "commit"|"best_case"|"pipeline"|"omit" } }
_forecast_submissions: dict = {}  # { token: [ ForecastSubmission dicts ] }
_quota_settings: dict = {}        # { token: { quarterly_quota: float, period_label: str } }

# Warnings cache: fetched once per board load, keyed by (token, deal_id)
_warnings_cache: dict = {}        # { token: { deal_id: { has_critical: bool } } }

_MAX_SUBMISSIONS = 12


def _get_token(authorization: str) -> str:
    """Extract raw token string (used as cache key)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    return authorization.replace("Bearer ", "").strip()


def _auto_bucket(stage: str) -> str:
    """Default category for a deal based on its CRM stage."""
    s = stage.lower().strip()
    # Closed deals — omit from board
    if any(kw in s for kw in ("closed won", "won", "closed lost", "lost", "churned")):
        return "omit"
    # High-intent stages → best_case (rep can promote to commit manually)
    if any(kw in s for kw in (
        "contract sent", "negotiations", "negotiation",
        "proposal", "price quote", "value proposition", "commercials",
    )):
        return "best_case"
    # Everything else (Followup, Demo Done, Evaluation, Qualification, Sales Approved, etc.)
    return "pipeline"


def _current_week_monday() -> str:
    today = datetime.now(timezone.utc).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _deal_to_board_item(deal: dict, category: str, warnings_for_token: dict) -> dict:
    deal_id = deal.get("id", "")
    w = warnings_for_token.get(deal_id, {})
    return {
        "id": deal_id,
        "name": deal.get("deal_name") or deal.get("name") or "Unnamed Deal",
        "company": deal.get("account_name") or deal.get("company") or "—",
        "amount": deal.get("amount") or 0,
        "stage": deal.get("stage") or "Unknown",
        "health_score": deal.get("health_score") or 0,
        "effective_category": category,
        "has_critical_warning": bool(w.get("has_critical", False)),
    }


# ── Pydantic bodies ────────────────────────────────────────────────────────────

class CategorizeBody(BaseModel):
    deal_id: str
    category: str


class SubmitForecastBody(BaseModel):
    commit_amount: float
    best_case_amount: float
    pipeline_amount: float
    notes: str = ""


class QuotaBody(BaseModel):
    quarterly_quota: float
    period_label: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/board")
async def get_forecast_board(authorization: str = Header(default="")):
    """
    Returns all deals bucketed into commit / best_case / pipeline,
    plus quota progress and last submission.
    """
    token = _get_token(authorization)
    session = _decode_session(authorization)
    is_demo = _is_demo(session)

    # Fetch deals
    if is_demo:
        deals = list(SIMULATED_DEALS)
        # Ensure health_score present on demo deals (they already have it)
        for d in deals:
            if "health_score" not in d:
                d["health_score"] = 50
    else:
        try:
            from services.zoho_client import fetch_deals, map_zoho_deal
            from services.health_scorer import score_deal_from_zoho
            raw = await fetch_deals(session.get("access_token", ""))
            deals = []
            for r in raw:
                d = map_zoho_deal(r)
                # Enrich with computed fields needed by health scorer
                d["days_in_stage"] = _days_since(d.get("created_time"))
                d["last_activity_days"] = _days_since(d.get("last_activity_time"))
                d["days_since_buyer_response"] = _days_since(d.get("last_activity_time"))
                prob = d.get("probability", 0) or 0
                d["activity_count_30d"] = 5 if prob >= 90 else 3 if prob >= 50 else 2 if prob >= 20 else 1
                d["economic_buyer_engaged"] = prob >= 70
                d["contact_count"] = 2 if prob >= 30 else 1
                d["discount_mention_count"] = 0
                result = score_deal_from_zoho(d)
                d["health_score"] = result.total_score
                deals.append(d)
        except Exception:
            deals = list(SIMULATED_DEALS)

    # Fetch warning summaries for all deals in one shot (best-effort)
    warnings_map: dict = _warnings_cache.get(token, {})
    try:
        from routers.warnings import DEMO_WARNINGS, _compute_warnings
        if is_demo:
            warnings_map = {d["id"]: DEMO_WARNINGS.get(d["id"], {}) for d in deals}
        else:
            warnings_map = {d["id"]: _compute_warnings(d) for d in deals}
        _warnings_cache[token] = warnings_map
    except Exception:
        pass

    # Resolve categories
    overrides = _forecast_categories.get(token, {})
    quota_cfg = _quota_settings.get(token, DEMO_FORECAST_QUOTA if is_demo else {"quarterly_quota": 0.0, "period_label": get_current_quarter_label()})

    buckets: dict[str, list] = {"commit": [], "best_case": [], "pipeline": []}

    for deal in deals:
        deal_id = deal.get("id", "")
        stage = deal.get("stage") or ""
        category = overrides.get(deal_id) or _auto_bucket(stage)
        if category == "omit":
            continue
        item = _deal_to_board_item(deal, category, warnings_map)
        buckets[category].append(item)

    commit_total    = sum(d["amount"] for d in buckets["commit"])
    best_case_total = sum(d["amount"] for d in buckets["best_case"])
    pipeline_total  = sum(d["amount"] for d in buckets["pipeline"])
    quarterly_quota = quota_cfg.get("quarterly_quota", 0.0)

    coverage_ratio = (
        (commit_total + best_case_total + pipeline_total) / quarterly_quota
        if quarterly_quota > 0 else 0.0
    )

    all_active_deals = buckets["commit"] + buckets["best_case"] + buckets["pipeline"]

    critical_count = sum(
        1 for d in all_active_deals
        if d["health_score"] < 40 or d.get("has_critical_warning", False)
    )
    at_risk_count = sum(
        1 for d in all_active_deals
        if 40 <= d["health_score"] < 60 and not d.get("has_critical_warning", False)
    )
    ai_risk_count = critical_count if critical_count > 0 else at_risk_count

    submissions = _forecast_submissions.get(token, DEMO_FORECAST_SUBMISSIONS if is_demo else [])
    last_submission = submissions[-1] if submissions else None

    return {
        "quota": quarterly_quota,
        "period_label": quota_cfg.get("period_label", get_current_quarter_label()),
        "categories": {
            "commit":    {"deals": buckets["commit"],    "total": commit_total},
            "best_case": {"deals": buckets["best_case"], "total": best_case_total},
            "pipeline":  {"deals": buckets["pipeline"],  "total": pipeline_total},
        },
        "last_submission": last_submission,
        "ai_risk_count": ai_risk_count,
        "critical_count": critical_count,
        "at_risk_count": at_risk_count,
        "total_pipeline_amount": sum(d["amount"] for d in all_active_deals),
        "coverage_ratio": coverage_ratio,
    }


@router.post("/categorize")
async def categorize_deal(body: CategorizeBody, authorization: str = Header(default="")):
    token = _get_token(authorization)
    allowed = {"commit", "best_case", "pipeline", "omit"}
    if body.category not in allowed:
        raise HTTPException(status_code=422, detail=f"category must be one of: {', '.join(allowed)}")
    if token not in _forecast_categories:
        _forecast_categories[token] = {}
    _forecast_categories[token][body.deal_id] = body.category
    return {"success": True, "deal_id": body.deal_id, "category": body.category}


@router.post("/submit")
async def submit_forecast(body: SubmitForecastBody, authorization: str = Header(default="")):
    token = _get_token(authorization)
    week_of = _current_week_monday()
    entry = {
        "week_of": week_of,
        "commit_amount": body.commit_amount,
        "best_case_amount": body.best_case_amount,
        "pipeline_amount": body.pipeline_amount,
        "notes": body.notes,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }
    if token not in _forecast_submissions:
        _forecast_submissions[token] = []
    _forecast_submissions[token].append(entry)
    if len(_forecast_submissions[token]) > _MAX_SUBMISSIONS:
        _forecast_submissions[token].pop(0)
    return {"success": True, "week_of": week_of, "submitted_at": entry["submitted_at"]}


@router.get("/submissions")
async def get_forecast_submissions(authorization: str = Header(default="")):
    token = _get_token(authorization)
    session = _decode_session(authorization)
    is_demo = _is_demo(session)
    submissions = _forecast_submissions.get(token, DEMO_FORECAST_SUBMISSIONS if is_demo else [])
    return {"submissions": submissions[-8:]}


@router.post("/quota")
async def set_quota(body: QuotaBody, authorization: str = Header(default="")):
    token = _get_token(authorization)
    if body.quarterly_quota <= 0:
        raise HTTPException(status_code=422, detail="quarterly_quota must be greater than 0")
    _quota_settings[token] = {
        "quarterly_quota": body.quarterly_quota,
        "period_label": body.period_label or get_current_quarter_label(),
    }
    return {"success": True, "quarterly_quota": body.quarterly_quota, "period_label": body.period_label}