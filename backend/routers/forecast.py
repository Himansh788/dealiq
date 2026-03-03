from fastapi import APIRouter, Header, HTTPException, Query
import asyncio
import base64
import json
from typing import Optional
from services.forecast import compute_forecast
from services.ai_forecast_narrative import (
    generate_pipeline_narrative,
    generate_rep_coaching,
    generate_rescue_priorities,
    generate_rep_health_pattern,
)
from services.demo_data import SIMULATED_DEALS

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

            # 2. Rep coaching — all reps in parallel (no arbitrary cap)
            top_reps = by_rep_dicts
            coaching_tasks = [generate_rep_coaching(rep) for rep in top_reps]

            # Fire everything at once
            all_results = await asyncio.gather(
                narrative_task,
                rescue_task,
                *coaching_tasks,
                return_exceptions=True,
            )

            ai["narrative"] = all_results[0] if not isinstance(all_results[0], Exception) else None
            ai["rescue_priorities"] = all_results[1] if not isinstance(all_results[1], Exception) else None

            for i, rep in enumerate(top_reps):
                coaching = all_results[2 + i]
                if not isinstance(coaching, Exception):
                    ai["rep_coaching"][rep["name"]] = coaching

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