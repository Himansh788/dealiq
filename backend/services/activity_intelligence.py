"""
Activity Intelligence service — engagement velocity scoring, ghost stakeholder detection,
and team activity summaries. Stateless: all analysis is based on current data only.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from models.activity_schemas import (
    ActivityItem,
    EngagementVelocityScore,
    GhostStakeholder,
    ActivityFeedResponse,
    RepActivity,
    TeamActivitySummary,
)

logger = logging.getLogger(__name__)

# Stages where ghost detection is meaningful (late-stage deals only)
GHOST_DETECTION_STAGES = {
    "Proposal/Price Quote",
    "Negotiation/Review",
    "Contract Sent",
    "Value Proposition",
}

# Industry benchmarks per stage (meetings/week, touchpoints in 14d)
STAGE_BENCHMARKS = {
    "Negotiation/Review":    {"meetings_pw": 3.2, "touchpoints_14d": 8},
    "Proposal/Price Quote":  {"meetings_pw": 2.0, "touchpoints_14d": 5},
    "Value Proposition":     {"meetings_pw": 1.5, "touchpoints_14d": 4},
    "Qualification":         {"meetings_pw": 1.0, "touchpoints_14d": 3},
    "Needs Analysis":        {"meetings_pw": 1.5, "touchpoints_14d": 4},
    "Id. Decision Makers":   {"meetings_pw": 1.0, "touchpoints_14d": 3},
    "Contract Sent":         {"meetings_pw": 2.5, "touchpoints_14d": 6},
}


def _parse_date(date_str: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _days_since(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    dt = _parse_date(date_str)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def compute_engagement_velocity(
    activities: list[ActivityItem],
    stage: str,
) -> EngagementVelocityScore:
    """Score engagement velocity 0-15 pts based on activity patterns."""
    now = datetime.now(timezone.utc)

    # Activities in last 14 days
    recent = []
    for a in activities:
        dt = _parse_date(a.date)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).days <= 14:
                recent.append(a)

    touchpoints_14d = len(recent)

    # Unique contacts in last 14 days
    contacts_seen: set[str] = set()
    for a in recent:
        for p in a.participants:
            if p:
                contacts_seen.add(p.lower())
    unique_contacts_14d = len(contacts_seen)

    # Days since last two-way exchange (inbound + outbound both present within same week)
    days_since_two_way = 999
    sorted_acts = sorted(activities, key=lambda a: a.date, reverse=True)
    has_inbound = False
    has_outbound = False
    for a in sorted_acts:
        if a.direction == "inbound":
            has_inbound = True
        elif a.direction == "outbound":
            has_outbound = True
        if has_inbound and has_outbound:
            days = _days_since(a.date)
            days_since_two_way = days if days is not None else 999
            break

    # Meeting trend (compare last 7d meetings vs prior 7d meetings)
    meetings_last_7d = sum(
        1 for a in activities
        if a.type == "meeting" and _days_since(a.date) is not None and _days_since(a.date) <= 7
    )
    meetings_prior_7d = sum(
        1 for a in activities
        if a.type == "meeting"
        and _days_since(a.date) is not None
        and 7 < _days_since(a.date) <= 14
    )

    if meetings_last_7d == 0 and meetings_prior_7d == 0:
        meeting_trend = "none"
    elif meetings_last_7d > meetings_prior_7d:
        meeting_trend = "increasing"
    elif meetings_last_7d == meetings_prior_7d:
        meeting_trend = "stable"
    else:
        meeting_trend = "declining"

    # Scoring
    # Touchpoints in 14d: ≥5=5pts | ≥3=3pts | ≥1=1pt | 0=0
    if touchpoints_14d >= 5:
        t_score = 5
    elif touchpoints_14d >= 3:
        t_score = 3
    elif touchpoints_14d >= 1:
        t_score = 1
    else:
        t_score = 0

    # Unique contacts: ≥3=4pts | ≥2=2pts | ≥1=1pt
    if unique_contacts_14d >= 3:
        c_score = 4
    elif unique_contacts_14d >= 2:
        c_score = 2
    elif unique_contacts_14d >= 1:
        c_score = 1
    else:
        c_score = 0

    # Two-way recency: ≤7d=4pts | ≤14d=2pts | ≤30d=1pt | >30d=0
    if days_since_two_way <= 7:
        tw_score = 4
    elif days_since_two_way <= 14:
        tw_score = 2
    elif days_since_two_way <= 30:
        tw_score = 1
    else:
        tw_score = 0

    # Meeting trend: increasing=2pts | stable=1pt | declining/none=0
    if meeting_trend == "increasing":
        mt_score = 2
    elif meeting_trend == "stable":
        mt_score = 1
    else:
        mt_score = 0

    total = t_score + c_score + tw_score + mt_score

    # Stage benchmark comparison
    stage_benchmark: Optional[str] = None
    bench = STAGE_BENCHMARKS.get(stage)
    if bench:
        expected = bench["touchpoints_14d"]
        if touchpoints_14d < expected:
            stage_benchmark = (
                f"Deals at '{stage}' average {expected} touchpoints/14 days. "
                f"This deal: {touchpoints_14d}. Below benchmark."
            )
        else:
            stage_benchmark = (
                f"Deals at '{stage}' average {expected} touchpoints/14 days. "
                f"This deal: {touchpoints_14d}. On track."
            )

    return EngagementVelocityScore(
        score=total,
        touchpoints_14d=touchpoints_14d,
        unique_contacts_14d=unique_contacts_14d,
        days_since_two_way=days_since_two_way if days_since_two_way < 999 else 0,
        meeting_trend=meeting_trend,
        stage_benchmark=stage_benchmark,
    )


def detect_ghost_stakeholders(
    contacts: list[dict],
    activities: list[ActivityItem],
    stage: str,
    deal_age_days: int,
) -> list[GhostStakeholder]:
    """Flag contacts who haven't appeared in any activity for >14 days."""
    if stage not in GHOST_DETECTION_STAGES:
        return []
    if deal_age_days < 14:
        return []

    # Build lookup: contact email/name → most recent activity date
    participant_last_seen: dict[str, str] = {}
    for a in activities:
        for p in a.participants:
            key = p.lower()
            if key not in participant_last_seen or a.date > participant_last_seen[key]:
                participant_last_seen[key] = a.date

    ghosts: list[GhostStakeholder] = []
    for contact in contacts:
        name = contact.get("name", "Unknown")
        email = contact.get("email", "")
        role = contact.get("role")

        # Try to find this contact in participant history
        last_seen_date: Optional[str] = None
        for key, date in participant_last_seen.items():
            if (email and email.lower() in key) or name.lower() in key:
                last_seen_date = date
                break

        if last_seen_date is None:
            # Never seen in activities
            days_silent = deal_age_days
        else:
            days_silent = _days_since(last_seen_date) or 0

        if days_silent > 14:
            role_str = f" ({role})" if role else ""
            alert = (
                f"{name}{role_str} hasn't appeared in any emails or calls "
                f"for {days_silent} days."
            )
            ghosts.append(GhostStakeholder(
                name=name,
                role=role,
                email=email or None,
                days_silent=days_silent,
                last_seen_date=last_seen_date,
                alert=alert,
            ))

    return ghosts


