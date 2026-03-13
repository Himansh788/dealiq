"""
Regional & Quarterly Target Analytics service.

Computes pipeline attainment vs targets per region per quarter.
Works with both real Zoho data and demo data.
"""
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Country → Region mapping for deriving region from Zoho deal account country
COUNTRY_REGION_MAP: Dict[str, str] = {
    # APAC
    "India": "APAC", "Japan": "APAC", "China": "APAC", "Australia": "APAC",
    "Singapore": "APAC", "South Korea": "APAC", "Indonesia": "APAC",
    "Malaysia": "APAC", "Thailand": "APAC", "Vietnam": "APAC", "Philippines": "APAC",
    "New Zealand": "APAC", "Hong Kong": "APAC", "Taiwan": "APAC",
    # EMEA
    "United Kingdom": "EMEA", "UK": "EMEA", "Germany": "EMEA", "France": "EMEA",
    "Netherlands": "EMEA", "Sweden": "EMEA", "Norway": "EMEA", "Denmark": "EMEA",
    "Finland": "EMEA", "Switzerland": "EMEA", "Austria": "EMEA", "Belgium": "EMEA",
    "Spain": "EMEA", "Italy": "EMEA", "Poland": "EMEA", "UAE": "EMEA",
    "Saudi Arabia": "EMEA", "Israel": "EMEA", "South Africa": "EMEA",
    "Ireland": "EMEA", "Portugal": "EMEA", "Czech Republic": "EMEA",
    # North America
    "United States": "North America", "US": "North America", "USA": "North America",
    "Canada": "North America", "Mexico": "North America",
    # LATAM
    "Brazil": "LATAM", "Argentina": "LATAM", "Colombia": "LATAM", "Chile": "LATAM",
    "Peru": "LATAM", "Venezuela": "LATAM", "Ecuador": "LATAM",
}

REGIONS = ["North America", "APAC", "EMEA", "LATAM"]

CLOSED_WON_STAGES = {"Closed Won", "Closed - Won", "closed won", "won"}
CLOSED_LOST_STAGES = {"Closed Lost", "Closed - Lost", "closed lost", "lost"}


def _get_region_from_deal(deal: Dict[str, Any]) -> str:
    """Extract region from deal. Tries explicit field first, then country mapping, then 'Unknown'."""
    region = deal.get("region") or deal.get("geo_region") or deal.get("GeoRegion__c")
    if region:
        return str(region).strip()

    country = deal.get("country") or deal.get("billing_country") or ""
    if country:
        mapped = COUNTRY_REGION_MAP.get(str(country).strip())
        if mapped:
            return mapped

    return "Unknown"


def _get_current_quarter() -> str:
    from datetime import datetime
    month = datetime.utcnow().month
    return f"Q{(month - 1) // 3 + 1}"


def _get_current_fy() -> int:
    from datetime import datetime
    return datetime.utcnow().year


def _score_deal(deal: Dict[str, Any]) -> tuple[int, str]:
    """Score a deal once; returns (total_score, health_label). Never raises."""
    try:
        from services.health_scorer import score_deal_from_zoho
        result = score_deal_from_zoho(deal)
        return result.total_score, result.health_label
    except Exception:
        return 50, "at_risk"


