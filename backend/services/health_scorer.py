from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from models.schemas import HealthSignal, DealHealthResult
from models.activity_schemas import ActivityItem


# Stage order for calculating "going backward" detection
STAGE_ORDER = [
    "Qualification",
    "Needs Analysis",
    "Value Proposition",
    "Id. Decision Makers",
    "Perception Analysis",
    "Proposal/Price Quote",
    "Negotiation/Review",
    "Closed Won",
    "Closed Lost",
]

# Average days per stage benchmark (simulated from typical SaaS data)
STAGE_BENCHMARKS: Dict[str, int] = {
    "Qualification": 7,
    "Needs Analysis": 10,
    "Value Proposition": 7,
    "Id. Decision Makers": 14,
    "Perception Analysis": 10,
    "Proposal/Price Quote": 14,
    "Negotiation/Review": 21,
    # Additional real-world stages
    "Demo Done": 14,
    "Demo Scheduled": 7,
    "Demo": 14,
    "Evaluation": 21,
    "Contract Sent": 14,
    "Sales Approved Deal": 10,
    "Closed - Won": 0,
    "Closed - Lost": 0,
}


def _days_since(dt_str: Optional[str]) -> Optional[int]:
    """Return days since a datetime string (ISO 8601)."""
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return (now - dt).days
    except Exception:
        return None


def score_next_step(next_step: Optional[str]) -> HealthSignal:
    """Signal 1: Does the most recent outbound have a defined next step?"""
    if next_step and len(next_step.strip()) > 10:
        return HealthSignal(
            name="Next Step Defined",
            score=20,
            max_score=20,
            label="good",
            detail=f"Next step found: '{next_step[:80]}'"
        )
    elif next_step:
        return HealthSignal(
            name="Next Step Defined",
            score=10,
            max_score=20,
            label="warn",
            detail="Next step exists but lacks a date or clear owner."
        )
    else:
        return HealthSignal(
            name="Next Step Defined",
            score=0,
            max_score=20,
            label="critical",
            detail="No next step defined. CRM activity is not progress."
        )


LATE_STAGE_LENIENT = {"Negotiation/Review", "Value Proposition", "Id. Decision Makers",
                      "Contract Sent", "Evaluation", "Sales Approved Deal"}


def score_response_recency(days_since_response: Optional[int], stage: str = "") -> HealthSignal:
    """Signal 2: How recently did the buyer respond?
    Later-stage deals (negotiation, evaluation) tolerate longer response gaps."""
    if days_since_response is None:
        return HealthSignal(
            name="Buyer Response Recency",
            score=5,
            max_score=20,
            label="warn",
            detail="No response date recorded. Cannot measure buyer engagement."
        )
    lenient = stage in LATE_STAGE_LENIENT
    if days_since_response <= 3:
        score, label = 20, "good"
        detail = f"Buyer responded {days_since_response} day(s) ago — actively engaged."
    elif days_since_response <= 7:
        score, label = 20 if lenient else 15, "good"
        detail = f"Buyer last responded {days_since_response} days ago — within normal range."
    elif days_since_response <= 14:
        score, label = 15 if lenient else 8, "good" if lenient else "warn"
        detail = f"No buyer response in {days_since_response} days. Follow up with a specific question."
    elif days_since_response <= 21:
        score, label = 10 if lenient else 5, "warn"
        detail = f"{days_since_response} days without buyer response. This deal may be stalling."
    elif days_since_response <= 30:
        score, label = 5 if lenient else 3, "warn" if lenient else "critical"
        detail = f"{days_since_response} days without buyer response. This deal may be stalling."
    else:
        score, label = 0, "critical"
        detail = f"Buyer has not responded in {days_since_response} days. Risk of zombie status."
    return HealthSignal(name="Buyer Response Recency", score=score, max_score=20, label=label, detail=detail)


def score_stakeholder_depth(contact_count: int, economic_buyer_engaged: bool) -> HealthSignal:
    """Signal 3: Has anyone beyond first contact engaged? Has economic buyer been reached?"""
    if economic_buyer_engaged and contact_count >= 3:
        return HealthSignal(name="Stakeholder Depth", score=20, max_score=20, label="good",
                            detail=f"{contact_count} stakeholders engaged including economic buyer.")
    elif economic_buyer_engaged:
        return HealthSignal(name="Stakeholder Depth", score=15, max_score=20, label="good",
                            detail="Economic buyer engaged. Broaden stakeholder map.")
    elif contact_count >= 2:
        return HealthSignal(name="Stakeholder Depth", score=10, max_score=20, label="warn",
                            detail=f"{contact_count} contacts involved but economic buyer not confirmed.")
    else:
        return HealthSignal(name="Stakeholder Depth", score=8, max_score=20, label="warn",
                            detail="Only one contact engaged. Economic buyer unreached — high single-thread risk.")


