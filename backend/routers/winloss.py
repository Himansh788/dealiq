from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from services.ai_client import AsyncAnthropicCompat as AsyncGroq

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store — persists across requests, resets on server restart
_winloss_store: list[dict] = []

DEAL_PATTERNS = [
    "pricing_issue", "champion_lost", "no_urgency", "competitor_win",
    "single_threaded", "budget_cut", "good_execution", "multi_threaded",
    "strong_champion", "urgency_created",
]

# Cap on auto-analyzed Zoho deals per board request to avoid rate limits
AUTO_ANALYZE_CAP = 10


def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "display_name": "Zoho User", "email": "", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _get_groq_client() -> AsyncGroq:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return AsyncGroq(api_key=api_key)


def _classify_outcome(stage: str) -> Optional[str]:
    """Return 'won', 'lost', or None based on Zoho stage name."""
    s = stage.lower().strip()
    won_keywords = ["closed won", "won", "closed-won", "deal won", "closed/won"]
    lost_keywords = ["closed lost", "lost", "closed-lost", "deal lost", "closed/lost"]
    for kw in won_keywords:
        if kw in s:
            return "won"
    for kw in lost_keywords:
        if kw in s:
            return "lost"
    return None


class AnalyzeRequest(BaseModel):
    deal_id: str
    outcome: Literal["won", "lost"]
    notes: Optional[str] = None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _build_deal_summary(deal: dict, email_context: str = "") -> str:
    """Build a rich text summary of the deal for the AI prompt, including email thread."""
    name = deal.get("name") or deal.get("Deal_Name") or "Unknown"
    amount = deal.get("amount") or deal.get("Amount") or 0
    stage = deal.get("stage") or deal.get("Stage") or "Unknown"
    description = deal.get("description") or deal.get("Description") or ""
    next_step = deal.get("next_step") or deal.get("Next_Step") or ""
    probability = deal.get("probability") or deal.get("Probability") or 0
    contact = deal.get("contact_name") or deal.get("contact") or "unknown"
    account = deal.get("account_name") or deal.get("Account_Name") or name
    closing_date = deal.get("closing_date") or deal.get("Closing_Date") or "not set"
    days_in_stage = deal.get("days_in_stage") or "unknown"
    last_activity = deal.get("last_activity_days") or "unknown"

    notes = []
    if description:
        notes.append(f"Description: {description}")
    if next_step:
        notes.append(f"Next step: {next_step}")
    notes_str = " | ".join(notes) if notes else "No notes recorded"

    email_section = ""
    if email_context and email_context.strip() and "No email" not in email_context:
        email_section = f"""
EMAIL THREAD (actual buyer communication — use this to identify what really happened):
{email_context}"""
    else:
        email_section = "\nEMAIL THREAD: Not available — rep did not BCC Zoho and Outlook is not connected."

    return f"""Company: {account}
Deal name: {name}
Amount: ${amount}
Stage when closed: {stage}
Days in stage: {days_in_stage}
Last CRM activity: {last_activity} days ago
Close probability: {probability}%
Closing date: {closing_date}
Primary contact: {contact}
Notes: {notes_str}
{email_section}"""


