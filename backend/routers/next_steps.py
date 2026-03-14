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


# TTL in seconds — next stepss cached for 1 hour with email context, 10 min without
CACHE_TTL_SECONDS = 3600
CACHE_TTL_NO_EMAIL = 600


# ── Request / helpers ─────────────────────────────────────────────────────────

class NextStepsRequest(BaseModel):
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


def _build_deal_context(deal: dict, warnings: list, health_result, meeting_context: str, email_context: str = "", contacts_block: str = "", zoho_notes_block: str = "") -> str:
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

    notes_section = f"""
ZOHO NOTES (rep notes logged in CRM — use to understand history, commitments, and context):
{zoho_notes_block if zoho_notes_block.strip() else "  No notes found in Zoho CRM."}
"""

    return f"""Deal Intelligence Report — Next Steps Analysis

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

{notes_section}
{email_section}"""


async def _call_groq(deal_context: str) -> dict:
    client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))

    system_prompt = """You are a sales execution coach. Based on deal data, email history, Zoho notes, and CRM activity, define the precise next steps a rep must take to advance this deal.

Your job is NOT a generic brief — it is a concrete action plan with the right channel (email, call, or WhatsApp message) for each action, grounded in what actually happened.

CRITICAL RULES:
- Read the EMAIL THREAD and ZOHO NOTES carefully. They are ground truth — they override CRM fields when they conflict.
- Every recommended next step must name the contact, the channel, the specific message/ask, and the reason why.
- Channel selection logic:
    * email: formal commitments, proposals, follow-ups with attachments, first outreach to new contacts
    * call: stalled deals, complex objections, negotiation, deals >30 days silent, when email tone is cool/disengaged
    * whatsapp: warm relationships with recent engagement, quick confirmations, reminders for scheduled calls, when buyer previously responded via informal channels
- If the email thread shows buyer disengagement, the next step must be a call — not an email.
- If no next step is in CRM AND no commitment in email thread, the first action must be to establish one.
- open_loops must come from the actual email thread or Zoho notes — unresolved questions, unkept commitments, unanswered asks.
- watch_out must name specific risk signals visible in the email tone, Zoho notes, or CRM data.
- never write generic actions like "follow up" — always say exactly what to say and why.

Respond ONLY with valid JSON. No markdown, no explanation:

{
  "situation": "2-3 sentences. Name company, stage, health score, and what the email thread + Zoho notes reveal about where this deal actually stands.",
  "last_interaction": "Reference the actual last touchpoint: who initiated it, channel used, when, what was said or committed. If no data: state what the CRM silence implies.",
  "next_steps": [
    {
      "action": "Specific action to take — name contact, what to say/ask",
      "channel": "email|call|whatsapp",
      "contact": "Contact name",
      "timing": "Today|Within 24h|This week|Before [date]",
      "why": "Reason grounded in email thread, notes, or CRM signal",
      "message_hint": "Opening line or key talking point for this touchpoint"
    }
  ],
  "open_loops": [
    "Specific unresolved commitment or question from email thread or Zoho notes — quote or paraphrase actual language",
    "item 2"
  ],
  "key_contacts": [{"name": "Contact Name", "role": "their role in this deal", "last_contact_days": 0, "engagement": "hot|warm|cold|silent"}],
  "watch_out": [
    "Specific risk 1 — reference the actual email pattern, note, or CRM signal",
    "risk 2"
  ],
  "one_liner": "One sentence. Name the company or contact. State what must happen on the next touchpoint and why it matters now.",
  "email_intelligence": {
    "last_buyer_reply": "Date and summary of last buyer email, or 'none found'",
    "buyer_tone": "positive|neutral|cool|disengaged|urgent",
    "crm_gap": "Yes — X emails found in Outlook not in CRM | No gap detected",
    "key_commitment": "Most important open commitment from email thread or Zoho notes, or 'none'"
  }
}

Rules:
- next_steps: 2-4 items ordered by priority. Each must have a specific channel, contact, and message_hint.
- open_loops: 1-4 items from actual data. If none, return [].
- watch_out: 2-3 items. Each must name the actual pattern, not a generic risk category.
- email_intelligence: always populate even if no email data — state that explicitly."""

    try:
        response = await client.chat.completions.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
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
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Truncated response — attempt to close open braces/brackets
            depth_brace = raw.count("{") - raw.count("}")
            depth_bracket = raw.count("[") - raw.count("]")
            raw_patched = raw.rstrip().rstrip(",") + ("]" * depth_bracket) + ("}" * depth_brace)
            return json.loads(raw_patched)
    except Exception as e:
        logger.warning("Next steps: Claude call failed: %s", e)
        return {
            "situation": "Unable to generate summary. Review deal manually in Zoho.",
            "last_interaction": "No recent activity data available.",
            "next_steps": [
                {"action": "Review deal status and open commitments", "channel": "call", "contact": "Primary contact", "timing": "Today", "why": "No AI analysis available — manual review required", "message_hint": "Hi, following up on our last conversation — wanted to check where things stand."},
            ],
            "open_loops": [],
            "key_contacts": [{"name": "Unknown", "role": "Primary contact", "last_contact_days": -1, "engagement": "unknown"}],
            "watch_out": ["Review deal warnings before next touchpoint"],
            "one_liner": "Establish clear next steps with a specific date.",
            "email_intelligence": {"last_buyer_reply": "unavailable", "buyer_tone": "neutral", "crm_gap": "unknown", "key_commitment": "none"},
        }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/next-steps/generate")