def score_discount_pattern(discount_mention_count: int) -> HealthSignal:
    """Signal 4: Has discount been mentioned multiple times without a close signal? (max 10 pts)"""
    if discount_mention_count == 0:
        return HealthSignal(name="Discount Pattern", score=10, max_score=10, label="good",
                            detail="No discount pressure detected in this deal.")
    elif discount_mention_count == 1:
        return HealthSignal(name="Discount Pattern", score=7, max_score=10, label="good",
                            detail="Discount mentioned once — within normal range.")
    elif discount_mention_count == 2:
        return HealthSignal(name="Discount Pattern", score=3, max_score=10, label="warn",
                            detail="Discount mentioned twice. Check if rep is discounting out of anxiety.")
    else:
        return HealthSignal(name="Discount Pattern", score=0, max_score=10, label="critical",
                            detail=f"Discount mentioned {discount_mention_count} times. Commercial pressure is elevated.")


def score_stage_age(stage: str, days_in_stage: Optional[int]) -> HealthSignal:
    """Signal 5: How long has deal been at current stage vs. benchmark?"""
    if days_in_stage is None:
        return HealthSignal(name="Stage Velocity", score=8, max_score=15, label="warn",
                            detail="Stage entry date unavailable. Cannot benchmark velocity.")
    benchmark = STAGE_BENCHMARKS.get(stage, 14)
    ratio = days_in_stage / benchmark if benchmark > 0 else 1
    if ratio <= 1.0:
        return HealthSignal(name="Stage Velocity", score=15, max_score=15, label="good",
                            detail=f"{days_in_stage} days in '{stage}' — on track (benchmark: {benchmark} days).")
    elif ratio <= 1.5:
        return HealthSignal(name="Stage Velocity", score=8, max_score=15, label="warn",
                            detail=f"{days_in_stage} days in '{stage}' — slightly over benchmark of {benchmark} days.")
    elif ratio <= 2.5:
        return HealthSignal(name="Stage Velocity", score=3, max_score=15, label="critical",
                            detail=f"{days_in_stage} days in '{stage}' — {days_in_stage - benchmark} days over benchmark.")
    else:
        return HealthSignal(name="Stage Velocity", score=0, max_score=15, label="critical",
                            detail=f"Deal stuck in '{stage}' for {days_in_stage} days. {int(ratio)}x over benchmark.")


def score_activity_velocity(activities: Optional[List[ActivityItem]] = None) -> HealthSignal:
    """Signal 6: Engagement velocity based on real activity feed (max 15 pts).
    Falls back to neutral 5/15 if no activity data is provided (e.g. list view fetch).
    """
    if not activities:
        return HealthSignal(name="Activity Velocity", score=5, max_score=15, label="warn",
                            detail="No activity data available. Open deal for full analysis.")

    from services.activity_intelligence import compute_engagement_velocity
    ev = compute_engagement_velocity(activities, stage="")
    score = ev.score

    if score >= 12:
        label, detail = "good", f"{ev.touchpoints_14d} touchpoints in 14 days. Strong engagement velocity."
    elif score >= 8:
        label, detail = "good", f"{ev.touchpoints_14d} touchpoints in 14 days. Healthy cadence."
    elif score >= 5:
        label, detail = "warn", f"Moderate activity ({ev.touchpoints_14d} touchpoints/14d). Increase cadence."
    elif score >= 2:
        label, detail = "warn", f"Low activity. Only {ev.touchpoints_14d} touchpoints in last 14 days."
    else:
        label, detail = "critical", "No activity in 14 days — send a re-engagement email and schedule a call."

    return HealthSignal(name="Activity Velocity", score=score, max_score=15, label=label, detail=detail)


def determine_health_label(score: int) -> str:
    if score >= 65:
        return "healthy"
    elif score >= 45:
        return "at_risk"
    elif score >= 20:
        return "critical"
    else:
        return "zombie"


