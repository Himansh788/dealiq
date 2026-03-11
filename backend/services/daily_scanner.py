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
    deal: dict[str, Any], db: AsyncSession | None
) -> dict[str, Any] | None:
    """Check if rep promised something in email but hasn't followed up."""
    if db is None:
        return None
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


ZOHO_STAGES = [
    "Qualification", "Needs Analysis", "Value Proposition", "Id. Decision Makers",
    "Perception Analysis", "Proposal/Price Quote", "Negotiation/Review",
    "Contract Sent", "Closed Won", "Closed Lost",
]

_STAGE_KEYWORDS: dict[str, list[str]] = {
    "Proposal/Price Quote": ["proposal", "quote", "pricing", "cost breakdown", "roi", "business case", "investment"],
    "Negotiation/Review":   ["negotiation", "negotiate", "counter", "revised pricing", "legal review", "revised proposal"],
    "Contract Sent":        ["contract", "agreement", "msa", "nda", "docusign", "signed", "order form", "sow", "statement of work"],
    "Closed Won":           ["purchase order", "po sent", "kicked off", "onboarding", "invoice", "approved", "go ahead"],
    "Needs Analysis":       ["requirements", "use case", "pain points", "scoping", "current process", "discovery"],
    "Value Proposition":    ["demo", "product demo", "walkthrough", "demo done", "showed the product"],
}


async def _fetch_email_context_for_scan(deal_id: str, session: dict, limit: int = 8) -> str:
    """Fetch email context for a deal — Outlook primary, Zoho fallback."""
    try:
        from services.outlook_enrichment import get_enriched_emails, fmt_emails_for_ai
        user_key = session.get("email") or session.get("user_id") or "default"
        emails = await get_enriched_emails(
            deal_id=deal_id,
            zoho_token=session.get("access_token", ""),
            user_key=user_key,
            limit=limit,
        )
        if emails:
            return fmt_emails_for_ai(emails, limit=limit)
    except Exception:
        pass
    try:
        from services.zoho_client import fetch_deal_emails
        emails = await fetch_deal_emails(session.get("access_token", ""), deal_id)
        if emails:
            parts = []
            for e in emails[:limit]:
                subj = e.get("Subject") or e.get("subject") or "(no subject)"
                frm = e.get("From") or e.get("from") or ""
                body = (e.get("Description") or e.get("body") or "")[:300]
                parts.append(f"From: {frm}\nSubject: {subj}\n{body}")
            return "\n---\n".join(parts)
    except Exception:
        pass
    return ""


