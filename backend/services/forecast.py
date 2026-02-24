"""
DealIQ Forecast Engine
======================
The core insight: CRM forecasts are lies.
Reps enter probability based on gut feel and manager pressure.
DealIQ computes forecast from health signals — actual buyer behaviour.

Three forecast numbers:
  - CRM Forecast:    What reps entered (Amount × Probability)
  - DealIQ Realistic: Health-adjusted expected value
  - DealIQ Optimistic: If at-risk deals are rescued in time

The gap between CRM and DealIQ is where revenue is being lost.
"""

from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


HEALTH_CONFIDENCE: Dict[str, float] = {
    "healthy":  0.85,   # High confidence, some deals always slip at the last minute
    "at_risk":  0.45,   # Meaningful risk, roughly coin-flip adjusted for value
    "critical": 0.15,   # Likely to die, small chance of rescue
    "zombie":   0.03,   # Almost certainly dead, keep it low not zero (miracles happen)
}

# Stage maturity weight — later stages should close sooner
STAGE_MATURITY: Dict[str, float] = {
    "Negotiation/Review":     1.0,
    "Contract sent":          1.0,
    "Commercials - Proposal": 0.85,
    "Proposal/Price Quote":   0.80,
    "Sales Approved Deal":    0.75,
    "Demo Done":              0.55,
    "Evaluation":             0.50,
    "Followup":               0.40,
    "Value Proposition":      0.45,
    "Needs Analysis":         0.30,
    "Qualification":          0.20,
}


@dataclass
class ScoredDeal:
    id: str
    name: str
    account_name: str
    stage: str
    owner: str
    amount: float
    closing_date: Optional[str]
    crm_probability: float          # What the rep entered in Zoho
    health_score: int               # DealIQ 0–100 score
    health_label: str               # healthy / at_risk / critical / zombie

    # Computed
    crm_expected_value: float = 0.0       # amount × crm_probability
    dealiq_expected_value: float = 0.0    # amount × health_confidence × stage_maturity
    confidence_multiplier: float = 0.0
    stage_maturity: float = 0.0
    days_to_close: Optional[int] = None
    is_overdue: bool = False
    closing_this_month: bool = False
    closing_next_month: bool = False
    forecast_gap: float = 0.0             # crm_expected - dealiq_expected (positive = rep is overconfident)
    risk_flag: Optional[str] = None       # Human-readable reason this deal is dragging forecast


@dataclass
class RepDealSummary:
    id: str
    name: str
    amount: float
    stage: str
    health_score: int
    closing_date: Optional[str]

@dataclass
class RepForecast:
    name: str
    deal_count: int
    total_pipeline: float
    crm_forecast: float
    dealiq_forecast: float
    avg_health_score: float
    healthy_count: int
    at_risk_count: int
    critical_count: int
    zombie_count: int
    overconfidence_gap: float           # How much they're over-forecasting
    top_deal: Optional[str] = None      # Their biggest healthy deal
    deals_by_health: Dict[str, list] = field(default_factory=dict)  # deal lists per health label


@dataclass
class MonthlyProjection:
    month: str                  # "Feb 2026"
    month_key: str              # "2026-02"
    deals_closing: int
    crm_value: float
    dealiq_value: float
    deals: List[str] = field(default_factory=list)


@dataclass
class ForecastResult:
    # Top-line numbers
    total_pipeline: float
    crm_forecast: float                 # Sum of (amount × crm_probability)
    dealiq_realistic: float             # Sum of (amount × health_confidence × stage_maturity)
    dealiq_optimistic: float            # If all at_risk deals are rescued
    dealiq_conservative: float          # Only healthy deals, deeply discounted

    # Gap analysis
    forecast_gap: float                 # crm_forecast - dealiq_realistic (the "lie")
    gap_percentage: float               # How wrong the CRM forecast is as a %

    # This month specifically
    this_month_crm: float
    this_month_dealiq: float
    this_month_gap: float
    deals_closing_this_month: int
    at_risk_this_month: int             # Deals closing this month with critical/zombie health

    # Breakdowns
    by_rep: List[RepForecast]
    by_month: List[MonthlyProjection]

    # Deal-level intelligence
    overforecasted_deals: List[Dict]    # Deals where rep is most overconfident
    rescue_opportunities: List[Dict]    # At-risk deals closing soon that could be saved
    already_dead: List[Dict]            # Zombie deals still showing in CRM forecast

    # Meta
    total_deals_analysed: int
    simulated: bool
    generated_at: str


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except Exception:
        try:
            return date.fromisoformat(date_str[:10])
        except Exception:
            return None