def build_recommendation(signals: List[HealthSignal], score: int, stage: str) -> str:
    """Build a plain-language recommendation based on the worst signals."""
    critical = [s for s in signals if s.label == "critical"]
    warn = [s for s in signals if s.label == "warn"]

    if not critical and not warn:
        return "Deal looks healthy. Maintain momentum and confirm next steps after every interaction."

    worst = critical[0] if critical else warn[0]

    recommendations = {
        "Next Step Defined": "Define a specific next step with a date before your next contact.",
        "Buyer Response Recency": "Send a direct, short re-engagement email with one clear question.",
        "Stakeholder Depth": "Map the buying committee. Identify and engage the economic buyer.",
        "Discount Pattern": "Stop discounting reactively. Link any concession to a specific ask from the buyer.",
        "Stage Velocity": f"This deal has stalled in {stage}. Force a decision: advance, escalate, or kill.",
        "Activity Velocity": "No activity in 14 days — send a re-engagement email and schedule a call.",
        "Communication Balance": "Re-engage the buyer. Send a question that requires a response.",
        "Multi-threading": "Add a second contact. Ask your champion to introduce you to the decision maker.",
        "Activity Momentum": "No recent activity — schedule a touchpoint today.",
    }
    return recommendations.get(worst.name, "Review this deal with your manager.")


# ── Activity-data signal scorers (used by score_deal_with_activities) ──────────

def _score_communication_balance(emails_out: int, emails_in: int) -> HealthSignal:
    ratio = emails_out / max(emails_in, 1)
    if 0.5 <= ratio <= 2.0:
        return HealthSignal(name="Communication Balance", score=10, max_score=10, label="good",
                            detail=f"{emails_out} out / {emails_in} in — healthy two-way dialogue.")
    elif 0.3 <= ratio <= 3.0:
        return HealthSignal(name="Communication Balance", score=6, max_score=10, label="warn",
                            detail=f"Ratio {ratio:.1f}:1 — slightly imbalanced communication.")
    else:
        return HealthSignal(name="Communication Balance", score=2, max_score=10, label="critical",
                            detail=f"{emails_out} outbound, {emails_in} inbound — one-sided conversation.")


def _score_multithreading(contact_count: int) -> HealthSignal:
    if contact_count >= 3:
        return HealthSignal(name="Multi-threading", score=10, max_score=10, label="good",
                            detail=f"{contact_count} contacts engaged. Strong stakeholder coverage.")
    elif contact_count == 2:
        return HealthSignal(name="Multi-threading", score=7, max_score=10, label="warn",
                            detail="2 contacts. Add a third stakeholder to reduce single-thread risk.")
    elif contact_count == 1:
        return HealthSignal(name="Multi-threading", score=3, max_score=10, label="critical",
                            detail="Only 1 contact. If they go dark, deal is stuck.")
    else:
        return HealthSignal(name="Multi-threading", score=0, max_score=10, label="critical",
                            detail="No contacts linked. Cannot assess stakeholder coverage.")


def _score_activity_momentum(days_since_any: int) -> HealthSignal:
    if days_since_any <= 3:
        return HealthSignal(name="Activity Momentum", score=5, max_score=5, label="good",
                            detail=f"Activity {days_since_any} day(s) ago — deal is live.")
    elif days_since_any <= 7:
        return HealthSignal(name="Activity Momentum", score=4, max_score=5, label="good",
                            detail=f"Last activity {days_since_any} days ago — within normal range.")
    elif days_since_any <= 14:
        return HealthSignal(name="Activity Momentum", score=2, max_score=5, label="warn",
                            detail=f"{days_since_any} days since last touchpoint. Momentum slowing.")
    else:
        return HealthSignal(name="Activity Momentum", score=0, max_score=5, label="critical",
                            detail=f"{days_since_any} days since any activity. Deal may be stalling.")


def _rescale_signal(sig: HealthSignal, new_max: int) -> HealthSignal:
    """Proportionally rescale a signal score to a new max_score."""
    new_score = round((sig.score / sig.max_score) * new_max) if sig.max_score else 0
    return HealthSignal(name=sig.name, score=new_score, max_score=new_max,
                        label=sig.label, detail=sig.detail)


def score_deal(
    deal_id: str,
    deal_name: str,
    stage: str,
    next_step: Optional[str] = None,
    days_since_buyer_response: Optional[int] = None,
    contact_count: int = 1,
    economic_buyer_engaged: bool = False,
    discount_mention_count: int = 0,
    days_in_stage: Optional[int] = None,
    last_activity_days: Optional[int] = None,
    activity_count_30d: int = 0,
    activities: Optional[List[ActivityItem]] = None,
) -> DealHealthResult:
    """Compute the full health score for a deal."""

    signals = [
        score_next_step(next_step),
        score_response_recency(days_since_buyer_response, stage),
        score_stakeholder_depth(contact_count, economic_buyer_engaged),
        score_discount_pattern(discount_mention_count),
        score_stage_age(stage, days_in_stage),
        score_activity_velocity(activities),
    ]

    total = sum(s.score for s in signals)
    label = determine_health_label(total)
    recommendation = build_recommendation(signals, total, stage)
    action_required = any(s.label == "critical" for s in signals)

    return DealHealthResult(
        deal_id=deal_id,
        deal_name=deal_name,
        total_score=total,
        health_label=label,
        signals=signals,
        recommendation=recommendation,
        action_required=action_required,
    )