async def _check_stage_drift_batch(
    deals: list[dict[str, Any]],
    session: dict,
    max_deals: int = 6,
) -> list[dict[str, Any]]:
    """
    Detect CRM stage staleness by comparing email context against the current stage.
    Fetches emails for the most recently-active deals, then does ONE batched AI call
    to identify mismatches. Returns up to 3 stage_drift action items.
    """
    if not deals or not GROQ_API_KEY:
        return []

    closed = {"Closed Won", "Closed Lost"}
    candidates = sorted(
        [d for d in deals if d.get("stage") not in closed and d.get("last_activity_time")],
        key=lambda d: d.get("last_activity_time", ""),
        reverse=True,
    )[:max_deals]

    if not candidates:
        return []

    # Fetch email context for each candidate concurrently
    import asyncio
    contexts = await asyncio.gather(
        *[_fetch_email_context_for_scan(d["id"], session, limit=8) for d in candidates],
        return_exceptions=True,
    )

    # Build the batch prompt
    deal_blocks = []
    valid_candidates = []
    for deal, ctx in zip(candidates, contexts):
        if isinstance(ctx, Exception) or not ctx or len(ctx) < 50:
            continue
        block = (
            f"DEAL #{len(valid_candidates)+1}: {deal.get('name', deal.get('deal_name', 'Unknown'))} "
            f"(id={deal['id']}, stage={deal.get('stage','?')})\n{ctx[:600]}"
        )
        deal_blocks.append(block)
        valid_candidates.append(deal)

    if not deal_blocks:
        return []

    # Use the actual stages present in the pipeline — handles custom stage names
    all_stages = list(dict.fromkeys(
        d.get("stage", "") for d in deals if d.get("stage")
    ))
    stages_list = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(all_stages))
    batch_text = "\n\n".join(deal_blocks)

    prompt = f"""You are a CRM data quality checker for a B2B sales team.
For each deal below, read the email thread and decide if the CRM stage is stale — i.e. the deal has actually progressed further than what CRM shows.

STAGES USED IN THIS PIPELINE (in rough progression order):
{stages_list}

DEALS TO ANALYZE:
{batch_text}

RULES:
- Only flag drift when emails contain CLEAR, SPECIFIC evidence (contract language, signed docs, proposal sent, demo completed, pricing discussed, etc.)
- Return the suggested_stage using EXACTLY the stage name as shown in the list above
- The suggested stage must be MORE ADVANCED than the current stage
- Never suggest the final Closed stages unless there is explicit confirmation (signed contract, PO received)
- If evidence is weak or absent → no_drift: true for that deal

Respond with a JSON array — one object per deal, in the same order as the deals above:
[
  {{"deal_id": "...", "no_drift": true/false, "suggested_stage": "exact stage name from list or null", "confidence": "high|medium|low", "reasoning": "one sentence citing specific email evidence"}},
  ...
]
Return ONLY the JSON array, no markdown fences."""

    try:
        client = AsyncGroq(api_key=GROQ_API_KEY)
        resp = await client.chat.completions.create(
            model=_FAST_MODEL,
            max_tokens=600,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        results = json.loads(raw)
    except Exception:
        return []

    actions = []
    for deal, result in zip(valid_candidates, results):
        if result.get("no_drift"):
            continue
        suggested = result.get("suggested_stage")
        confidence = result.get("confidence", "low")
        if not suggested or confidence == "low":
            continue
        # Ensure suggested stage is different from current
        current = deal.get("stage", "")
        if suggested == current:
            continue
        # Soft-validate: suggested stage must appear in the pipeline's known stages
        if suggested not in all_stages:
            continue

        actions.append({
            "type": "stage_drift",
            "deal_id": deal["id"],
            "deal_name": deal.get("name", deal.get("deal_name", "Unknown")),
            "company": deal.get("account_name", deal.get("company", "")),
            "amount": deal.get("amount", 0),
            "stage": current,
            "urgency_score": 78 if confidence == "high" else 65,
            "context": result.get("reasoning", f"Emails suggest this deal has advanced beyond '{current}'."),
            "suggested_action": f"Update CRM stage from '{current}' → '{suggested}' to reflect actual deal progress.",
            "suggested_stage": suggested,
        })

    return actions[:3]  # surface at most 3 to avoid noise


async def run_morning_scan(
    deals: list[dict[str, Any]],
    db: AsyncSession,
    generate_drafts: bool = False,
    session: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Run the morning scan across all active deals.
    Returns actions sorted by urgency_score DESC, capped at 12.
    Pass session to enable email-based stage drift detection.
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

    # Sort + cap the CRM-rule actions first
    actions.sort(key=lambda a: a["urgency_score"], reverse=True)
    actions = actions[:12]

    # Email-based stage drift detection — runs across ALL active deals and is
    # appended AFTER the cap so it is never crowded out by overdue/silent signals.
    # A deal can be both overdue AND need a stage update, so we scan all, not just unflagged.
    if session:
        drift_actions = await _check_stage_drift_batch(
            [d for d in deals if d.get("stage") not in active_stages],
            session,
        )
        # Deduplicate: if a deal already has an action, skip drift for it to avoid two cards
        existing_ids = {a["deal_id"] for a in actions}
        drift_actions = [a for a in drift_actions if a["deal_id"] not in existing_ids]
        actions.extend(drift_actions)

    # Optionally generate AI email drafts
    if generate_drafts:
        deal_map = {d["id"]: d for d in deals}
        for action in actions:
            deal = deal_map.get(action["deal_id"], {})
            action["draft"] = await _generate_draft(action, deal)

    return actions
