"""
Regional & Quarterly Target Analytics router.

Endpoints:
  GET  /analytics/regional-summary      — all regions attainment
  GET  /analytics/region-deals          — gap deals for a region (?region=SEA/Oceania)
  GET  /analytics/gap-deals             — priority deals across underperforming regions
  GET  /analytics/component-ids         — Zoho Analytics discovery (debug)
"""
import base64
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()

REGIONS = ["Americas", "MENA", "SEA/Oceania", "EU", "ASIA"]

# Region → Zoho CRM territory/country values used to classify deals
REGION_TERRITORY_MAP = {
    "Americas":    ["Americas", "North America", "AMER", "United States", "US", "USA",
                    "Canada", "Mexico", "Brazil", "Latin America", "LATAM"],
    "MENA":        ["MENA", "Middle East", "UAE", "Saudi Arabia", "Qatar", "Kuwait",
                    "Bahrain", "Oman", "Jordan", "Egypt", "North Africa"],
    "SEA/Oceania": ["SEA", "SEA/Oceania", "Southeast Asia", "Singapore", "Malaysia",
                    "Indonesia", "Thailand", "Philippines", "Vietnam", "Australia",
                    "New Zealand", "Oceania", "APAC"],
    "EU":          ["EU", "Europe", "EMEA", "United Kingdom", "UK", "Germany", "France",
                    "Netherlands", "Sweden", "Spain", "Italy", "Poland", "Switzerland"],
    "ASIA":        ["ASIA", "Asia", "India", "Japan", "China", "South Korea",
                    "Hong Kong", "Taiwan"],
}


# ── Auth helpers ───────────────────────────────────────────────────────────────

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


def _current_quarter() -> str:
    from datetime import datetime
    return f"Q{(datetime.utcnow().month - 1) // 3 + 1}"


def _current_fy() -> int:
    from datetime import datetime
    return datetime.utcnow().year


# ── Region classifier ─────────────────────────────────────────────────────────

def _classify_region(deal: dict) -> str:
    """Map a Zoho deal to one of the 5 regions."""
    # Try explicit region/territory field first
    for field in ("region", "geo_region", "territory", "Territory", "Region__c"):
        val = (deal.get(field) or "").strip()
        if val:
            for region, aliases in REGION_TERRITORY_MAP.items():
                if any(val.lower() == a.lower() for a in aliases):
                    return region

    # Fall back to country/billing_country
    country = (deal.get("country") or deal.get("billing_country") or "").strip()
    if country:
        for region, aliases in REGION_TERRITORY_MAP.items():
            if any(country.lower() == a.lower() for a in aliases):
                return region

    return "Unknown"


def _classify_status(pct: float) -> str:
    if pct >= 90:
        return "on_track"
    if pct >= 60:
        return "at_risk"
    return "critical"


CLOSED_WON = {"closed won", "closed - won", "won"}
CLOSED_LOST = {"closed lost", "closed - lost", "lost"}


# ── Core computation from real Zoho deals ────────────────────────────────────

def _compute_from_deals(deals: list, targets: list, quarter: str, fiscal_year: int) -> dict:
    """Compute regional attainment from real Closed Won deals + target map."""
    target_map = {t["region"]: float(t["target_amount"]) for t in targets}

    # Bucket deals by region
    buckets: dict[str, list] = {r: [] for r in REGIONS}
    for d in deals:
        r = _classify_region(d)
        if r in buckets:
            buckets[r].append(d)

    region_stats = []
    total_target = total_achieved = 0.0
    regions_at_risk = 0

    for region in REGIONS:
        rdeal = buckets[region]
        target = target_map.get(region, 0.0)

        closed_won = [d for d in rdeal if (d.get("stage") or "").strip().lower() in CLOSED_WON]
        pipeline = [d for d in rdeal if (d.get("stage") or "").strip().lower() not in CLOSED_WON | CLOSED_LOST]

        achieved = sum(float(d.get("amount") or 0) for d in closed_won)
        gap = target - achieved
        pct = round(achieved / target * 100, 1) if target > 0 else 0.0
        status = _classify_status(pct)
        if status in ("at_risk", "critical"):
            regions_at_risk += 1

        total_target += target
        total_achieved += achieved

        # Top pipeline deals sorted by amount for gap-closing
        top_deals = sorted(pipeline, key=lambda d: float(d.get("amount") or 0), reverse=True)[:5]

        region_stats.append({
            "region": region,
            "target": target,
            "achieved": achieved,
            "gap": gap,
            "attainment_pct": pct,
            "status": status,
            "deal_count": len(rdeal),
            "closed_won_count": len(closed_won),
            "pipeline_deal_count": len(pipeline),
            "source": "zoho_crm",
        })

    return {
        "quarter": quarter,
        "fiscal_year": fiscal_year,
        "regions": region_stats,
        "total_target": total_target,
        "total_achieved": total_achieved,
        "total_gap": total_target - total_achieved,
        "total_attainment_pct": round(total_achieved / total_target * 100, 1) if total_target > 0 else 0.0,
        "regions_at_risk": regions_at_risk,
        "simulated": False,
    }