def compute_regional_summary(
    deals: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    quarter: str,
    fiscal_year: int,
) -> Dict[str, Any]:
    """
    Core computation: group deals by region, compute attainment vs targets.

    Returns dict with per-region stats + overall totals.
    """
    # Index targets by region
    target_map: Dict[str, float] = {}
    for t in targets:
        if t.get("quarter") == quarter and t.get("fiscal_year") == fiscal_year:
            target_map[t["region"]] = float(t.get("target_amount", 0))

    # Group deals by region
    region_deals: Dict[str, List[Dict]] = {r: [] for r in REGIONS}
    region_deals["Unknown"] = []

    for deal in deals:
        region = _get_region_from_deal(deal)
        if region not in region_deals:
            region_deals[region] = []
        region_deals[region].append(deal)

    region_stats = []
    total_pipeline = 0.0
    total_target = 0.0
    total_closed_won = 0.0
    regions_at_risk = 0

    for region in REGIONS:
        region_deal_list = region_deals.get(region, [])
        target = target_map.get(region, 0.0)

        pipeline_deals = []
        closed_won_deals = []
        stage_breakdown: Dict[str, int] = {}

        for d in region_deal_list:
            stage = (d.get("stage") or "").strip()
            stage_lower = stage.lower()
            stage_breakdown[stage] = stage_breakdown.get(stage, 0) + 1

            if stage_lower in {s.lower() for s in CLOSED_WON_STAGES}:
                closed_won_deals.append(d)
            elif stage_lower not in {s.lower() for s in CLOSED_LOST_STAGES}:
                pipeline_deals.append(d)

        closed_won_value = sum(float(d.get("amount") or 0) for d in closed_won_deals)
        pipeline_value = sum(float(d.get("amount") or 0) for d in pipeline_deals)
        achieved = closed_won_value
        total_pipeline_region = pipeline_value + closed_won_value

        attainment_pct = round((achieved / target * 100), 1) if target > 0 else 0.0
        gap = target - achieved

        if attainment_pct >= 90:
            status = "on_track"
        elif attainment_pct >= 60:
            status = "at_risk"
        else:
            status = "critical"

        if status in ("at_risk", "critical"):
            regions_at_risk += 1

        # Score each pipeline deal exactly once
        top_deals = []
        for d in pipeline_deals:
            score, label = _score_deal(d)
            amount = float(d.get("amount") or 0)
            top_deals.append({
                "id": d.get("id", ""),
                "name": d.get("name") or d.get("deal_name") or "Unnamed",
                "stage": d.get("stage", "Unknown"),
                "amount": amount,
                "health_score": score,
                "health_label": label,
                "recovery_potential": round(amount * score / 100, 0),
                "region": region,
                "owner": d.get("owner", ""),
                "account_name": d.get("account_name", ""),
                "closing_date": d.get("closing_date", ""),
            })

        top_deals.sort(key=lambda x: x["recovery_potential"], reverse=True)

        region_stats.append({
            "region": region,
            "target": target,
            "achieved": achieved,
            "pipeline_value": total_pipeline_region,
            "gap": gap,
            "attainment_pct": attainment_pct,
            "status": status,
            "deal_count": len(region_deal_list),
            "pipeline_deal_count": len(pipeline_deals),
            "closed_won_count": len(closed_won_deals),
            "stage_breakdown": stage_breakdown,
            "top_deals": top_deals[:5],
        })

        total_target += target
        total_pipeline += total_pipeline_region
        total_closed_won += achieved

    total_attainment = round((total_closed_won / total_target * 100), 1) if total_target > 0 else 0.0

    return {
        "quarter": quarter,
        "fiscal_year": fiscal_year,
        "regions": region_stats,
        "total_pipeline": total_pipeline,
        "total_target": total_target,
        "total_achieved": total_closed_won,
        "total_gap": total_target - total_closed_won,
        "total_attainment_pct": total_attainment,
        "regions_at_risk": regions_at_risk,
    }


def get_gap_closing_deals(
    deals: List[Dict[str, Any]],
    underperforming_regions: List[str],
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Return deals in underperforming regions sorted by recovery potential (amount x health_score).
    Only includes active pipeline deals (not closed).
    """
    result = []
    for d in deals:
        region = _get_region_from_deal(d)
        if region not in underperforming_regions:
            continue
        stage = (d.get("stage") or "").lower()
        if stage in {s.lower() for s in CLOSED_WON_STAGES | CLOSED_LOST_STAGES}:
            continue

        amount = float(d.get("amount") or 0)
        if amount <= 0:
            continue

        score, label = _score_deal(d)
        result.append({
            "id": d.get("id", ""),
            "name": d.get("name") or d.get("deal_name") or "Unnamed",
            "stage": d.get("stage", "Unknown"),
            "amount": amount,
            "health_score": score,
            "health_label": label,
            "recovery_potential": round(amount * score / 100, 0),
            "region": region,
            "owner": d.get("owner", ""),
            "account_name": d.get("account_name", ""),
            "closing_date": d.get("closing_date", ""),
        })

    result.sort(key=lambda x: x["recovery_potential"], reverse=True)
    return result[:limit]