def _map_zoho_activity_to_item(raw: dict, act_type: str) -> ActivityItem:
    """Map a raw Zoho activity/email/note dict to ActivityItem."""
    # Determine direction — handle Zoho email 'sent' bool + string direction values
    direction_val = (raw.get("direction") or raw.get("type") or "").lower()
    if direction_val in ("incoming", "received", "inbound"):
        direction = "inbound"
    elif direction_val in ("outgoing", "sent", "outbound"):
        direction = "outbound"
    elif act_type == "email":
        # Zoho email_related_list: sent=True → we sent it (outbound), sent=False → inbound
        direction = "outbound" if raw.get("sent", True) else "inbound"
    else:
        direction = "internal"

    # Date field varies by Zoho endpoint (priority order — broader list catches edge cases)
    date = (
        raw.get("sent_time")          # emails (email_related_list)
        or raw.get("Sent_Time")       # emails capitalised variant
        or raw.get("Date")            # some Zoho email records
        or raw.get("date")
        or raw.get("Call_Start_Time") # calls
        or raw.get("Start_DateTime")  # meetings/events
        or raw.get("activity_time")
        or raw.get("Activity_Date")
        or raw.get("Due_Date")        # tasks
        or raw.get("Created_Time")    # tasks, notes (Zoho capitalised)
        or raw.get("created_time")    # normalised variant
        or raw.get("Modified_Time")   # last resort
        or ""
    )
    if not date:
        logger.warning(
            "activity_intelligence: missing date — type=%s subject=%r keys=%s",
            act_type,
            str(raw.get("subject") or raw.get("Subject") or "")[:60],
            list(raw.keys()),
        )

    # Participants — handle both plain strings and Zoho nested dicts
    participants: list[str] = []

    # Email: extract from 'from' dict or plain string
    from_field = raw.get("from")
    if isinstance(from_field, dict):
        from_email = from_field.get("email") or from_field.get("name") or ""
        if from_email:
            participants.append(from_email)
    elif isinstance(from_field, str) and from_field:
        participants.append(from_field)

    # Email 'to' list
    for recipient in raw.get("to", []):
        if isinstance(recipient, dict):
            addr = recipient.get("email") or recipient.get("name") or ""
        else:
            addr = str(recipient)
        if addr and addr not in participants:
            participants.append(addr)

    # Fallback: owner field, then pre-built participants list
    if not participants:
        owner = raw.get("owner") or ""
        if isinstance(owner, dict):
            owner = owner.get("name") or owner.get("email") or ""
        if owner:
            participants.append(str(owner))

    for extra in raw.get("participants", []):
        if isinstance(extra, str) and extra not in participants:
            participants.append(extra)

    # Subject — handle both cases (Zoho uses both capitalised and lowercase)
    subject = (
        raw.get("subject")       # emails (lowercase)
        or raw.get("Subject")    # tasks / calls (capitalised)
        or raw.get("Event_Title")  # meetings
        or raw.get("Note_Title")
        or raw.get("description")
        or raw.get("note_title")
    )

    # Summary / body
    summary = (
        raw.get("content")
        or raw.get("note_content")
        or raw.get("Note_Content")
        or raw.get("body")
        or raw.get("Description")
        or raw.get("description")
    )
    if summary and len(summary) > 200:
        summary = summary[:200] + "…"

    return ActivityItem(
        id=str(raw.get("id", "")),
        type=act_type,
        direction=direction,
        date=date,
        subject=subject,
        participants=participants,
        summary=summary,
        duration_minutes=raw.get("duration_minutes") or raw.get("duration"),
    )