async def generate_next_steps(
    body: NextStepsRequest,
    authorization: str = Header(default=""),
):
    session = _decode_session(authorization)
    deal_id = body.deal_id
    is_demo = _is_demo(session)

    # Redis cache — user-scoped to prevent cross-tenant leakage
    _user = (session.get("email") or session.get("user_id") or "anon").replace(":", "_")
    _redis_key = _bck("next-steps", _user, deal_id)
    if not is_demo:
        _cached = await cache_get(_redis_key)
        if _cached:
            logger.debug("next-steps cache hit user=%s deal=%s", _user, deal_id)
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

    # Fetch Zoho notes
    zoho_notes_block = ""
    if not is_demo:
        try:
            from services.zoho_client import fetch_deal_notes
            notes = await fetch_deal_notes(session.get("access_token", ""), deal_id)
            if notes:
                lines = []
                for n in notes[:10]:
                    content = n.get("Note_Content") or n.get("note_content") or ""
                    title = n.get("Note_Title") or n.get("note_title") or "Note"
                    created = str(n.get("Created_Time") or n.get("created_time") or "")[:10]
                    owner = (n.get("Owner") or {}).get("name") or "rep"
                    if content:
                        lines.append(f"  [{created}] {owner} — {title}: {content[:300]}")
                zoho_notes_block = "\n".join(lines)
        except Exception as e:
            logger.warning("next-steps: Zoho notes fetch failed deal=%s: %s", deal_id, e)
    else:
        zoho_notes_block = (
            "  [2026-03-10] Alex (rep) — Pricing call: Discussed enterprise tier. Sarah mentioned budget approval needed from CFO by end of month.\n"
            "  [2026-03-05] Alex (rep) — Demo follow-up: James confirmed technical fit. Waiting on security review from IT team.\n"
            "  [2026-03-01] Alex (rep) — Initial meeting: Strong interest. Champion is James Liu. Economic buyer is Sarah Chen."
        )

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
            logger.warning("next-steps: email enrichment failed deal=%s: %s", deal_id, e)

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
            logger.warning("next-steps: contacts fetch failed deal=%s: %s", deal_id, e)
    else:
        # Demo contacts block
        contacts_block = (
            "CONFIRMED CONTACTS:\n"
            "  • Sarah Chen <sarah.chen@techcorp.com> | Role: Economic Buyer | Source: CRM (Zoho)\n"
            "  • James Liu <james.liu@techcorp.com> | Role: Champion | Source: CRM (Zoho)\n"
            "POTENTIAL PERSONAS (seen in Outlook emails, not yet confirmed by rep):\n"
            "  • Mike Torres <mike.torres@techcorp.com> | 3 email(s) | Last seen: 2026-03-08"
        )

    # Build context and call Claude — with compound intelligence + PG cache
    import asyncio
    import hashlib
    from services.ai_cache import get_or_generate, build_input_hash, build_prior_context

    # Inject prior intelligence (health + NBA + deal_insights) into deal context
    prior_ctx = await build_prior_context(deal_id, ["health_analysis", "nba", "deal_insights"])
    context_str = _build_deal_context(deal, warnings, health_result, body.meeting_context, email_context, contacts_block, zoho_notes_block)
    if prior_ctx:
        context_str = f"{prior_ctx}\n\n{context_str}"

    ns_hash = build_input_hash({
        "stage": deal.get("stage"),
        "health_score": health_result.total_score if health_result else 0,
        "email_hash": hashlib.sha256(email_context.encode()).hexdigest()[:16],
        "notes_hash": hashlib.sha256(zoho_notes_block.encode()).hexdigest()[:16],
    })

    try:
        sections = await asyncio.wait_for(
            get_or_generate(
                deal_id=deal_id,
                analysis_type="next_steps",
                input_hash=ns_hash,
                generator=lambda: _call_groq(context_str),
                result_text_fn=lambda r: r.get("one_liner", ""),
                model_used="claude-sonnet-4-6",
            ),
            timeout=55,
        )
    except asyncio.TimeoutError:
        logger.warning("next-steps: Claude timed out for deal=%s", deal_id)
        sections = {
            "situation": "AI analysis timed out — deal data loaded successfully, retry to generate full next steps.",
            "last_interaction": "Check CRM for latest activity.",
            "next_steps": [
                {"action": "Review deal status and define next commitment", "channel": "call", "contact": "Primary contact", "timing": "Today", "why": "AI timed out — manual review required", "message_hint": "Following up to confirm our next steps."},
            ],
            "open_loops": [],
            "key_contacts": [],
            "watch_out": ["AI analysis unavailable — review warnings manually"],
            "one_liner": "AI timed out — retry to generate full next steps.",
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


@router.delete("/next-steps/cache/{deal_id}")
async def clear_next_steps_cache(deal_id: str, authorization: str = Header(default="")):
    """Invalidate next steps cache for a deal. Clears all users' cached cards for this deal."""
    from services.cache import cache_delete_pattern
    await cache_delete_pattern(f"dealiq:next-steps:*:{deal_id}")
    return {"cleared": True, "deal_id": deal_id}