def _days_to_close(closing_date_str: Optional[str]) -> Optional[int]:
    d = _parse_date(closing_date_str)
    if d is None:
        return None
    return (d - date.today()).days


def _score_single_deal(raw: Dict[str, Any]) -> ScoredDeal:
    """Convert a raw deal dict (with health_score already computed) into a ScoredDeal."""
    amount = float(raw.get("amount") or 0)
    crm_prob = float(raw.get("probability") or 0) / 100.0  # Convert % to decimal
    health_label = raw.get("health_label", "critical")
    health_score = int(raw.get("health_score") or 0)
    stage = raw.get("stage", "Unknown")
    closing_date = raw.get("closing_date")

    confidence = HEALTH_CONFIDENCE.get(health_label, 0.10)
    maturity = STAGE_MATURITY.get(stage, 0.40)

    crm_expected = amount * crm_prob
    dealiq_expected = amount * confidence * maturity

    days = _days_to_close(closing_date)
    today = date.today()
    closing_d = _parse_date(closing_date)

    is_overdue = days is not None and days < 0
    closing_this_month = (
        closing_d is not None and
        closing_d.year == today.year and
        closing_d.month == today.month
    )

    # Next month
    next_month = today.month + 1 if today.month < 12 else 1
    next_year = today.year if today.month < 12 else today.year + 1
    closing_next_month = (
        closing_d is not None and
        closing_d.year == next_year and
        closing_d.month == next_month
    )

    forecast_gap = crm_expected - dealiq_expected

    # Build risk flag for overforecasted / zombie deals
    risk_flag = None
    if health_label == "zombie" and crm_prob > 0.3:
        risk_flag = f"Zombie deal showing {int(crm_prob * 100)}% probability in CRM — effectively ₹0"
    elif health_label == "critical" and crm_prob > 0.6:
        risk_flag = f"Critical health but {int(crm_prob * 100)}% probability entered — overconfident"
    elif is_overdue and health_label in ("critical", "zombie"):
        risk_flag = f"Closing date passed {abs(days)} days ago, still in pipeline"
    elif crm_expected > dealiq_expected * 3:
        risk_flag = "CRM value 3x higher than DealIQ estimate — significant overforecast"

    owner = raw.get("owner", "Unknown")
    if isinstance(owner, dict):
        owner = owner.get("name", "Unknown")

    return ScoredDeal(
        id=raw.get("id", ""),
        name=raw.get("name", raw.get("deal_name", "Unknown")),
        account_name=raw.get("account_name") or "—",
        stage=stage,
        owner=owner,
        amount=amount,
        closing_date=closing_date,
        crm_probability=crm_prob,
        health_score=health_score,
        health_label=health_label,
        crm_expected_value=round(crm_expected, 2),
        dealiq_expected_value=round(dealiq_expected, 2),
        confidence_multiplier=confidence,
        stage_maturity=maturity,
        days_to_close=days,
        is_overdue=is_overdue,
        closing_this_month=closing_this_month,
        closing_next_month=closing_next_month,
        forecast_gap=round(forecast_gap, 2),
        risk_flag=risk_flag,
    )