async def _call_groq_full(deal_json: dict, outcome: str, deal_name: str, email_context: str = "") -> dict:
    """Full analysis for manually submitted deals."""
    client = _get_groq_client()
    signals_key = "success_signals" if outcome == "won" else "warning_signs_missed"
    outcome_label = "WON" if outcome == "won" else "LOST"
    deal_summary = _build_deal_summary(deal_json, email_context)

    won_instructions = """This deal WAS WON. Your job:
- If an EMAIL THREAD is provided, find the specific email or buyer signal that indicated this would close — quote it
- Identify the specific behavior or event that caused the close
- Name the earliest signal that indicated this would close — from the email thread if available
- Identify what the rep did right that should be repeated on every similar deal
- Be specific — reference the stage, contact name, email subject, timeline, or notes"""

    lost_instructions = """This deal WAS LOST. Your job:
- If an EMAIL THREAD is provided, find the specific moment the buyer's tone changed — quote it
- Identify the specific moment or behavior that caused the loss
- Name the earliest warning sign that was visible but missed — check the email thread for early signals
- Identify one concrete action at a specific point in the deal that would have changed the outcome
- Be specific — reference the stage, days inactive, contact name, email content, or notes"""

    prompt = f"""You are a senior sales coach analyzing a real B2B deal outcome.

IMPORTANT: If an EMAIL THREAD is included below, it is the ground truth of what actually happened in this deal.
Use it to identify real buyer signals, tone shifts, and the exact moment the deal was won or lost.
Email marked "[Outlook — not in CRM]" means the rep communicated but didn't log it — this is important context.

DEAL DATA:
{deal_summary}

{won_instructions if outcome == "won" else lost_instructions}

RULES:
- Every field must reference specific data from above — company name, contact, amount, days, email content, or notes
- If the email thread shows a specific buyer objection or signal, name it explicitly
- Never write generic sales advice like "follow up more" or "build relationships"
- contributing_factors must name what actually happened in this deal, not general patterns
- {signals_key} must describe observable signals specific to this deal — prefer email evidence over CRM fields

Return ONLY valid JSON — no markdown, no explanation:
{{
  "primary_reason": "One sentence naming what decided the {outcome_label} outcome for {deal_name} — must reference specific deal data or email evidence",
  "contributing_factors": [
    "Factor 1 — specific to this deal (reference email content, stage, days, or contact if available)",
    "Factor 2 — specific event or behavior observed in this deal",
    "Factor 3"
  ],
  "{signals_key}": [
    "Signal 1 — specific observable event in this deal that {'indicated success' if outcome == 'won' else 'should have triggered action'} — cite email date/subject if available",
    "Signal 2",
    "Signal 3"
  ],
  "deal_pattern": "exactly one of: pricing_issue, champion_lost, no_urgency, competitor_win, single_threaded, budget_cut, good_execution, multi_threaded, strong_champion, urgency_created",
  "what_to_replicate_or_avoid": "{'Specific action that won this deal — what was done, when, and with whom' if outcome == 'won' else 'Specific action that should have been taken — name the moment and the exact better move based on the email evidence'}",
  "lesson": "One sentence a rep can act on — name the trigger (e.g. when buyer tone shifts to X in email, when deal hits Y days silent, when Z signal appears)",
  "email_evidence": "Key email finding that best explains this outcome, or 'No email data available'"
}}"""

    response = await client.chat.completions.create(
        model="claude-sonnet-4-5-20250929",
        messages=[
            {"role": "system", "content": "You are a B2B sales win/loss analyst. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=800,
    )
    return json.loads(_strip_json_fences(response.choices[0].message.content))


async def _call_groq_lightweight(deal: dict, outcome: str, email_context: str = "") -> dict:
    """Analysis for auto-detected Zoho closed deals — same quality, slightly shorter output."""
    client = _get_groq_client()
    outcome_label = "WON" if outcome == "won" else "LOST"
    deal_summary = _build_deal_summary(deal, email_context)
    deal_name = deal.get("name") or deal.get("Deal_Name") or "this deal"

    won_instructions = "This deal WAS WON. What specific behavior or event caused the close? Reference email evidence if available. What should the rep repeat next time?"
    lost_instructions = "This deal WAS LOST. What specifically went wrong? Find the earliest warning sign in the email thread. What one action at what specific point would have changed the outcome?"

    prompt = f"""You are a sales coach analyzing a real B2B deal outcome. Use the EMAIL THREAD as primary evidence — it shows what actually happened, not just what was logged in CRM.

DEAL DATA:
{deal_summary}

{won_instructions if outcome == "won" else lost_instructions}

RULES:
- Reference the actual company name, contact, email content, stage, days, or notes in every field
- If the email thread shows buyer disengagement, a tone shift, or a specific objection — name it
- Email marked "[Outlook — not in CRM]" means the rep communicated outside CRM — factor this into your analysis
- Never write generic advice — name the specific moment, email exchange, or action
- contributing_factors must describe what actually happened, not abstract patterns

Return ONLY valid JSON — no markdown:
{{
  "primary_reason": "One sentence specific to {deal_name} — reference actual email evidence, stage, contact, or timeline",
  "contributing_factors": [
    "Specific factor from this deal's data or email thread — not a generic label",
    "Specific factor 2"
  ],
  "deal_pattern": "exactly one of: pricing_issue, champion_lost, no_urgency, competitor_win, single_threaded, budget_cut, good_execution, multi_threaded, strong_champion, urgency_created",
  "what_to_replicate_or_avoid": "{'What specific action drove the win — name it and cite email evidence if available' if outcome == 'won' else 'What should have been done differently — name the specific moment in the email timeline and the better action'}",
  "lesson": "One actionable sentence — name the trigger (e.g. when buyer tone shifts to X in email, when deal hits Y days silent, when Z appears in thread)",
  "email_evidence": "Key email finding that best explains this outcome, or 'No email data available'"
}}"""

    response = await client.chat.completions.create(
        model="claude-sonnet-4-5-20250929",  # same model for quality
        messages=[
            {"role": "system", "content": "You are a B2B sales win/loss analyst. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=500,
    )
    return json.loads(_strip_json_fences(response.choices[0].message.content))


def _normalize_pattern(analysis: dict, outcome: str) -> dict:
    pattern = analysis.get("deal_pattern", "")
    if pattern not in DEAL_PATTERNS:
        analysis["deal_pattern"] = "good_execution" if outcome == "won" else "no_urgency"
    return analysis


@router.get("/debug-stages")
async def debug_stages(authorization: str = Header(default="")):
    """Shows all deal stages from Zoho to help configure win/loss detection."""
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"mode": "demo", "message": "Not available in demo mode"}
    from services.zoho_client import fetch_deals, map_zoho_deal
    access_token = session.get("access_token", "")
    raw = await fetch_deals(access_token, page=1, per_page=200)
    deals = [map_zoho_deal(r) for r in raw] if raw else []

    stages: dict[str, int] = {}
    for d in deals:
        stage = d.get("stage", "Unknown")
        stages[stage] = stages.get(stage, 0) + 1

    return {
        "total_deals": len(deals),
        "stages": stages,
        "classified": {
            stage: _classify_outcome(stage)
            for stage in stages
        },
        "sample_deals": [
            {"name": d.get("name"), "stage": d.get("stage"), "amount": d.get("amount")}
            for d in deals[:10]
        ]
    }


@router.post("/analyze")
async def analyze_outcome(
    body: AnalyzeRequest,
    authorization: str = Header(default=""),
):
    """Analyze a deal outcome with Groq and store the result."""
    session = _decode_session(authorization)
    is_demo = _is_demo(session) or body.deal_id.startswith("sim_")

    if is_demo:
        from services.demo_data import SIMULATED_DEALS
        deal = next((d for d in SIMULATED_DEALS if d["id"] == body.deal_id), None)
        if not deal:
            deal = {
                "id": body.deal_id,
                "name": "Demo Deal",
                "stage": "Closed",
                "amount": 50000,
                "probability": 0 if body.outcome == "lost" else 100,
                "description": "Demo deal",
            }
    else:
        from services.zoho_client import fetch_single_deal
        access_token = session.get("access_token", "")
        try:
            deal = await fetch_single_deal(access_token, body.deal_id) or {}
        except Exception:
            deal = {"id": body.deal_id, "name": body.deal_id}

    if body.notes:
        deal = {**deal, "additional_context": body.notes}

    deal_name = deal.get("name", body.deal_id)

    # Fetch enriched emails for richer analysis
    email_context = ""
    if not is_demo:
        try:
            from services.outlook_enrichment import get_enriched_emails, fmt_emails_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            emails = await get_enriched_emails(
                deal_id=body.deal_id,
                zoho_token=session.get("access_token", ""),
                user_key=user_key,
                limit=10,
            )
            email_context = fmt_emails_for_ai(emails, limit=10)
        except Exception as e:
            logger.warning("winloss: email enrichment failed deal=%s: %s", body.deal_id, e)

    try:
        analysis = await _call_groq_full(deal, body.outcome, deal_name, email_context)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    analysis = _normalize_pattern(analysis, body.outcome)

    entry = {
        "deal_id": body.deal_id,
        "deal_name": deal_name,
        "amount": deal.get("amount", 0),
        "outcome": body.outcome,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "auto_detected": False,
        **analysis,
    }

    global _winloss_store
    _winloss_store = [e for e in _winloss_store if e["deal_id"] != body.deal_id]
    _winloss_store.append(entry)

    return entry


@router.get("/board")
async def get_board(
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)
    is_demo = _is_demo(session)

    already_analyzed_ids = {e["deal_id"] for e in _winloss_store}

    auto_entries: list[dict] = []
    auto_analyzed_count = 0

    try:
        if is_demo:
            from services.demo_data import SIMULATED_DEALS
            all_deals = SIMULATED_DEALS
        else:
            from services.zoho_client import fetch_deals, map_zoho_deal
            access_token = session.get("access_token", "")
            raw = await fetch_deals(access_token, page=1, per_page=200)
            all_deals = [map_zoho_deal(r) for r in raw] if raw else []

        closed_deals: list[tuple[dict, str]] = []
        for deal in all_deals:
            deal_id = deal.get("id", "")
            if deal_id in already_analyzed_ids:
                continue

            if is_demo:
                score = deal.get("health_score") or deal.get("probability", 50)
                if score >= 75:
                    closed_deals.append((deal, "won"))
                elif score < 25:
                    closed_deals.append((deal, "lost"))
            else:
                outcome = _classify_outcome(deal.get("stage", ""))
                if outcome:
                    closed_deals.append((deal, outcome))

        to_analyze = closed_deals[:AUTO_ANALYZE_CAP]

        async def _analyze_one(deal: dict, outcome: str) -> Optional[dict]:
            try:
                analysis = await _call_groq_lightweight(deal, outcome)
                analysis = _normalize_pattern(analysis, outcome)
                return {
                    "deal_id": deal.get("id", f"auto_{deal.get('name', 'unknown')}"),
                    "deal_name": deal.get("name", "Unknown Deal"),
                    "amount": deal.get("amount", 0),
                    "outcome": outcome,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "auto_detected": True,
                    **analysis,
                }
            except Exception as e:
                logger.warning(f"Auto-analysis failed for {deal.get('name')}: {e}")
                return None

        results = await asyncio.gather(
            *[_analyze_one(d, o) for d, o in to_analyze],
            return_exceptions=False,
        )
        auto_entries = [r for r in results if r is not None]
        auto_analyzed_count = len(auto_entries)

        # Persist auto-analyzed entries so counts are stable across page refreshes
        for entry in auto_entries:
            if entry["deal_id"] not in already_analyzed_ids:
                _winloss_store.append(entry)

    except Exception as e:
        logger.warning(f"Win/loss board auto-detection failed: {e}")

    merged = list(_winloss_store)

    won = [e for e in merged if e["outcome"] == "won"]
    lost = [e for e in merged if e["outcome"] == "lost"]

    def _pattern_counts(entries: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for e in entries:
            p = e.get("deal_pattern", "unknown")
            counts[p] = counts.get(p, 0) + 1
        return counts

    def _amounts(entries: list[dict]) -> tuple[int, int]:
        amounts = [e.get("amount", 0) for e in entries if e.get("amount")]
        total = sum(amounts)
        avg = round(total / len(amounts)) if amounts else 0
        return total, avg

    def _top_pattern(counts: dict) -> str:
        return max(counts, key=lambda k: counts[k]) if counts else ""

    won_patterns = _pattern_counts(won)
    lost_patterns = _pattern_counts(lost)
    won_total, won_avg = _amounts(won)
    lost_total, lost_avg = _amounts(lost)

    return {
        "summary": {
            "won": {
                "count": len(won),
                "total_amount": won_total,
                "avg_amount": won_avg,
                "top_pattern": _top_pattern(won_patterns),
                "pattern_counts": won_patterns,
            },
            "lost": {
                "count": len(lost),
                "total_amount": lost_total,
                "avg_amount": lost_avg,
                "top_pattern": _top_pattern(lost_patterns),
                "pattern_counts": lost_patterns,
            },
        },
        "deals": merged,
        "auto_analyzed_count": auto_analyzed_count,
    }