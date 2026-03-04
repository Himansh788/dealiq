import json
import base64
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from groq import AsyncGroq
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

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


# ── In-memory cache: { deal_id: { data: dict, generated_at: datetime } } ────────

_battlecard_cache: dict = {}
CACHE_TTL_MINUTES = 60


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


def _build_deal_context(deal: dict, warnings: list, health_result, meeting_context: str) -> str:
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

    contact = deal.get("contact_name") or "Not specified"
    days_inactive = _days_since_str(deal.get("last_activity_time"))

    return f"""Deal Intelligence Report for Pre-Meeting Battle Card

DEAL OVERVIEW:
- Deal Name: {deal.get('name', 'Unknown')}
- Company: {deal.get('account_name', '—')}
- Deal Amount: ${float(deal.get('amount') or 0):,.0f}
- Current Stage: {deal.get('stage', 'Unknown')}
- Close Date: {deal.get('closing_date') or 'Not set'}
- Probability: {deal.get('probability', 0)}%
- Owner: {deal.get('owner') or 'Unknown'}
- Primary Contact: {contact}
- Days in Current Stage: {deal.get('days_in_stage') or 'unknown'}

HEALTH SCORE: {health_result.total_score if health_result else 50}/100 ({health_result.health_label if health_result else 'unknown'})
HEALTH SIGNALS:
{signals_text if signals_text else "  No signal data available"}

LAST ACTIVITY: {days_inactive} days ago
NEXT STEP DEFINED: {deal.get('next_step') or 'None — no next step set'}
DESCRIPTION / NOTES: {deal.get('description') or 'None'}

ACTIVE WARNINGS:
{warnings_text if warnings_text else "  No active warnings"}

MEETING CONTEXT: {meeting_context if meeting_context.strip() else "General check-in / follow-up call"}

RECOMMENDATION FROM HEALTH SCORER: {health_result.recommendation if health_result else 'Review deal status'}
"""


async def _call_groq(deal_context: str) -> dict:
    client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))

    system_prompt = """You are a sales intelligence assistant. Given deal data, generate a concise pre-meeting battle card.

Respond ONLY with a valid JSON object. No markdown, no explanation, no code blocks. Just the raw JSON.

The JSON must have exactly these keys:
{
  "situation": "2-3 sentence summary of where this deal stands. Be direct and specific.",
  "last_interaction": "1-2 sentences about what happened last time based on the activity data. If unknown, say so directly.",
  "open_loops": ["thing promised/unresolved 1", "thing 2"],
  "key_contacts": [{"name": "Contact Name or Unknown", "role": "their role or unknown", "last_contact_days": 0}],
  "talk_track": ["Specific thing to cover on this call 1", "thing 2", "thing 3", "thing 4"],
  "watch_out": ["Risk or concern 1", "risk 2"],
  "one_liner": "The single most important thing to do on this call. One sentence, direct."
}

Rules:
- open_loops: max 4 items. If none, return empty array []
- key_contacts: if contact data is missing, return [{"name": "Unknown", "role": "Primary contact", "last_contact_days": -1}]
- talk_track: exactly 3-4 items, each starting with an action verb (Ask, Confirm, Address, Present, Review, Get)
- watch_out: max 3 items, focus on deal-killing risks
- one_liner: be specific to this deal, not generic advice
- Write like a smart sales manager briefing a rep 90 seconds before a call
- Never say "I" or reference yourself"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": deal_context},
        ],
    )

    try:
        return json.loads(response.choices[0].message.content.strip())
    except json.JSONDecodeError:
        logger.warning("Battle card: Groq returned non-JSON, using fallback")
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
        }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/battlecard/generate")
async def generate_battlecard(
    body: BattleCardRequest,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)
    deal_id = body.deal_id

    # Serve from cache if still fresh
    cached_entry = _battlecard_cache.get(deal_id)
    if cached_entry:
        age_minutes = (datetime.utcnow() - cached_entry["generated_at"]).total_seconds() / 60
        if age_minutes < CACHE_TTL_MINUTES:
            return {**cached_entry["data"], "cached": True}

    # Fetch deal
    is_demo = _is_demo(session)
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

    # Build context and call Claude
    context_str = _build_deal_context(deal, warnings, health_result, body.meeting_context)
    sections = await _call_groq(context_str)

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

    _battlecard_cache[deal_id] = {
        "data": response_data,
        "generated_at": datetime.utcnow(),
    }
    return response_data


@router.delete("/battlecard/cache/{deal_id}")
async def clear_battlecard_cache(deal_id: str):
    _battlecard_cache.pop(deal_id, None)
    return {"cleared": True, "deal_id": deal_id}