def _build_demo_summary(quarter: str, fiscal_year: int) -> dict:
    from services.demo_data import get_demo_regional_targets, DEMO_ZOHO_ACHIEVED

    targets = get_demo_regional_targets(quarter=quarter, fiscal_year=fiscal_year)
    target_map = {t["region"]: float(t["target_amount"]) for t in targets}

    region_stats = []
    total_target = total_achieved = 0.0
    regions_at_risk = 0

    for region in REGIONS:
        target = target_map.get(region, 0.0)
        achieved = DEMO_ZOHO_ACHIEVED.get(region, 0.0) if (quarter == "Q1" and fiscal_year == 2026) else round(target * 0.4, 2)
        gap = target - achieved
        pct = round(achieved / target * 100, 1) if target > 0 else 0.0
        status = _classify_status(pct)
        if status in ("at_risk", "critical"):
            regions_at_risk += 1
        total_target += target
        total_achieved += achieved
        region_stats.append({
            "region": region, "target": target, "achieved": achieved,
            "gap": gap, "attainment_pct": pct, "status": status,
            "deal_count": 0, "closed_won_count": 0, "pipeline_deal_count": 0,
            "source": "demo",
        })

    return {
        "quarter": quarter, "fiscal_year": fiscal_year,
        "regions": region_stats,
        "total_target": total_target, "total_achieved": total_achieved,
        "total_gap": total_target - total_achieved,
        "total_attainment_pct": round(total_achieved / total_target * 100, 1) if total_target > 0 else 0.0,
        "regions_at_risk": regions_at_risk, "simulated": True,
    }


async def _build_live_summary(session: dict, quarter: str, fiscal_year: int) -> dict:
    """
    Build summary for real (non-demo) users.

    Uses hardcoded achieved values from the Zoho Analytics dashboard for Q1 2026
    (the Zoho Analytics API is internal-only and not accessible via OAuth).
    For other quarters, falls back to Closed Won deal computation.
    """
    from services.demo_data import get_demo_regional_targets, DEMO_ZOHO_ACHIEVED

    targets = get_demo_regional_targets(quarter=quarter, fiscal_year=fiscal_year)
    target_map = {t["region"]: float(t["target_amount"]) for t in targets}

    # Q1 2026: use the verified real numbers from the Zoho Analytics dashboard
    if quarter == "Q1" and fiscal_year == 2026:
        region_stats = []
        total_target = total_achieved = 0.0
        regions_at_risk = 0
        for region in REGIONS:
            target = target_map.get(region, 0.0)
            achieved = DEMO_ZOHO_ACHIEVED.get(region, 0.0)
            gap = target - achieved
            pct = round(achieved / target * 100, 1) if target > 0 else 0.0
            status = _classify_status(pct)
            if status in ("at_risk", "critical"):
                regions_at_risk += 1
            total_target += target
            total_achieved += achieved
            region_stats.append({
                "region": region, "target": target, "achieved": achieved,
                "gap": gap, "attainment_pct": pct, "status": status,
                "deal_count": 0, "closed_won_count": 0, "pipeline_deal_count": 0,
                "source": "zoho_dashboard",
            })
        return {
            "quarter": quarter, "fiscal_year": fiscal_year,
            "regions": region_stats,
            "total_target": total_target, "total_achieved": total_achieved,
            "total_gap": total_target - total_achieved,
            "total_attainment_pct": round(total_achieved / total_target * 100, 1) if total_target > 0 else 0.0,
            "regions_at_risk": regions_at_risk, "simulated": False,
        }

    # Other quarters: compute from Closed Won deals in Zoho CRM
    try:
        from routers.deals import _fetch_all_zoho_deals
        deals = await _fetch_all_zoho_deals(session["access_token"])
        return _compute_from_deals(deals, targets, quarter, fiscal_year)
    except Exception as e:
        logger.warning("_build_live_summary failed: %s — falling back to demo", e)
        return _build_demo_summary(quarter, fiscal_year)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/regional-summary")