async def get_deal_activity_feed(
    deal_id: str,
    access_token: str,    # FIXED: was zoho_headers: dict — wrong type and wrong arg order
    stage: str,
    deal_age_days: int,
    is_demo: bool = False,
    demo_activities: Optional[dict] = None,
) -> ActivityFeedResponse:
    """
    Fetch and score activity data for a single deal.
    In demo mode uses SIMULATED_ACTIVITIES. In real mode fetches from Zoho.
    """
    if is_demo:
        entry = (demo_activities or {}).get(deal_id, {"activities": [], "contacts": []})
        raw_activities = entry.get("activities", [])
        contacts = entry.get("contacts", [])

        items: list[ActivityItem] = []
        for act in raw_activities:
            act_type = act.get("type", "email")
            items.append(_map_zoho_activity_to_item(act, act_type))

    else:
        from services.zoho_client import get_all_activity_for_deal

        bundle = await get_all_activity_for_deal(access_token, deal_id)

        items = []
        seen_ids: set[str] = set()

        for email in bundle.get("emails", []):
            item = _map_zoho_activity_to_item(email, "email")
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)

        for act in bundle.get("activities", []):
            act_type = act.get("type") or (
                "meeting" if act.get("Event_Title") or act.get("Start_DateTime") else "task"
            )
            item = _map_zoho_activity_to_item(act, act_type)
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)

        for note in bundle.get("notes", []):
            item = _map_zoho_activity_to_item(note, "note")
            if item.id not in seen_ids:
                seen_ids.add(item.id)
                items.append(item)

        # contacts already normalised by get_contacts_for_deal: {id, email, name, role, title}
        contacts = bundle.get("contacts", [])

    # Sort descending by date
    items.sort(key=lambda a: a.date or "", reverse=True)

    engagement_score = compute_engagement_velocity(items, stage)
    ghost_stakeholders = detect_ghost_stakeholders(contacts, items, stage, deal_age_days)

    return ActivityFeedResponse(
        deal_id=deal_id,
        activities=items,
        total_count=len(items),
        engagement_score=engagement_score,
        ghost_stakeholders=ghost_stakeholders,
        simulated=is_demo,
    )