def score_deal_from_zoho(raw_deal: Dict[str, Any]) -> DealHealthResult:
    """Score a deal using data directly from Zoho CRM fields."""
    deal_id = raw_deal.get("id", "unknown")
    deal_name = raw_deal.get("name", "Unknown Deal")
    stage = raw_deal.get("stage", "Unknown")

    # Days in current stage — use modified_time (when stage last changed) or created_time
    # NOTE: last_activity_time is NOT stage entry time — it changes with every email/call
    days_in_stage = (
        raw_deal.get("days_in_stage") or          # explicitly set (e.g. from stage history)
        _days_since(raw_deal.get("modified_time")) or  # when deal record last changed
        _days_since(raw_deal.get("created_time"))  # fallback: deal age
    )

    # Days since last activity
    last_activity_days = _days_since(raw_deal.get("last_activity_time"))

    # Use description/next step field
    next_step = raw_deal.get("next_step") or raw_deal.get("description")

    return score_deal(
        deal_id=deal_id,
        deal_name=deal_name,
        stage=stage,
        next_step=next_step,
        days_since_buyer_response=last_activity_days,  # Approximate
        contact_count=raw_deal.get("contact_count", 1),
        economic_buyer_engaged=raw_deal.get("economic_buyer_engaged", False),
        discount_mention_count=raw_deal.get("discount_mention_count", 0),
        days_in_stage=days_in_stage,
        last_activity_days=last_activity_days,
        activity_count_30d=raw_deal.get("activity_count_30d", 0),
    )


def score_deal_with_activities(deal_data: Dict[str, Any], activity_data: dict) -> DealHealthResult:
    """
    Score a deal using Zoho CRM fields + real activity bundle (9 signals, total=100).

    Rebalanced max scores vs score_deal (6 signals, 100pts):
      Next Step Defined    20 → 15
      Buyer Response       20 → 20  (now uses real inbound email date)
      Stakeholder Depth    20 → 10
      Discount Pattern     10 → 10
      Stage Velocity       15 → 10
      Activity Velocity    15 → 10
      Communication Balance —  → 10  (NEW)
      Multi-threading      —  → 10  (NEW)
      Activity Momentum    —  →  5  (NEW)
    """
    deal_id = deal_data.get("id", "unknown")
    deal_name = deal_data.get("name", "Unknown Deal")
    stage = deal_data.get("stage", "Unknown")
    summary = activity_data.get("summary", {})

    days_in_stage = (
        deal_data.get("days_in_stage")
        or _days_since(deal_data.get("modified_time"))
        or _days_since(deal_data.get("created_time"))
    )
    next_step = deal_data.get("next_step") or deal_data.get("description")

    # Use real inbound email date; treat sentinel 999 as "no data"
    days_since_inbound = summary.get("days_since_last_inbound")
    if isinstance(days_since_inbound, int) and days_since_inbound >= 999:
        days_since_inbound = None

    # Existing 6 signals, rescaled to new max weights
    raw_signals = [
        (_rescale_signal(score_next_step(next_step), 15)),
        score_response_recency(days_since_inbound, stage),      # stays 20
        (_rescale_signal(score_stakeholder_depth(
            deal_data.get("contact_count", 1),
            deal_data.get("economic_buyer_engaged", False),
        ), 10)),
        score_discount_pattern(deal_data.get("discount_mention_count", 0)),  # stays 10
        (_rescale_signal(score_stage_age(stage, days_in_stage), 10)),
        (_rescale_signal(score_activity_velocity(), 10)),
    ]

    # 3 new activity-data signals
    emails_out = summary.get("emails_outbound", 0)
    emails_in = summary.get("emails_inbound", 0)
    contact_count = summary.get("total_contacts", 0)
    days_since_any = summary.get("days_since_any_activity", 999)

    signals = raw_signals + [
        _score_communication_balance(emails_out, emails_in),
        _score_multithreading(contact_count),
        _score_activity_momentum(days_since_any),
    ]

    total = sum(s.score for s in signals)
    label = determine_health_label(total)
    recommendation = build_recommendation(signals, total, stage)
    action_required = any(s.label == "critical" for s in signals)

    return DealHealthResult(
        deal_id=deal_id,
        deal_name=deal_name,
        total_score=total,
        health_label=label,
        signals=signals,
        recommendation=recommendation,
        action_required=action_required,
    )