def compute_forecast(scored_deals: List[Dict[str, Any]], simulated: bool = False) -> ForecastResult:
    """
    Main forecast computation.
    Expects deals that already have health_score and health_label computed.
    """
    deals = [_score_single_deal(d) for d in scored_deals]

    # ── Top-line numbers ──────────────────────────────────────────────────────
    total_pipeline = sum(d.amount for d in deals)
    crm_forecast = sum(d.crm_expected_value for d in deals)
    dealiq_realistic = sum(d.dealiq_expected_value for d in deals)

    # Optimistic: rescue all at_risk deals (bump them to healthy confidence)
    optimistic_extra = sum(
        d.amount * (HEALTH_CONFIDENCE["healthy"] - HEALTH_CONFIDENCE["at_risk"]) * d.stage_maturity
        for d in deals if d.health_label == "at_risk"
    )
    dealiq_optimistic = dealiq_realistic + optimistic_extra

    # Conservative: only healthy deals, further discounted
    dealiq_conservative = sum(
        d.amount * 0.70 * d.stage_maturity
        for d in deals if d.health_label == "healthy"
    )

    forecast_gap = crm_forecast - dealiq_realistic
    gap_pct = (forecast_gap / crm_forecast * 100) if crm_forecast > 0 else 0

    # ── This month ───────────────────────────────────────────────────────────
    this_month_deals = [d for d in deals if d.closing_this_month]
    this_month_crm = sum(d.crm_expected_value for d in this_month_deals)
    this_month_dealiq = sum(d.dealiq_expected_value for d in this_month_deals)
    at_risk_this_month = sum(
        1 for d in this_month_deals
        if d.health_label in ("critical", "zombie")
    )

    # ── By rep ───────────────────────────────────────────────────────────────
    rep_map: Dict[str, List[ScoredDeal]] = {}
    for d in deals:
        rep_map.setdefault(d.owner, []).append(d)

    by_rep = []
    for rep_name, rep_deals in sorted(rep_map.items()):
        health_counts = {"healthy": 0, "at_risk": 0, "critical": 0, "zombie": 0}
        for d in rep_deals:
            health_counts[d.health_label] = health_counts.get(d.health_label, 0) + 1

        top_deal = max(
            (d for d in rep_deals if d.health_label == "healthy"),
            key=lambda d: d.amount,
            default=None,
        )

        rep_crm = sum(d.crm_expected_value for d in rep_deals)
        rep_dealiq = sum(d.dealiq_expected_value for d in rep_deals)
        avg_health = sum(d.health_score for d in rep_deals) / len(rep_deals) if rep_deals else 0

        # Build deal list per health label for drill-down
        deals_by_health = {}
        for label in ("healthy", "at_risk", "critical", "zombie"):
            label_deals = sorted(
                [d for d in rep_deals if d.health_label == label],
                key=lambda d: d.amount, reverse=True
            )
            if label_deals:
                deals_by_health[label] = [
                    {"id": d.id, "name": d.name, "amount": d.amount,
                     "stage": d.stage, "health_score": d.health_score,
                     "closing_date": d.closing_date}
                    for d in label_deals
                ]

        by_rep.append(RepForecast(
            name=rep_name,
            deal_count=len(rep_deals),
            total_pipeline=round(sum(d.amount for d in rep_deals), 2),
            crm_forecast=round(rep_crm, 2),
            dealiq_forecast=round(rep_dealiq, 2),
            avg_health_score=round(avg_health, 1),
            healthy_count=health_counts["healthy"],
            at_risk_count=health_counts["at_risk"],
            critical_count=health_counts["critical"],
            zombie_count=health_counts["zombie"],
            overconfidence_gap=round(rep_crm - rep_dealiq, 2),
            top_deal=top_deal.name if top_deal else None,
            deals_by_health=deals_by_health,
        ))

    # Sort reps by overconfidence gap descending (biggest liars first)
    by_rep.sort(key=lambda r: r.overconfidence_gap, reverse=True)

    # ── By month ─────────────────────────────────────────────────────────────
    month_map: Dict[str, List[ScoredDeal]] = {}
    for d in deals:
        cd = _parse_date(d.closing_date)
        if cd:
            key = f"{cd.year}-{cd.month:02d}"
            month_map.setdefault(key, []).append(d)

    by_month = []
    for key in sorted(month_map.keys())[:6]:   # Next 6 months
        year, month = int(key.split("-")[0]), int(key.split("-")[1])
        month_name = datetime(year, month, 1).strftime("%b %Y")
        month_deals = month_map[key]
        by_month.append(MonthlyProjection(
            month=month_name,
            month_key=key,
            deals_closing=len(month_deals),
            crm_value=round(sum(d.crm_expected_value for d in month_deals), 2),
            dealiq_value=round(sum(d.dealiq_expected_value for d in month_deals), 2),
            deals=[d.name for d in month_deals[:5]],  # Top 5 deal names
        ))

    # ── Deal-level alerts ────────────────────────────────────────────────────
    # Overforecasted: biggest gap between CRM and DealIQ
    overforecasted = sorted(
        [d for d in deals if d.forecast_gap > 500],
        key=lambda d: d.forecast_gap,
        reverse=True
    )[:8]

    overforecasted_out = [
        {
            "id": d.id,
            "name": d.name,
            "account_name": d.account_name,
            "owner": d.owner,
            "amount": d.amount,
            "stage": d.stage,
            "crm_expected": d.crm_expected_value,
            "dealiq_expected": d.dealiq_expected_value,
            "gap": d.forecast_gap,
            "health_label": d.health_label,
            "health_score": d.health_score,
            "risk_flag": d.risk_flag,
            "closing_date": d.closing_date,
        }
        for d in overforecasted
    ]

    # Rescue opportunities: at_risk/critical deals closing in next 60 days with decent amount
    rescue = sorted(
        [
            d for d in deals
            if d.health_label in ("at_risk", "critical")
            and d.days_to_close is not None
            and -5 <= d.days_to_close <= 60
            and d.amount >= 1000
        ],
        key=lambda d: d.amount,
        reverse=True
    )[:8]

    rescue_out = [
        {
            "id": d.id,
            "name": d.name,
            "account_name": d.account_name,
            "owner": d.owner,
            "amount": d.amount,
            "stage": d.stage,
            "health_label": d.health_label,
            "health_score": d.health_score,
            "days_to_close": d.days_to_close,
            "closing_date": d.closing_date,
            "potential_value": round(d.amount * HEALTH_CONFIDENCE["healthy"] * d.stage_maturity, 0),
            "current_dealiq_value": d.dealiq_expected_value,
            "rescue_upside": round(
                d.amount * (HEALTH_CONFIDENCE["healthy"] - d.confidence_multiplier) * d.stage_maturity, 0
            ),
        }
        for d in rescue
    ]

    # Already dead: zombie deals with significant CRM forecast
    dead = sorted(
        [d for d in deals if d.health_label == "zombie" and d.crm_expected_value > 100],
        key=lambda d: d.crm_expected_value,
        reverse=True
    )[:8]

    dead_out = [
        {
            "id": d.id,
            "name": d.name,
            "account_name": d.account_name,
            "owner": d.owner,
            "amount": d.amount,
            "stage": d.stage,
            "health_score": d.health_score,
            "crm_expected": d.crm_expected_value,
            "days_to_close": d.days_to_close,
            "closing_date": d.closing_date,
            "is_overdue": d.is_overdue,
        }
        for d in dead
    ]

    return ForecastResult(
        total_pipeline=round(total_pipeline, 2),
        crm_forecast=round(crm_forecast, 2),
        dealiq_realistic=round(dealiq_realistic, 2),
        dealiq_optimistic=round(dealiq_optimistic, 2),
        dealiq_conservative=round(dealiq_conservative, 2),
        forecast_gap=round(forecast_gap, 2),
        gap_percentage=round(gap_pct, 1),
        this_month_crm=round(this_month_crm, 2),
        this_month_dealiq=round(this_month_dealiq, 2),
        this_month_gap=round(this_month_crm - this_month_dealiq, 2),
        deals_closing_this_month=len(this_month_deals),
        at_risk_this_month=at_risk_this_month,
        by_rep=by_rep,
        by_month=by_month,
        overforecasted_deals=overforecasted_out,
        rescue_opportunities=rescue_out,
        already_dead=dead_out,
        total_deals_analysed=len(deals),
        simulated=simulated,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )