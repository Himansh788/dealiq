import json
import base64
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel
from services.cache import cache_get, cache_set, cache_delete, cache_key as _bck

from services.health_scorer import score_deal_from_zoho
from routers.warnings import _compute_warnings

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Auth helpers (same pattern as warnings.py) ─────────────────────────────────

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


# TTL in seconds — battle cards cached for 1 hour with email context, 10 min without
CACHE_TTL_SECONDS = 3600
CACHE_TTL_NO_EMAIL = 600


# ── Request / helpers ─────────────────────────────────────────────────────────

class BattleCardRequest(BaseModel):
    deal_id: str
    meeting_context: str = ""


def _get_demo_deal(deal_id: str) -> Optional[dict]:
    from services.demo_data import SIMULATED_DEALS
    for d in SIMULATED_DEALS:
        if d.get("id") == deal_id:
            return d
    # Fallback: return first demo deal so the feature is always demo-able
    return SIMULATED_DEALS[0] if SIMULATED_DEALS else None


def _enrich_deal_for_scoring(deal: dict) -> dict:
    """Add computed fields required by score_deal_from_zoho."""
    from datetime import datetime, timezone

    def _days(dt_str) -> Optional[int]:
        if not dt_str:
            return None
        try:
            dt = datetime.fromisoformat(str(dt_str)[:19].replace("Z", ""))
            return (datetime.utcnow() - dt).days
        except Exception:
            return None

    enriched = dict(deal)
    enriched.setdefault("days_in_stage",            _days(deal.get("Created_Time") or deal.get("created_time")))
    enriched.setdefault("last_activity_days",       _days(deal.get("Last_Activity_Time") or deal.get("last_activity_time")))
    enriched.setdefault("days_since_buyer_response", enriched.get("last_activity_days"))
    prob = float(deal.get("Probability") or deal.get("probability") or 0)
    enriched.setdefault("activity_count_30d",  5 if prob >= 90 else 3 if prob >= 50 else 2 if prob >= 20 else 1)
    enriched.setdefault("economic_buyer_engaged", prob >= 70)
    enriched.setdefault("contact_count",       2 if prob >= 30 else 1)
    enriched.setdefault("discount_mention_count", 0)
    return enriched


def _normalise_deal(raw: dict) -> dict:
    """Return a lowercase-key dict regardless of whether raw came from Zoho or demo."""
    def _name(field: str) -> Optional[str]:
        v = raw.get(field)
        return v.get("name") if isinstance(v, dict) else v

    return {
        "id":                raw.get("id", ""),
        "name":              raw.get("Deal_Name") or raw.get("name") or "Unnamed Deal",
        "stage":             raw.get("Stage") or raw.get("stage") or "Unknown",
        "amount":            raw.get("Amount") or raw.get("amount") or 0,
        "closing_date":      raw.get("Closing_Date") or raw.get("closing_date"),
        "account_name":      _name("Account_Name") or raw.get("account_name") or "—",
        "owner":             _name("Owner") or raw.get("owner") or "",
        "last_activity_time": raw.get("Last_Activity_Time") or raw.get("last_activity_time"),
        "created_time":      raw.get("Created_Time") or raw.get("created_time"),
        "probability":       raw.get("Probability") or raw.get("probability") or 0,
        "next_step":         raw.get("Next_Step") or raw.get("next_step") or "",
        "contact_name":      _name("Contact_Name") or raw.get("contact_name"),
        "description":       raw.get("Description") or raw.get("description") or "",
    }


def _build_deal_context(deal: dict, warnings: list, health_result, meeting_context: str, email_context: str = "", contacts_block: str = "") -> str:
    def _days_since_str(dt_str) -> str:
        if not dt_str:
            return "unknown"
        try:
            dt = datetime.fromisoformat(str(dt_str)[:19].replace("Z", ""))
            return str((datetime.utcnow() - dt).days)
        except Exception:
            return "unknown"

    signals_text = ""
    for sig in (health_result.signals if health_result else []):
        signals_text += f"  - {sig.name}: {sig.score}/{sig.max_score} — {sig.detail}\n"

    warnings_text = ""
    for w in warnings:
        sev = w.get("severity", "").upper()
        title = w.get("title", "")
        msg = w.get("message", "")
        warnings_text += f"  - [{sev}] {title}: {msg}\n"

    days_inactive = _days_since_str(deal.get("last_activity_time"))

    email_section = f"""
EMAIL THREAD (most recent first — use this to understand the actual conversation, buyer tone, and open commitments):
{email_context if email_context.strip() else "  No email history available — rep may not have BCC'd Zoho. Check Outlook."}
""" if email_context else "\nEMAIL THREAD: Not available — Outlook not connected or no emails found.\n"

    return f"""Deal Intelligence Report for Pre-Meeting Battle Card

DEAL OVERVIEW:
- Deal Name: {deal.get('name', 'Unknown')}
- Company: {deal.get('account_name', '—')}
- Deal Amount: ${float(deal.get('amount') or 0):,.0f}
- Current Stage: {deal.get('stage', 'Unknown')}
- Close Date: {deal.get('closing_date') or 'Not set'}
- Probability: {deal.get('probability', 0)}%
- Owner: {deal.get('owner') or 'Unknown'}
- Primary Contact: {deal.get('contact_name') or 'Not specified'}
- Days in Current Stage: {deal.get('days_in_stage') or 'unknown'}

HEALTH SCORE: {health_result.total_score if health_result else 50}/100 ({health_result.health_label if health_result else 'unknown'})
HEALTH SIGNALS:
{signals_text if signals_text else "  No signal data available"}

LAST CRM ACTIVITY: {days_inactive} days ago (NOTE: rep may have emailed via Outlook without updating CRM — see email thread below)
NEXT STEP DEFINED: {deal.get('next_step') or 'None — no next step set in CRM'}
DESCRIPTION / NOTES: {deal.get('description') or 'None'}

ACTIVE WARNINGS:
{warnings_text if warnings_text else "  No active warnings"}

MEETING CONTEXT: {meeting_context if meeting_context.strip() else "General check-in / follow-up call"}

RECOMMENDATION FROM HEALTH SCORER: {health_result.recommendation if health_result else 'Review deal status'}

CONTACTS & STAKEHOLDERS:
{contacts_block if contacts_block else "  No contact data available — connect Outlook to discover personas."}

{email_section}"""


async def _call_groq(deal_context: str) -> dict:
    client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system_prompt = """You are a brutally honest sales coach preparing a rep for a live call. You have 90 seconds to brief them.

You have real deal data INCLUDING the actual email thread. This is the ground truth — it overrides CRM fields when they conflict.

CRITICAL RULES:
- Read the EMAIL THREAD carefully. If it shows recent buyer engagement that the CRM doesn't reflect, lead with that.
- If emails marked "[Outlook — not in CRM]" exist, the rep is communicating but not logging — flag this.
- Every sentence must reference something specific: company name, contact name, email subject, stage, amount, or a specific date.
- If the deal has CRM silence but recent Outlook emails, say: "CRM shows X days inactive but email thread shows [actual last contact]"
- If there's no next step in CRM AND no commitment in the email thread, your talk track must start with getting one.
- open_loops must come from the actual email thread — unresolved questions, unkept commitments, unanswered asks.
- watch_out must name specific risk signals visible in the email tone or CRM data — not generic patterns.
- Never write "Ask about current project status" — instead: "Ask [contact] to confirm the [specific thing from email thread]"
- If health score is below 50 AND email thread shows buyer disengagement, one_liner must be about saving or qualifying out.

Respond ONLY with valid JSON. No markdown, no explanation:

{
  "situation": "3 sentences. Name company, exact stage, days in stage, health score, and — critically — what the EMAIL THREAD reveals about where this deal actually stands vs what CRM shows.",
  "last_interaction": "Reference the actual last email: who sent it, when, what they said. If no email data: state what the CRM silence pattern implies.",
  "open_loops": [
    "Specific unresolved commitment or question from the email thread — quote or paraphrase actual language",
    "item 2 — from email or CRM data"
  ],
  "key_contacts": [{"name": "Contact Name", "role": "their role in this deal", "last_contact_days": 0, "engagement": "hot|warm|cold|silent"}],
  "talk_track": [
    "Opening: reference something specific from the last email or last known touchpoint",
    "Middle: address the biggest open loop or risk from the email thread",
    "Specific ask: what commitment to extract on this call — name it exactly",
    "Close: what happens if they don't commit — escalate or disqualify?"
  ],
  "watch_out": [
    "Specific risk 1 — reference the actual email pattern or CRM signal that indicates this",
    "risk 2"
  ],
  "one_liner": "One sentence. Name the company or contact. Reference the email thread state. Tell the rep what this call must achieve.",
  "email_intelligence": {
    "last_buyer_reply": "Date and summary of last buyer email, or 'none found'",
    "buyer_tone": "positive|neutral|cool|disengaged|urgent",
    "crm_gap": "Yes — X emails found in Outlook not in CRM | No gap detected",
    "key_commitment": "Most important open commitment from the email thread, or 'none'"
  }
}

Rules:
- open_loops: 1-4 items. Must come from actual email thread data or CRM gaps. If none, return [].
- talk_track: exactly 4 items. Each must be specific to THIS deal.
- watch_out: 2-3 items. Each must name the actual pattern, not a generic risk category.
- email_intelligence: always populate — even if email_context says "no emails", state that explicitly."""

    try:
        response = await client.chat.completions.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": deal_context},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning("Battle card: Claude call failed: %s", e)
        return {
            "situation": "Unable to generate summary. Review deal manually in Zoho.",
            "last_interaction": "No recent activity data available.",
            "open_loops": [],
            "key_contacts": [{"name": "Unknown", "role": "Primary contact", "last_contact_days": -1}],
            "talk_track": [
                "Ask about current status and any blockers",
                "Confirm next steps and timeline",
                "Address any outstanding questions",
                "Get commitment on a decision date",
            ],
            "watch_out": ["Review deal warnings before call"],
            "one_liner": "Establish clear next steps with a specific date.",
            "email_intelligence": {"last_buyer_reply": "unavailable", "buyer_tone": "neutral", "crm_gap": "unknown", "key_commitment": "none"},
        }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/battlecard/generate")
async def generate_battlecard(
    body: BattleCardRequest,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)
    deal_id = body.deal_id
    is_demo = _is_demo(session)

    # Redis cache — user-scoped to prevent cross-tenant leakage
    _user = (session.get("email") or session.get("user_id") or "anon").replace(":", "_")
    _redis_key = _bck("battlecard", _user, deal_id)
    if not is_demo:
        _cached = await cache_get(_redis_key)
        if _cached:
            logger.debug("battlecard cache hit user=%s deal=%s", _user, deal_id)
            return {**_cached, "cached": True}

    if is_demo:
        raw_deal = _get_demo_deal(deal_id)
    else:
        from services.zoho_client import fetch_single_deal, map_zoho_deal
        raw_deal = await fetch_single_deal(session.get("access_token", ""), deal_id)

    if not raw_deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Normalise to lowercase keys
    deal = _normalise_deal(raw_deal)

    # Score
    enriched = _enrich_deal_for_scoring(raw_deal)
    health_result = score_deal_from_zoho(enriched)

    # Warnings — _compute_warnings expects lowercase keys (already normalised above)
    warnings_result = _compute_warnings(deal)
    warnings = warnings_result.get("warnings", [])

    # Fetch enriched emails (Outlook primary + Zoho supplementary)
    email_context = ""
    if not is_demo:
        try:
            from services.outlook_enrichment import get_enriched_emails, fmt_emails_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            emails = await get_enriched_emails(
                deal_id=deal_id,
                zoho_token=session.get("access_token", ""),
                user_key=user_key,
                limit=10,
            )
            email_context = fmt_emails_for_ai(emails, limit=10)
        except Exception as e:
            logger.warning("battlecard: email enrichment failed deal=%s: %s", deal_id, e)

    # Fetch contacts + personas
    contacts_block = ""
    if not is_demo:
        try:
            from services.contact_intelligence import get_deal_contacts, format_contacts_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            contacts_data = await get_deal_contacts(
                deal_id=deal_id,
                zoho_token=session.get("access_token", ""),
                user_key=user_key,
                db=None,
            )
            contacts_block = format_contacts_for_ai(
                contacts_data.get("zoho_contacts", []),
                contacts_data.get("confirmed_personas", []),
                contacts_data.get("potential_personas", []),
            )
        except Exception as e:
            logger.warning("battlecard: contacts fetch failed deal=%s: %s", deal_id, e)
    else:
        # Demo contacts block
        contacts_block = (
            "CONFIRMED CONTACTS:\n"
            "  • Sarah Chen <sarah.chen@techcorp.com> | Role: Economic Buyer | Source: CRM (Zoho)\n"
            "  • James Liu <james.liu@techcorp.com> | Role: Champion | Source: CRM (Zoho)\n"
            "POTENTIAL PERSONAS (seen in Outlook emails, not yet confirmed by rep):\n"
            "  • Mike Torres <mike.torres@techcorp.com> | 3 email(s) | Last seen: 2026-03-08"
        )

    # Build context and call Claude
    import asyncio
    context_str = _build_deal_context(deal, warnings, health_result, body.meeting_context, email_context, contacts_block)
    try:
        sections = await asyncio.wait_for(_call_groq(context_str), timeout=55)
    except asyncio.TimeoutError:
        logger.warning("battlecard: Claude timed out for deal=%s", deal_id)
        sections = {
            "situation": "AI analysis timed out — deal data loaded successfully, retry to generate full battle card.",
            "last_interaction": "Check CRM for latest activity.",
            "open_loops": [],
            "key_contacts": [],
            "talk_track": ["Review deal status", "Confirm next steps", "Address blockers", "Get commitment on timeline"],
            "watch_out": ["AI analysis unavailable — review warnings manually"],
            "one_liner": "AI timed out — retry to generate full battle card.",
            "email_intelligence": {"last_buyer_reply": "unavailable", "buyer_tone": "neutral", "crm_gap": "unknown", "key_commitment": "none"},
        }

    response_data = {
        "deal_id": deal_id,
        "deal_name": deal["name"],
        "company": deal["account_name"],
        "amount": float(deal["amount"] or 0),
        "stage": deal["stage"],
        "health_score": health_result.total_score,
        "generated_at": datetime.utcnow().isoformat(),
        "sections": sections,
        "warnings": warnings,
        "cached": False,
    }

    # Cache in Redis — shorter TTL when no email context (lower quality card)
    if not is_demo:
        ttl = CACHE_TTL_SECONDS if email_context else CACHE_TTL_NO_EMAIL
        await cache_set(_redis_key, response_data, ttl=ttl)

    return response_data


@router.delete("/battlecard/cache/{deal_id}")
async def clear_battlecard_cache(deal_id: str, authorization: str = Header(default="")):
    """Invalidate battle card cache for a deal. Clears all users' cached cards for this deal."""
    from services.cache import cache_delete_pattern
    await cache_delete_pattern(f"dealiq:battlecard:*:{deal_id}")
    return {"cleared": True, "deal_id": deal_id}
