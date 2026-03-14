"""
Ask DealIQ — Auth-Required Endpoints
======================================
All /ask/* routes (non-demo). Bearer token required.
Works in demo mode (DEMO_MODE token) and real Zoho mode.
"""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import base64
import json
import logging
import time
from datetime import datetime, timezone

from services.ask_dealiq_prompts import PRESET_QUESTIONS
from services.ask_dealiq_service import (
    ask_about_deal,
    ask_meddic_analysis,
    generate_deal_brief,
    ask_across_deals,
)
from services.email_generator import EmailGenerator
from services.demo_data import SIMULATED_DEALS, SIMULATED_EMAILS
import services.ai_router_ask as ai_router

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/ask", tags=["Ask DealIQ"])

# ── Simple in-memory email cache (5-min TTL, per deal) ───────────────────────
_EMAIL_CACHE: dict[str, tuple[float, list]] = {}  # deal_id → (expires_at, emails)
_EMAIL_CACHE_TTL = 300  # seconds


# ── Auth helpers (same pattern as analysis.py) ────────────────────────────────

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


# ── Data fetchers ─────────────────────────────────────────────────────────────

def _get_demo_deal(deal_id: str) -> dict:
    """Get a demo deal by ID, or use the first one as fallback."""
    from services.ask_demo_data import DEMO_DEAL
    if deal_id in ("demo_1", "demo"):
        return DEMO_DEAL
    match = next((d for d in SIMULATED_DEALS if d["id"] == deal_id), None)
    if not match:
        raise HTTPException(status_code=404, detail=f"Deal '{deal_id}' not found in demo data")
    return match


def _get_demo_emails(deal_id: str) -> list:
    from services.ask_demo_data import DEMO_EMAILS
    if deal_id in ("demo_1", "demo"):
        return DEMO_EMAILS
    return SIMULATED_EMAILS.get(deal_id, [])


def _get_demo_contacts(deal_id: str) -> list:
    """Return contacts list for a demo deal (from SIMULATED_ACTIVITIES)."""
    from services.demo_data import SIMULATED_ACTIVITIES
    bundle = SIMULATED_ACTIVITIES.get(deal_id, {})
    return bundle.get("contacts", [])


async def _resolve_primary_contact(session: dict, deal_id: str) -> Optional[dict]:
    """
    Return the primary contact (with a resolvable email) for a deal.
    Demo mode: pull from SIMULATED_ACTIVITIES.
    Real mode: call get_contacts_for_deal and pick first contact with an email.
    Returns { name, email } or None.
    """
    if _is_demo(session):
        contacts = _get_demo_contacts(deal_id)
    else:
        from services.zoho_client import get_contacts_for_deal
        contacts = await get_contacts_for_deal(session["access_token"], deal_id)

    for c in contacts:
        email = (c.get("email") or "").strip()
        name = (c.get("name") or "").strip()
        if email:
            return {"name": name or email, "email": email}
    return None


def _get_demo_transcript(deal_id: str) -> Optional[str]:
    from services.ask_demo_data import DEMO_TRANSCRIPT
    if deal_id in ("demo_1", "demo"):
        return DEMO_TRANSCRIPT
    return None