def build_team_summary(deals: list[dict], is_demo: bool = False) -> TeamActivitySummary:
    """
    Compute rep-level activity summary from deal objects.
    Uses last_activity_time already present — no extra Zoho calls.
    Health scores are computed via score_deal_from_zoho when not pre-cached on the deal.
    """
    from datetime import timedelta
    from services.health_scorer import score_deal_from_zoho

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    rep_map: dict[str, dict] = {}

    for deal in deals:
        owner = deal.get("owner") or "Unknown"
        if isinstance(owner, dict):
            owner = owner.get("name", "Unknown")

        if owner not in rep_map:
            rep_map[owner] = {
                "deals_active": 0,
                "deals_touched_7d": 0,
                "health_scores": [],
                "pipeline_value": 0.0,
                "last_activities": [],
            }

        rep_map[owner]["deals_active"] += 1
        rep_map[owner]["pipeline_value"] += float(deal.get("amount", 0) or 0)

        # Prefer a pre-computed score; fall back to scoring the deal on the fly.
        health = deal.get("health_score") or deal.get("total_score") or 0
        if not health:
            try:
                result = score_deal_from_zoho(deal)
                health = result.total_score
            except Exception:
                health = 0
        if health:
            rep_map[owner]["health_scores"].append(int(health))

        last_act_str = deal.get("last_activity_time")
        if last_act_str:
            rep_map[owner]["last_activities"].append(last_act_str)
            dt = _parse_date(last_act_str)
            if dt:
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= seven_days_ago:
                    rep_map[owner]["deals_touched_7d"] += 1

    reps: list[RepActivity] = []
    for rep_name, data in rep_map.items():
        avg_health = (
            sum(data["health_scores"]) / len(data["health_scores"])
            if data["health_scores"] else 0.0
        )

        # Trend: compare deals_touched_7d vs deals_active
        touch_ratio = data["deals_touched_7d"] / max(data["deals_active"], 1)
        if touch_ratio >= 0.6:
            trend = "active"
        elif touch_ratio >= 0.3:
            trend = "slowing"
        else:
            trend = "inactive"

        reps.append(RepActivity(
            rep_name=rep_name,
            deals_active=data["deals_active"],
            deals_touched_7d=data["deals_touched_7d"],
            avg_health_score=round(avg_health, 1),
            total_pipeline_value=data["pipeline_value"],
            activity_trend=trend,
        ))

    # Sort by deals_touched_7d descending
    reps.sort(key=lambda r: r.deals_touched_7d, reverse=True)

    team_avg_touched = (
        sum(r.deals_touched_7d for r in reps) / len(reps) if reps else 0.0
    )
    team_avg_health = (
        sum(r.avg_health_score for r in reps) / len(reps) if reps else 0.0
    )

    return TeamActivitySummary(
        reps=reps,
        team_avg_deals_touched_7d=round(team_avg_touched, 1),
        team_avg_health_score=round(team_avg_health, 1),
        generated_at=now.isoformat(),
        simulated=is_demo,
    )
