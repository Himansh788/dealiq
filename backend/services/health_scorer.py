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
            detail=f"Next step found: '{next_step[:80].rsplit(' ', 1)[0]}'"
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


def score_response_recency(
    days_since_response: Optional[int],
    stage: str = "",
    has_outbound: bool = False,
) -> HealthSignal:
    """Signal 2: How recently did the buyer respond?
    Later-stage deals (negotiation, evaluation) tolerate longer response gaps.

    has_outbound=True means we've sent at least one email — so None means "never responded"
    rather than "no email data at all", which is a harder critical signal.
    """
    if days_since_response is None:
        if has_outbound:
            return HealthSignal(
                name="Buyer Response Recency",
                score=0,
                max_score=20,
                label="critical",
                detail="Buyer has never responded to any outreach. This is not yet a two-way conversation.",
            )
        return HealthSignal(
            name="Buyer Response Recency",
            score=8,
            max_score=20,
            label="insufficient_data",
            detail="No email data available. Connect Outlook or ensure emails are BCC'd to Zoho for accurate scoring.",
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


def score_stage_age(stage: str, days_in_stage: Optional[int], stage_history: Optional[list] = None) -> HealthSignal:
    """Signal 5: How long has deal been at current stage vs. benchmark?"""
    if stage_history is not None and len(stage_history) == 0:
        return HealthSignal(name="Stage Velocity", score=0, max_score=15, label="insufficient_data",
                            detail="No stage history available. Stage movement cannot be assessed.")
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


def apply_signal_override(label: str, signals: List[HealthSignal]) -> str:
    """
    Override the score-derived label when signals are disproportionately bad.
    Rule: 2+ critical signals → label can be no better than 'critical'.
    """
    critical_count = sum(1 for s in signals if s.label == "critical")
    if critical_count >= 2 and label in ("healthy", "at_risk"):
        return "critical"
    return label


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
    # Zero inbound = buyer has NEVER responded — always critical regardless of outbound count
    if emails_in == 0:
        if emails_out == 0:
            return HealthSignal(name="Communication Balance", score=0, max_score=10, label="insufficient_data",
                                detail="No emails exchanged yet.")
        return HealthSignal(name="Communication Balance", score=0, max_score=10, label="critical",
                            detail=f"{emails_out} sent / 0 received — buyer has never responded. No two-way dialogue exists.")

    # Zero outbound = buyer is reaching out but rep hasn't responded
    if emails_out == 0:
        return HealthSignal(name="Communication Balance", score=2, max_score=10, label="warn",
                            detail=f"0 sent / {emails_in} received — buyer is reaching out but rep hasn't responded.")

    ratio = emails_out / emails_in
    total = emails_out + emails_in

    # Too few emails to judge pattern
    if total < 4:
        return HealthSignal(name="Communication Balance", score=3, max_score=10, label="warn",
                            detail=f"{emails_out} sent / {emails_in} received — too few emails to assess pattern reliably.")

    if 0.5 <= ratio <= 2.5:
        return HealthSignal(name="Communication Balance", score=10, max_score=10, label="good",
                            detail=f"Ratio {ratio:.1f}:1 — healthy two-way dialogue.")
    elif ratio <= 4.0:
        return HealthSignal(name="Communication Balance", score=4, max_score=10, label="warn",
                            detail=f"Ratio {ratio:.1f}:1 — communication is imbalanced. Buyer may be disengaging.")
    else:
        return HealthSignal(name="Communication Balance", score=1, max_score=10, label="critical",
                            detail=f"Ratio {ratio:.1f}:1 — heavily one-sided. Buyer is not responding.")


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


def _score_activity_momentum(days_since_any: Optional[int]) -> HealthSignal:
    if days_since_any is None:
        return HealthSignal(name="Activity Momentum", score=0, max_score=5, label="insufficient_data",
                            detail="No activity data available.")
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
    label = apply_signal_override(determine_health_label(total), signals)
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


def score_deal_from_zoho(
    raw_deal: Dict[str, Any],
    outlook_emails: Optional[List[Dict[str, Any]]] = None,
) -> DealHealthResult:
    """Score a deal using Zoho CRM fields, enriched with Outlook emails when available."""
    deal_id = raw_deal.get("id", "unknown")
    deal_name = raw_deal.get("name", "Unknown Deal")
    stage = raw_deal.get("stage", "Unknown")

    # When Outlook emails are available, delegate to score_deal_with_activities
    # so communication signals are computed from real email data.
    if outlook_emails:
        activity_data = {"summary": {}}
        return score_deal_with_activities(raw_deal, activity_data, outlook_emails=outlook_emails)

    # Pure Zoho fallback — be honest about what we don't know
    days_in_stage = (
        raw_deal.get("days_in_stage") or
        _days_since(raw_deal.get("modified_time")) or
        _days_since(raw_deal.get("created_time"))
    )

    # last_activity_time is updated by rep-side CRM events — use as momentum proxy only,
    # NOT as buyer response time. Pass None for buyer response when no email data.
    last_activity_days = _days_since(raw_deal.get("last_activity_time"))
    next_step = raw_deal.get("next_step") or raw_deal.get("description")

    return score_deal(
        deal_id=deal_id,
        deal_name=deal_name,
        stage=stage,
        next_step=next_step,
        days_since_buyer_response=None,  # unknown without email data
        contact_count=raw_deal.get("contact_count", 1),
        economic_buyer_engaged=raw_deal.get("economic_buyer_engaged", False),
        discount_mention_count=raw_deal.get("discount_mention_count", 0),
        days_in_stage=days_in_stage,
        last_activity_days=last_activity_days,
        activity_count_30d=raw_deal.get("activity_count_30d", 0),
    )


def score_from_timeline(timeline_analysis: dict) -> Dict[str, Any]:
    """
    Derive three bonus signals from Zoho v9 Timeline analysis.
    Returns a dict of { signal_name: HealthSignal } to be merged into score_deal().

    Signals added:
      Stage Momentum  : +15 forward, -0 (but 0/15) backward, neutral if no stage data
      Email Recency   : replaces activity-based recency with real email send date
      Deal Engagement : human vs automation ratio signal
    """
    signals = timeline_analysis.get("deal_health_signals", {})

    # Stage Momentum (max 15 pts)
    stage_progression = timeline_analysis.get("stage_progression", [])
    n_transitions = len(stage_progression)
    if n_transitions == 0:
        stage_momentum = HealthSignal(
            name="Stage Momentum",
            score=0, max_score=15, label="insufficient_data",
            detail="No stage transitions found. Cannot assess deal movement."
        )
    elif signals.get("stage_moving_forward"):
        latest = stage_progression[-1]
        days_ago = latest.get("days_ago") or 0
        # Recency decay: older transitions score less even if still moving forward
        if days_ago > 60:
            recency_score = 2
            recency_note = f"last move {days_ago}d ago — momentum stale"
        elif days_ago > 30:
            recency_score = 4
            recency_note = f"last move {days_ago}d ago — slowing"
        else:
            recency_score = 8
            recency_note = f"last move {days_ago}d ago — recent"
        # Forward transition count bonus (2 pts each, max 7)
        forward_count = sum(1 for s in stage_progression if s.get("direction") == "forward")
        count_score = min(7, forward_count * 2)
        momentum_score = min(15, recency_score + count_score)
        momentum_label = "good" if momentum_score >= 8 else "warn"
        stage_momentum = HealthSignal(
            name="Stage Momentum",
            score=momentum_score, max_score=15, label=momentum_label,
            detail=f"Moving forward: {latest['old_stage']} → {latest['new_stage']} ({recency_note}, {forward_count} forward move{'s' if forward_count != 1 else ''})."
        )
    else:
        latest = stage_progression[-1]
        count_str = f"Only {n_transitions} stage transition{'s' if n_transitions != 1 else ''} found"
        stage_momentum = HealthSignal(
            name="Stage Momentum",
            score=0, max_score=15, label="critical",
            detail=f"Stage regressed: {latest['old_stage']} → {latest['new_stage']}. {count_str}. Investigate immediately."
        )

    # Email Recency (max 10 pts — bonus; used to override activity-based recency if better)
    days = timeline_analysis.get("days_since_last_email")
    if days is None:
        email_recency = HealthSignal(
            name="Email Recency (Timeline)",
            score=0, max_score=10, label="insufficient_data",
            detail="No email send events found in the v9 timeline. Sync your mailbox or check CRM email settings."
        )
    elif days <= 7:
        email_recency = HealthSignal(
            name="Email Recency (Timeline)",
            score=10, max_score=10, label="good",
            detail=f"Email sent {days} day(s) ago — active communication."
        )
    elif days <= 14:
        email_recency = HealthSignal(
            name="Email Recency (Timeline)",
            score=7, max_score=10, label="good",
            detail=f"Email sent {days} days ago — within acceptable range."
        )
    elif days <= 30:
        email_recency = HealthSignal(
            name="Email Recency (Timeline)",
            score=3, max_score=10, label="warn",
            detail=f"No email in {days} days. Follow up now."
        )
    else:
        email_recency = HealthSignal(
            name="Email Recency (Timeline)",
            score=0, max_score=10, label="critical",
            detail=f"No email in {days} days — risk of buyer going dark."
        )

    # Deal Engagement — human vs automation ratio + recency (max 10 pts)
    # Recency is critical: a deal where the rep was active 3 months ago but not in 14 days
    # should NOT score as "strong engagement."
    ratio = signals.get("human_activity_ratio", 0.5)
    total = timeline_analysis.get("total_entries", 0)
    days_since_human = timeline_analysis.get("days_since_last_human_activity")
    human_pct = int(ratio * 100)

    if total == 0:
        engagement = HealthSignal(
            name="Deal Engagement",
            score=0, max_score=10, label="insufficient_data",
            detail="No timeline entries to assess engagement quality."
        )
    elif ratio >= 0.7:
        # High human ratio — but check if it's recent
        if days_since_human is not None and days_since_human > 14:
            engagement = HealthSignal(
                name="Deal Engagement",
                score=4, max_score=10, label="warn",
                detail=(
                    f"{human_pct}% human-driven historically, but last rep activity was "
                    f"{days_since_human} days ago. Engagement has dropped off."
                )
            )
        elif days_since_human is not None and days_since_human > 30:
            engagement = HealthSignal(
                name="Deal Engagement",
                score=2, max_score=10, label="critical",
                detail=(
                    f"{human_pct}% human-driven historically, but no rep activity in "
                    f"{days_since_human} days. Deal is effectively unattended."
                )
            )
        else:
            engagement = HealthSignal(
                name="Deal Engagement",
                score=10, max_score=10, label="good",
                detail=f"{human_pct}% human-driven activity — strong rep engagement."
            )
    elif ratio >= 0.4:
        if days_since_human is not None and days_since_human > 14:
            engagement = HealthSignal(
                name="Deal Engagement",
                score=2, max_score=10, label="critical",
                detail=(
                    f"{human_pct}% human activity, last rep action {days_since_human} days ago. "
                    f"Automations handling the rest — deal needs rep attention."
                )
            )
        else:
            engagement = HealthSignal(
                name="Deal Engagement",
                score=6, max_score=10, label="warn",
                detail=f"{human_pct}% human activity. Automations handling the rest — rep should be more active."
            )
    else:
        engagement = HealthSignal(
            name="Deal Engagement",
            score=2, max_score=10, label="critical",
            detail=f"Only {human_pct}% human activity. This deal is running on autopilot — no real rep engagement."
        )

    return {
        "stage_momentum": stage_momentum,
        "email_recency": email_recency,
        "deal_engagement": engagement,
    }


def _enrich_summary_with_outlook(
    summary: Dict[str, Any],
    outlook_emails: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Patch the activity summary dict with real signals from Outlook emails.

    Called when Zoho's activity data is absent/stale because the rep didn't BCC.
    Only upgrades (improves data quality) — never overwrites a better existing value.

    Patches:
      emails_outbound       — count of emails rep sent via Outlook
      emails_inbound        — count of buyer replies found in Outlook
      days_since_last_inbound — most recent buyer reply date
      days_since_any_activity — most recent email in either direction
    """
    if not outlook_emails:
        return summary

    summary = dict(summary)   # shallow copy — don't mutate caller's dict

    now = datetime.now(timezone.utc)
    outlook_out = 0
    outlook_in = 0
    latest_inbound_days: Optional[int] = None
    latest_any_days: Optional[int] = None

    for e in outlook_emails:
        # Skip internal-only threads — not buyer communication
        match_meta = e.get("_outlook_match") or {}
        if match_meta.get("is_internal"):
            continue
        # Skip post-close emails for live health signals
        if match_meta.get("post_close"):
            continue

        direction = e.get("direction") or e.get("status") or ""
        sent_at_str = e.get("sent_at") or e.get("date") or ""
        days: Optional[int] = _days_since(sent_at_str)

        if direction in ("sent", "outbound"):
            outlook_out += 1
        elif direction in ("delivered", "received", "inbound"):
            outlook_in += 1
            if days is not None:
                if latest_inbound_days is None or days < latest_inbound_days:
                    latest_inbound_days = days

        if days is not None:
            if latest_any_days is None or days < latest_any_days:
                latest_any_days = days

    # Only patch if Outlook gives us more/better data than what Zoho provided
    if outlook_out > 0:
        existing_out = summary.get("emails_outbound", 0) or 0
        summary["emails_outbound"] = max(existing_out, outlook_out)

    if outlook_in > 0:
        existing_in = summary.get("emails_inbound", 0) or 0
        summary["emails_inbound"] = max(existing_in, outlook_in)

    if latest_inbound_days is not None:
        existing_inbound = summary.get("days_since_last_inbound")
        # Use Outlook date if Zoho has none, or if Outlook is more recent
        if (
            existing_inbound is None
            or (isinstance(existing_inbound, int) and existing_inbound >= 999)
            or (isinstance(existing_inbound, int) and latest_inbound_days < existing_inbound)
        ):
            summary["days_since_last_inbound"] = latest_inbound_days

    if latest_any_days is not None:
        existing_any = summary.get("days_since_any_activity")
        if (
            existing_any is None
            or (isinstance(existing_any, int) and existing_any >= 999)
            or (isinstance(existing_any, int) and latest_any_days < existing_any)
        ):
            summary["days_since_any_activity"] = latest_any_days

    return summary


def score_deal_with_activities(
    deal_data: Dict[str, Any],
    activity_data: dict,
    outlook_emails: Optional[List[Dict[str, Any]]] = None,
) -> DealHealthResult:
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

    # Patch summary with Outlook signals when rep didn't BCC Zoho
    if outlook_emails:
        summary = _enrich_summary_with_outlook(summary, outlook_emails)

    days_in_stage = (
        deal_data.get("days_in_stage")
        or _days_since(deal_data.get("modified_time"))
        or _days_since(deal_data.get("created_time"))
    )
    next_step = deal_data.get("next_step") or deal_data.get("description")

    # 3 new activity-data signals (read before building signals for has_outbound check)
    emails_out = summary.get("emails_outbound", 0)
    emails_in = summary.get("emails_inbound", 0)

    # Use real inbound email date; treat sentinel 999 as "no data"
    days_since_inbound = summary.get("days_since_last_inbound")
    if isinstance(days_since_inbound, int) and days_since_inbound >= 999:
        days_since_inbound = None

    # Existing 6 signals, rescaled to new max weights
    raw_signals = [
        (_rescale_signal(score_next_step(next_step), 15)),
        # has_outbound=True lets scorer distinguish "buyer never responded" from "no email data"
        score_response_recency(days_since_inbound, stage, has_outbound=(emails_out > 0)),
        (_rescale_signal(score_stakeholder_depth(
            deal_data.get("confirmed_persona_count") or deal_data.get("contact_count", 1),
            deal_data.get("economic_buyer_engaged", False),
        ), 10)),
        score_discount_pattern(deal_data.get("discount_mention_count", 0)),  # stays 10
        (_rescale_signal(score_stage_age(stage, days_in_stage), 10)),
        (_rescale_signal(score_activity_velocity(), 10)),
    ]

    contact_count = summary.get("total_contacts", 0)
    days_since_any_raw = summary.get("days_since_any_activity")
    days_since_any = None if (days_since_any_raw is None or (isinstance(days_since_any_raw, int) and days_since_any_raw >= 999)) else days_since_any_raw

    signals = raw_signals + [
        _score_communication_balance(emails_out, emails_in),
        _score_multithreading(contact_count),
        _score_activity_momentum(days_since_any),
    ]

    total = sum(s.score for s in signals)
    label = apply_signal_override(determine_health_label(total), signals)
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


def enrich_signal_details(
    signals: List[HealthSignal],
    days_silent: Optional[int] = None,
    contact_count: int = 1,
    last_email_subject: Optional[str] = None,
    stage_name: Optional[str] = None,
) -> List[HealthSignal]:
    """
    Post-process signals to add cross-signal context to detail strings.
    Signals that are critical gain richer details when other critical signals compound them.
    Returns a new list of HealthSignal instances (immutable-safe).
    """
    critical_names = {s.name for s in signals if s.label == "critical"}
    days_str = f"{days_silent} days" if days_silent else "an extended period"
    subject_str = f" about '{last_email_subject}'" if last_email_subject and last_email_subject != "N/A" else ""

    enriched = []
    for sig in signals:
        detail = sig.detail

        if sig.label == "critical":
            if sig.name == "Buyer Response Recency" and "Multi-threading" in critical_names:
                detail = (
                    f"Buyer silent for {days_str}. With only {contact_count} contact(s) engaged, "
                    f"there's no fallback path — this is the highest-priority fix."
                )
            elif sig.name == "Multi-threading" and "Buyer Response Recency" in critical_names:
                detail = (
                    f"Only {contact_count} contact(s) engaged. Buyer has been silent for {days_str} "
                    f"— no alternative path to advance. Identify and engage the economic buyer this week."
                )
            elif sig.name == "Stage Velocity" and any(
                n in critical_names for n in ("Activity Momentum", "Activity Velocity", "Buyer Response Recency")
            ):
                detail = sig.detail + (
                    " Combined with buyer silence and low activity, this deal shows no forward momentum. "
                    "Escalate or disqualify."
                )
            elif sig.name == "Email Recency (Timeline)" and last_email_subject:
                detail = (
                    f"Last email{subject_str} was {days_silent or '?'} days ago — "
                    f"the conversation has gone cold. Reference this topic when re-engaging."
                )
            elif sig.name == "Activity Momentum":
                other_critical = [n for n in critical_names if n != sig.name]
                if len(other_critical) >= 2:
                    detail = (
                        f"{days_str} since any activity, combined with {len(other_critical)} other critical signals. "
                        f"This deal is at serious risk — escalate to manager for pipeline review."
                    )

        enriched.append(HealthSignal(
            name=sig.name, score=sig.score, max_score=sig.max_score,
            label=sig.label, detail=detail,
        ))

    return enriched


def score_deal_with_timeline(
    deal_data: Dict[str, Any],
    activity_data: dict,
    timeline_analysis: dict,
    outlook_emails: Optional[List[Dict[str, Any]]] = None,
) -> DealHealthResult:
    """
    Score a deal using Zoho CRM fields + activity bundle + v9 Timeline signals.

    Extends score_deal_with_activities (9 signals, 100 pts) by replacing the
    generic Activity Velocity signal with three timeline-derived signals:
      Stage Momentum     (15 pts) — forward/backward movement detected from stage history
      Email Recency      (10 pts) — last email sent date from timeline (more accurate)
      Deal Engagement    (10 pts) — human vs automation activity ratio

    When timeline_analysis is empty, falls back to score_deal_with_activities.
    """
    if not timeline_analysis or not timeline_analysis.get("total_entries"):
        return score_deal_with_activities(deal_data, activity_data, outlook_emails)

    deal_id = deal_data.get("id", "unknown")
    deal_name = deal_data.get("name", "Unknown Deal")
    stage = deal_data.get("stage", "Unknown")
    summary = activity_data.get("summary", {})

    # Patch summary with Outlook signals when rep didn't BCC Zoho
    if outlook_emails:
        summary = _enrich_summary_with_outlook(summary, outlook_emails)

    days_in_stage = (
        deal_data.get("days_in_stage")
        or _days_since(deal_data.get("modified_time"))
        or _days_since(deal_data.get("created_time"))
    )
    next_step = deal_data.get("next_step") or deal_data.get("description")

    emails_out = summary.get("emails_outbound", 0)
    emails_in = summary.get("emails_inbound", 0)
    contact_count = summary.get("total_contacts", 0)

    # Buyer Response Recency: use ONLY inbound email date.
    # days_since_last_email from timeline_analysis is when WE sent an email (outbound) —
    # using it as "buyer response recency" is wrong. Keep it for the Email Recency signal only.
    days_since_inbound = summary.get("days_since_last_inbound")
    if isinstance(days_since_inbound, int) and days_since_inbound >= 999:
        days_since_inbound = None

    # Activity Momentum: prefer timeline human-activity scan over Zoho summary field
    # (Last_Activity_Time is often null; timeline events are always present when synced)
    days_since_any_timeline = timeline_analysis.get("days_since_last_human_activity")
    days_since_any_raw = summary.get("days_since_any_activity")
    days_since_any_zoho = None if (days_since_any_raw is None or (isinstance(days_since_any_raw, int) and days_since_any_raw >= 999)) else days_since_any_raw
    days_since_any = days_since_any_timeline if days_since_any_timeline is not None else days_since_any_zoho

    core_signals = [
        _rescale_signal(score_next_step(next_step), 15),
        # has_outbound lets scorer distinguish "buyer never responded" from "no email data"
        score_response_recency(days_since_inbound, stage, has_outbound=(emails_out > 0)),
        _rescale_signal(score_stakeholder_depth(
            deal_data.get("confirmed_persona_count") or deal_data.get("contact_count", 1),
            deal_data.get("economic_buyer_engaged", False),
        ), 10),
        score_discount_pattern(deal_data.get("discount_mention_count", 0)),
        _rescale_signal(score_stage_age(stage, days_in_stage), 10),
        _score_communication_balance(emails_out, emails_in),
        _score_multithreading(contact_count),
        _score_activity_momentum(days_since_any),
    ]

    timeline_signals_map = score_from_timeline(timeline_analysis)
    timeline_signals = [
        timeline_signals_map["stage_momentum"],
        timeline_signals_map["email_recency"],
        timeline_signals_map["deal_engagement"],
    ]

    # Rescale core signals (max 90) to 65 pts so timeline signals (max 35) round to 100
    rescaled_core = [_rescale_signal(s, round(s.max_score * 65 / 90)) for s in core_signals]

    all_signals = rescaled_core + timeline_signals
    total = min(100, sum(s.score for s in all_signals))
    label = apply_signal_override(determine_health_label(total), all_signals)
    recommendation = build_recommendation(all_signals, total, stage)
    action_required = any(s.label == "critical" for s in all_signals)

    return DealHealthResult(
        deal_id=deal_id,
        deal_name=deal_name,
        total_score=total,
        health_label=label,
        signals=all_signals,
        recommendation=recommendation,
        action_required=action_required,
    )