async def get_regional_summary(
    authorization: str = Header(...),
    quarter: Optional[str] = Query(default=None),
    fy: Optional[int] = Query(default=None),
):
    session = _decode_session(authorization)
    demo = _is_demo(session)
    q = (quarter or _current_quarter()).upper()
    fiscal_year = fy or _current_fy()

    if demo:
        return _build_demo_summary(q, fiscal_year)
    return await _build_live_summary(session, q, fiscal_year)


@router.get("/region-deals")
async def get_region_deals(
    authorization: str = Header(...),
    region: str = Query(...),
    quarter: Optional[str] = Query(default=None),
    fy: Optional[int] = Query(default=None),
):
    """Returns gap-closing deals for a specific region. Uses query param to avoid slash issues."""
    session = _decode_session(authorization)
    demo = _is_demo(session)
    q = (quarter or _current_quarter()).upper()
    fiscal_year = fy or _current_fy()

    if demo:
        from services.demo_data import DEMO_GAP_DEALS
        deals = [d for d in DEMO_GAP_DEALS if d["region"] == region]
    else:
        try:
            from routers.deals import _fetch_all_zoho_deals
            from services.regional_analytics import get_gap_closing_deals
            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            # Filter to the requested region using same classifier
            region_deals = [d for d in all_deals if _classify_region(d) == region]
            deals = get_gap_closing_deals(region_deals, [region])
        except Exception as e:
            logger.warning("region-deals failed: %s", e)
            deals = []

    return {"region": region, "quarter": q, "fiscal_year": fiscal_year,
            "deals": deals, "simulated": demo}


@router.get("/gap-deals")
async def get_gap_deals(
    authorization: str = Header(...),
    quarter: Optional[str] = Query(default=None),
    fy: Optional[int] = Query(default=None),
):
    session = _decode_session(authorization)
    demo = _is_demo(session)
    q = (quarter or _current_quarter()).upper()
    fiscal_year = fy or _current_fy()

    summary = _build_demo_summary(q, fiscal_year) if demo else await _build_live_summary(session, q, fiscal_year)

    underperforming = [r["region"] for r in summary["regions"] if r["status"] in ("at_risk", "critical")]

    if demo:
        from services.demo_data import DEMO_GAP_DEALS
        deals = [d for d in DEMO_GAP_DEALS if d["region"] in underperforming]
    else:
        try:
            from routers.deals import _fetch_all_zoho_deals
            from services.regional_analytics import get_gap_closing_deals
            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            gap_deals_input = [d for d in all_deals if _classify_region(d) in underperforming]
            deals = get_gap_closing_deals(gap_deals_input, underperforming)
        except Exception as e:
            logger.warning("gap-deals fetch failed: %s", e)
            deals = []

    return {"quarter": q, "fiscal_year": fiscal_year,
            "underperforming_regions": underperforming, "deals": deals, "simulated": demo}


@router.get("/component-ids")
async def get_component_ids(authorization: str = Header(...)):
    """Debug: list Zoho Analytics dashboard components to discover gauge IDs."""
    from services.zoho_analytics import REGIONAL_COMPONENTS, DASHBOARD_ID
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"dashboard_id": DASHBOARD_ID,
                "configured_components": [{"component_id": k, "region": v} for k, v in REGIONAL_COMPONENTS.items()],
                "simulated": True}
    try:
        from services.zoho_analytics import fetch_dashboard_components
        components = await fetch_dashboard_components(session["access_token"])
        return {"dashboard_id": DASHBOARD_ID, "dashboard_components": components,
                "configured_components": [{"component_id": k, "region": v} for k, v in REGIONAL_COMPONENTS.items()]}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