async def _fetch_real_deal(access_token: str, deal_id: str) -> dict:
    try:
        from routers.deals import get_fully_enriched_deal
        return await get_fully_enriched_deal(access_token, deal_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch deal: {exc}")


async def _fetch_real_emails(session: dict, deal_id: str) -> list:
    """
    Fetch enriched emails for a deal — Outlook primary, Zoho supplementary.
    Returns merged, normalised, newest-first list via outlook_enrichment pipeline.
    Falls back to Zoho-only on error.
    """
    cached = _EMAIL_CACHE.get(deal_id)
    if cached and time.monotonic() < cached[0]:
        _log.debug("Email cache hit for deal=%s count=%d", deal_id, len(cached[1]))
        return cached[1]
    try:
        from services.outlook_enrichment import get_enriched_emails
        user_key = session.get("email") or session.get("user_id") or "default"
        emails = await get_enriched_emails(
            deal_id=deal_id,
            zoho_token=session["access_token"],
            user_key=user_key,
            limit=10,
        )
        _log.info("Email fetch for deal=%s: %d enriched emails", deal_id, len(emails))
        _EMAIL_CACHE[deal_id] = (time.monotonic() + _EMAIL_CACHE_TTL, emails)
        return emails
    except Exception as exc:
        _log.warning("Enriched email fetch failed for deal=%s: %s — falling back to Zoho", deal_id, exc)
    try:
        from services.zoho_client import fetch_deal_emails
        from routers.email_intel import _normalise_zoho_email
        raw = await fetch_deal_emails(session["access_token"], deal_id)
        emails = [_normalise_zoho_email(e) for e in raw]
        _EMAIL_CACHE[deal_id] = (time.monotonic() + _EMAIL_CACHE_TTL, emails)
        return emails
    except Exception as exc2:
        _log.warning("Zoho email fetch failed for deal=%s: %s", deal_id, exc2)
        return []


# ── Pipeline deal fetcher ─────────────────────────────────────────────────────

def _score_deals(deals: list) -> list:
    """Apply health scoring to an already-normalized deal list (e.g. SIMULATED_DEALS)."""
    from services.health_scorer import score_deal_from_zoho
    out = []
    for d in deals:
        if "health_score" not in d or "health_label" not in d:
            d = dict(d)  # don't mutate the original
            result = score_deal_from_zoho(d)
            d["health_score"] = result.total_score
            d["health_label"] = result.health_label
        out.append(d)
    return out


async def _fetch_and_score_deals(access_token: str) -> list:
    """
    Fetch all Zoho deals, normalize field names, add proxy enrichment,
    and health-score each deal so ask_across_deals has real data to reason over.
    No per-deal API calls — uses probability-based proxies for activity/contact fields.
    """
    from services.zoho_client import fetch_deals, map_zoho_deal
    from services.health_scorer import score_deal_from_zoho

    all_deals = []
    page = 1
    while True:
        raw_page = await fetch_deals(access_token, page=page, per_page=200)
        if not raw_page:
            break
        for raw in raw_page:
            d = map_zoho_deal(raw)
            # Lightweight proxy enrichment — same logic as routers/deals.py _enrich_deal
            prob = d.get("probability") or 0
            d["activity_count_30d"]       = 3 if prob >= 50 else 1
            d["economic_buyer_engaged"]   = prob >= 70
            d["discount_mention_count"]   = 0
            d["has_completed_meeting"]    = False
            d["days_in_stage"]            = 0
            d["last_activity_days"]       = 0
            d["days_since_buyer_response"]= 0
            # Score
            result = score_deal_from_zoho(d)
            d["health_score"] = result.total_score
            d["health_label"] = result.health_label
            all_deals.append(d)
        if len(raw_page) < 200:
            break
        page += 1
    return all_deals


# ── Request / Response models ─────────────────────────────────────────────────

class DealQuestionRequest(BaseModel):
    deal_id: str
    question: str = Field(..., max_length=500)


class MeddicRequest(BaseModel):
    deal_id: str
    transcript_id: Optional[str] = None


class BriefRequest(BaseModel):
    deal_id: str


class FollowUpEmailRequest(BaseModel):
    deal_id: str
    transcript_id: Optional[str] = None
    tone_override: Optional[str] = None        # formal | casual | urgent
    additional_context: Optional[str] = None   # extra instructions passed to AI


class PipelineQuestionRequest(BaseModel):
    question: str = Field(..., max_length=500)
    filters: Optional[Dict[str, Any]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/presets")
def get_presets():
    """Return preset questions for the UI quick-action buttons. No rate limit needed."""
    return PRESET_QUESTIONS


@router.post("/deal")
async def ask_deal(
    request: DealQuestionRequest,
    authorization: str = Header(...),
):
    """
    Ask any natural language question about a specific deal.
    Assembles context from emails, transcripts, health scores, and CRM data.
    """
    if not ai_router.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured. Set GROQ_API_KEY.")

    session = _decode_session(authorization)

    if _is_demo(session):
        deal = _get_demo_deal(request.deal_id)
        emails = _get_demo_emails(request.deal_id)
        transcript = _get_demo_transcript(request.deal_id)
    else:
        deal = await _fetch_real_deal(session["access_token"], request.deal_id)
        emails = await _fetch_real_emails(session, request.deal_id)
        transcript = deal.get("_latest_transcript")  # populated by enriched deal if available

    # Compound intelligence: inject all prior analyses so Q&A has full context
    from services.ai_cache import build_prior_context
    prior_ctx = await build_prior_context(request.deal_id)
    if prior_ctx:
        deal["_prior_intelligence"] = prior_ctx

    result = await ask_about_deal(
        deal=deal,
        emails=emails,
        transcript=transcript,
        question=request.question,
    )

    return {
        **result,
        "deal_id": request.deal_id,
        "question": request.question,
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/deal/meddic")
async def deal_meddic_analysis(
    request: MeddicRequest,
    authorization: str = Header(...),
):
    """
    MEDDIC framework analysis of the most recent (or specified) call transcript.
    Returns structured 6-element breakdown with evidence from the transcript.
    """
    if not ai_router.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured. Set GROQ_API_KEY.")

    session = _decode_session(authorization)

    if _is_demo(session):
        deal = _get_demo_deal(request.deal_id)
        emails = _get_demo_emails(request.deal_id)
        transcript = _get_demo_transcript(request.deal_id)
    else:
        deal = await _fetch_real_deal(session["access_token"], request.deal_id)
        emails = await _fetch_real_emails(session, request.deal_id)
        transcript = deal.get("_latest_transcript")

    import hashlib
    from services.ai_cache import get_or_generate, build_input_hash, build_prior_context

    # Compound intelligence: inject prior health + NBA into context
    prior_ctx = await build_prior_context(request.deal_id, ["health_analysis", "nba"])
    if prior_ctx:
        deal["_prior_intelligence"] = prior_ctx

    cache_input = {
        "stage": deal.get("stage"),
        "health_score": deal.get("health_score"),
        "transcript_hash": hashlib.sha256((transcript or "").encode()).hexdigest()[:16],
        "email_count": len(emails),
    }
    input_hash = build_input_hash(cache_input)

    result = await get_or_generate(
        deal_id=request.deal_id,
        analysis_type="ask_meddic",
        input_hash=input_hash,
        generator=lambda: ask_meddic_analysis(deal=deal, emails=emails, transcript=transcript),
        result_text_fn=lambda r: r.get("overall_score", ""),
        model_used="claude-sonnet-4-6",
    )

    return {
        **result,
        "deal_id": request.deal_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/deal/brief")
async def deal_brief(
    request: BriefRequest,
    authorization: str = Header(...),
):
    """
    Generate a comprehensive deal brief — structured for manager review.
    Covers snapshot, timeline, stakeholders, risks, and recommended actions.
    """
    if not ai_router.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured. Set GROQ_API_KEY.")

    session = _decode_session(authorization)

    if _is_demo(session):
        deal = _get_demo_deal(request.deal_id)
        emails = _get_demo_emails(request.deal_id)
        transcript = _get_demo_transcript(request.deal_id)
    else:
        deal = await _fetch_real_deal(session["access_token"], request.deal_id)
        emails = await _fetch_real_emails(session, request.deal_id)
        transcript = deal.get("_latest_transcript")

    import hashlib
    from services.ai_cache import get_or_generate, build_input_hash, build_prior_context

    # Compound intelligence: inject all prior analyses into brief
    prior_ctx = await build_prior_context(request.deal_id, ["health_analysis", "nba", "deal_insights"])
    if prior_ctx:
        deal["_prior_intelligence"] = prior_ctx

    cache_input = {
        "stage": deal.get("stage"),
        "amount": deal.get("amount"),
        "health_score": deal.get("health_score"),
        "email_count": len(emails),
        "has_transcript": bool(transcript),
    }
    input_hash = build_input_hash(cache_input)

    result = await get_or_generate(
        deal_id=request.deal_id,
        analysis_type="ask_brief",
        input_hash=input_hash,
        generator=lambda: generate_deal_brief(deal=deal, emails=emails, transcript=transcript),
        result_text_fn=lambda r: r.get("executive_summary", r.get("summary", "")),
        model_used="claude-sonnet-4-6",
    )

    return {
        **result,
        "deal_id": request.deal_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/deal/follow-up-email")
async def deal_follow_up_email(
    request: FollowUpEmailRequest,
    authorization: str = Header(...),
):
    """
    Generate a context-rich follow-up email using the Context Engine.
    Two-pass: transcript pre-processing (structured intel) → email generation.
    Works with or without a transcript; falls back to re-engagement email from deal context.
    """
    if not ai_router.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured. Set GROQ_API_KEY.")

    session = _decode_session(authorization)

    # Resolve primary contact first — fail fast if none has an email
    recipient = await _resolve_primary_contact(session, request.deal_id)
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail="No contact email found for this deal. Add a contact with an email address in your CRM."
        )

    if _is_demo(session):
        deal = _get_demo_deal(request.deal_id)
        emails = _get_demo_emails(request.deal_id)
        transcript = _get_demo_transcript(request.deal_id)
    else:
        deal = await _fetch_real_deal(session["access_token"], request.deal_id)
        emails = await _fetch_real_emails(session, request.deal_id)
        transcript = deal.get("_latest_transcript")

    result = await EmailGenerator().generate(
        deal=deal,
        emails=emails,
        transcript=transcript,
        tone_override=request.tone_override,
        additional_context=request.additional_context,
    )

    return {
        **result,
        "deal_id": request.deal_id,
        "recipient": recipient,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/pipeline")
async def ask_pipeline(
    request: PipelineQuestionRequest,
    authorization: str = Header(...),
):
    """
    Ask a question across all deals (or a filtered subset).
    Examples: 'Which deals are at risk?', 'What deals have no next step?'
    """
    if not ai_router.is_configured():
        raise HTTPException(status_code=503, detail="AI service not configured. Set GROQ_API_KEY.")

    session = _decode_session(authorization)

    if _is_demo(session):
        deals = _score_deals(SIMULATED_DEALS)
    else:
        try:
            deals = await _fetch_and_score_deals(session["access_token"])
        except Exception as exc:
            _log.error("Failed to fetch deals for pipeline query: %s", exc)
            raise HTTPException(status_code=502, detail=f"Failed to fetch deals from CRM: {exc}")

    result = await ask_across_deals(
        deals=deals,
        question=request.question,
        filters=request.filters,
    )

    return {
        **result,
        "question": request.question,
        "filters_applied": request.filters or {},
        "queried_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history")
async def get_ask_history(
    authorization: str = Header(...),
    deal_id: Optional[str] = None,
    limit: int = 20,
):
    """
    Returns recent Ask DealIQ queries for the current user.
    Query log is in-memory only (no persistent audit log in current implementation).
    """
    _decode_session(authorization)
    # Audit log persistence is a future enhancement — DB layer not yet in place.
    return {
        "history": [],
        "message": "Query history will be available once the database layer is configured.",
        "limit": limit,
        "deal_id": deal_id,
    }
