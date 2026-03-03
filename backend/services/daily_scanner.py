"""
Morning scan engine — runs via APScheduler at 7 AM.
Scans active deals and surfaces prioritized actions for the rep's day.
"""

import os
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from groq import AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import EmailExtraction

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_FAST_MODEL = "llama-3.1-8b-instant"

# Days-since-last-activity thresholds
SILENT_DEAL_DAYS = 14
MISSED_FOLLOWUP_DAYS = 5
PREP_WINDOW_HOURS = 3

_DRAFT_SYSTEM = """You are a sales AI assistant. Write a short, specific, personalized email draft (3-5 sentences).
Be direct, reference the deal context. Return ONLY the email body — no subject, no preamble."""


async def _generate_draft(action: dict[str, Any], deal: dict[str, Any]) -> str:
    """Generate a short email draft for an action item."""
    try:
        client = AsyncGroq(api_key=GROQ_API_KEY)
        prompt = f"""Deal: {deal.get('name', 'Unknown')} | Stage: {deal.get('stage', '?')} | Amount: ${deal.get('amount', 0):,}
Action type: {action.get('type', 'follow-up')}
Context: {action.get('context', '')}
Write a short email draft for this action."""
        resp = await client.chat.completions.create(
            model=_FAST_MODEL,
            messages=[
                {"role": "system", "content": _DRAFT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=200,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return ""


def _days_since(date_str: str | None) -> int | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _check_silent_deal(deal: dict[str, Any]) -> dict[str, Any] | None:
    days = _days_since(deal.get("last_activity_time"))
    if days is not None and days >= SILENT_DEAL_DAYS:
        urgency = 90 if days >= 30 else 75 if days >= 21 else 60
        stage = deal.get("stage", "")
        company = deal.get("account_name", deal.get("company", "the prospect"))
        suggested = _STAGE_NEXT_STEP.get(stage, "Send a re-engagement email to restart the conversation.")
        return {
            "type": "silent_deal",
            "deal_id": deal["id"],
            "deal_name": deal.get("name", deal.get("deal_name", "Unknown")),
            "company": company,
            "amount": deal.get("amount", 0),
            "stage": stage,
            "urgency_score": urgency,
            "context": f"No activity for {days} days. {company} is at risk of going cold — still in {stage}.",
            "suggested_action": suggested,
        }
    return None


def _check_overdue_close(deal: dict[str, Any]) -> dict[str, Any] | None:
    close_date_str = deal.get("closing_date") or deal.get("close_date")
    if not close_date_str:
        return None
    try:
        close_date = datetime.strptime(close_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if close_date < datetime.now(timezone.utc):
            overdue_days = (datetime.now(timezone.utc) - close_date).days
            return {
                "type": "overdue_close",
                "deal_id": deal["id"],
                "deal_name": deal.get("name", deal.get("deal_name", "Unknown")),
                "company": deal.get("account_name", deal.get("company", "")),
                "amount": deal.get("amount", 0),
                "stage": deal.get("stage", ""),
                "urgency_score": 85,
                "context": f"Close date passed {overdue_days} day{'s' if overdue_days != 1 else ''} ago. {deal.get('account_name', deal.get('company', 'Prospect'))} is still in {deal.get('stage', '?')} with no updated timeline.",
                "suggested_action": f"Contact {deal.get('account_name', deal.get('company', 'the buyer'))} to get a revised commitment date or reassess deal viability.",
            }
    except Exception:
        pass
    return None


_STAGE_NEXT_STEP: dict[str, str] = {
    "Qualification":        "Schedule a discovery call to qualify budget, authority, and timeline.",
    "Needs Analysis":       "Send a follow-up with a summary of pain points and proposed solution.",
    "Value Proposition":    "Book a tailored demo and share a relevant case study.",
    "Proposal/Price Quote": "Follow up on the proposal — ask if they have questions on pricing or scope.",
    "Negotiation/Review":   "Set a decision deadline and offer a call with legal or finance to unblock.",
    "Id. Decision Makers":  "Map remaining stakeholders and schedule calls with each decision maker.",
}


def _check_no_next_step(deal: dict[str, Any]) -> dict[str, Any] | None:
    stage = deal.get("stage", "")
    if not deal.get("next_step") and stage not in ("Closed Won", "Closed Lost"):
        days_silent = _days_since(deal.get("last_activity_time"))
        silence_note = f" No activity for {days_silent} days." if days_silent and days_silent > 3 else ""
        suggested = _STAGE_NEXT_STEP.get(stage, "Define a clear next step with a specific date to maintain momentum.")
        return {
            "type": "no_next_step",
            "deal_id": deal["id"],
            "deal_name": deal.get("name", deal.get("deal_name", "Unknown")),
            "company": deal.get("account_name", deal.get("company", "")),
            "amount": deal.get("amount", 0),
            "stage": stage,
            "urgency_score": 55,
            "context": f"No next step recorded in CRM.{silence_note} Stage: {stage}.",
            "suggested_action": suggested,
        }
    return None


async def _check_missed_followup(
    deal: dict[str, Any], db: AsyncSession
) -> dict[str, Any] | None:
    """Check if rep promised something in email but hasn't followed up."""
    result = await db.execute(
        select(EmailExtraction)
        .where(EmailExtraction.deal_zoho_id == deal["id"])
        .order_by(EmailExtraction.created_at.desc())
        .limit(1)
    )
    latest = result.scalars().first()
    if not latest or not latest.commitments:
        return None
    days = (datetime.now(timezone.utc) - latest.created_at.replace(tzinfo=timezone.utc)).days
    if days >= MISSED_FOLLOWUP_DAYS:
        return {
            "type": "missed_followup",
            "deal_id": deal["id"],
            "deal_name": deal.get("name", deal.get("deal_name", "Unknown")),
            "company": deal.get("account_name", deal.get("company", "")),
            "amount": deal.get("amount", 0),
            "stage": deal.get("stage", ""),
            "urgency_score": 80,
            "context": f"You committed: '{latest.commitments[0]}' — {days} days ago with no follow-up.",
            "suggested_action": "Follow up on your commitment to maintain trust.",
        }
    return None


async def run_morning_scan(
    deals: list[dict[str, Any]],
    db: AsyncSession,
    generate_drafts: bool = False,
) -> list[dict[str, Any]]:
    """
    Run the morning scan across all active deals.
    Returns actions sorted by urgency_score DESC, capped at 12.
    """
    actions: list[dict[str, Any]] = []
    active_stages = {"Closed Won", "Closed Lost"}

    for deal in deals:
        if deal.get("stage") in active_stages:
            continue

        # Run synchronous checks
        for check_fn in (_check_silent_deal, _check_overdue_close, _check_no_next_step):
            result = check_fn(deal)
            if result:
                actions.append(result)
                break  # one action per deal to avoid noise

    # Run async checks (DB lookups) — only if no action already found for this deal
    deal_ids_with_action = {a["deal_id"] for a in actions}
    for deal in deals:
        if deal.get("stage") in active_stages:
            continue
        if deal["id"] in deal_ids_with_action:
            continue
        result = await _check_missed_followup(deal, db)
        if result:
            actions.append(result)

    # Sort by urgency descending, cap at 12
    actions.sort(key=lambda a: a["urgency_score"], reverse=True)
    actions = actions[:12]

    # Optionally generate AI email drafts
    if generate_drafts:
        deal_map = {d["id"]: d for d in deals}
        for action in actions:
            deal = deal_map.get(action["deal_id"], {})
            action["draft"] = await _generate_draft(action, deal)

    return actions
