from fastapi import APIRouter, Depends, Header, HTTPException
from database import get_db
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import base64
import json
from services.claude_client import detect_narrative_mismatch, analyse_discount_thread, get_deal_ai_insights
from services.email_coach import analyse_email_draft
from services.deal_autopsy import generate_deal_autopsy
from services.health_scorer import score_deal_from_zoho
from services.demo_data import SIMULATED_DEALS, SIMULATED_EMAILS, DEMO_TRANSCRIPT, DEMO_EMAIL
from models.schemas import (
    MismatchRequest, MismatchResult, MismatchFlag,
    DiscountAnalysis, DiscountMention,
    ACKResult, ACKDecision,
)
from datetime import datetime, timezone, timedelta

router = APIRouter()


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


def _fmt_emails(emails: List[Dict], limit: int = 5) -> str:
    """Format the last N emails into a compact context string for AI prompts."""
    if not emails:
        return "No email history available — analysis based on CRM data only."
    lines = []
    for e in emails[-limit:]:
        # Zoho CRM v2 uses "incoming" for received and "outgoing" for sent/BCC Dropbox.
        # Also handle legacy values: "received", "inbound", "sent".
        direction_val = (e.get("direction") or e.get("type") or "").lower()
        is_buyer = direction_val in ("incoming", "received", "inbound")
        direction = "← BUYER" if is_buyer else "→ REP"
        # Content field varies by Zoho endpoint/version.
        # _fetch_email_body already strips HTML; strip here as fallback safety.
        import re as _re
        def _clean(s: str) -> str:
            if s and "<" in s:
                s = _re.sub(r"<[^>]+>", " ", s)
                s = _re.sub(r"\s+", " ", s).strip()
            return s
        content = _clean(
            e.get("content")
            or e.get("html_body")
            or e.get("body")
            or e.get("text_body")
            or e.get("description")
            or e.get("summary")
            or e.get("snippet")  # email_related_list format
            or ""
        )
        # Time field: "sent_time" for standard, "date" for email_related_list
        sent_at = e.get("sent_time") or e.get("date") or "Unknown date"
        lines.append(
            f"  [{direction}] {sent_at} | Subject: {e.get('subject', 'No subject')}\n"
            f"  {content[:400]}"
        )
    return "\n\n".join(lines)


async def _fetch_email_context(deal_id: str, session: dict, limit: int = 8) -> str:
    """
    Fetch and format emails for a deal — Outlook primary, Zoho supplementary.
    Returns a structured string ready for AI prompts.
    Gracefully falls back to Zoho-only or demo data.
    """
    import logging
    _log = logging.getLogger(__name__)

    if _is_demo(session):
        emails = SIMULATED_EMAILS.get(deal_id, [])
        return _fmt_emails(emails, limit)

    try:
        from services.outlook_enrichment import get_enriched_emails, fmt_emails_for_ai
        user_key = session.get("email") or session.get("user_id") or "default"
        emails = await get_enriched_emails(
            deal_id=deal_id,
            zoho_token=session["access_token"],
            user_key=user_key,
            limit=limit,
        )
        if emails:
            return fmt_emails_for_ai(emails, limit=limit)
    except Exception as exc:
        _log.warning("Enriched email fetch failed deal=%s: %s — falling back to Zoho", deal_id, exc)

    # Fallback: Zoho only
    try:
        from services.zoho_client import fetch_deal_emails
        emails = await fetch_deal_emails(session["access_token"], deal_id)
        return _fmt_emails(emails, limit)
    except Exception as exc:
        _log.warning("Zoho email fetch failed deal=%s: %s", deal_id, exc)
        return "No email history available — analysis based on CRM data only."


def _build_activity_context(deal: dict) -> str:
    """Build a compact activity + contact roles context string for AI prompts.
    Reads fields populated by _enrich_deal when real Zoho data is available.
    """
    lines = []

    contact_roles = deal.get("contact_roles") or []
    if contact_roles:
        lines.append("CONTACTS & ROLES:")
        for c in contact_roles:
            role = c.get("role") or "No role specified"
            name = c.get("name") or "Unknown"
            email = c.get("email") or ""
            lines.append(f"  • {name} ({role})" + (f" — {email}" if email else ""))
    else:
        lines.append("CONTACTS: No contact role data available in CRM")

    # Build contacts section from all contact sources
    contacts = deal.get("contact_roles") or deal.get("contacts") or []
    if contacts:
        contacts_lines = []
        for c in contacts:
            name = c.get("name") or c.get("Full_Name") or ""
            email = c.get("email") or c.get("Email") or ""
            role = c.get("role") or c.get("Contact_Role") or "Unknown"
            contacts_lines.append(f"  - {name} <{email}> | {role}")
        contacts_section = "CONTACTS:\n" + "\n".join(contacts_lines)
    else:
        contacts_section = "CONTACTS: None linked in CRM — deal may lack key stakeholders"
    lines.append(f"\n{contacts_section}")

    closed_meetings = deal.get("closed_meetings") or []
    if closed_meetings:
        lines.append("\nCOMPLETED MEETINGS:")
        for m in closed_meetings[:5]:
            lines.append(f"  • {m.get('Subject', 'Untitled')} — {m.get('Start_DateTime', m.get('Status', ''))}")

    closed_tasks = deal.get("closed_tasks") or []
    if closed_tasks:
        lines.append("\nCOMPLETED TASKS:")
        for t in closed_tasks[:5]:
            lines.append(f"  • {t.get('Subject', 'Untitled')} — closed {t.get('Closed_Time', t.get('Due_Date', ''))}")

    if not closed_meetings and not closed_tasks:
        lines.append("\nACTIVITIES: No completed activities found in CRM for this deal")

    return "\n".join(lines)


# ── Narrative Mismatch ────────────────────────────────────────────────────────

@router.post("/mismatch", response_model=MismatchResult)
async def check_mismatch(
    request: MismatchRequest,
    authorization: str = Header(...),
):
    _decode_session(authorization)
    if not request.transcript.strip() or not request.email_draft.strip():
        raise HTTPException(status_code=400, detail="Both transcript and email_draft are required")

    raw = await detect_narrative_mismatch(request.transcript, request.email_draft)
    flags = [
        MismatchFlag(
            category=m.get("category", "commitment"),
            description=m.get("description", ""),
            severity=m.get("severity", "medium"),
            suggested_fix=m.get("suggested_fix", "Review and add missing commitment to email."),
        )
        for m in raw.get("mismatches", [])
    ]
    return MismatchResult(
        mismatches=flags,
        deal_health_impact=raw.get("deal_health_impact", 0),
        clean=len(flags) == 0,
        summary=raw.get("summary", "Analysis complete."),
    )


@router.get("/mismatch/demo", response_model=MismatchResult)
async def demo_mismatch():
    raw = await detect_narrative_mismatch(DEMO_TRANSCRIPT, DEMO_EMAIL)
    flags = [
        MismatchFlag(
            category=m.get("category", "commitment"),
            description=m.get("description", ""),
            severity=m.get("severity", "medium"),
            suggested_fix=m.get("suggested_fix", ""),
        )
        for m in raw.get("mismatches", [])
    ]
    return MismatchResult(
        mismatches=flags,
        deal_health_impact=raw.get("deal_health_impact", 0),
        clean=len(flags) == 0,
        summary=raw.get("summary", ""),
    )


# ── Live Email Coach ──────────────────────────────────────────────────────────

class EmailCoachRequest(BaseModel):
    email_draft: str
    deal_id: Optional[str] = None
    deal_context: Optional[Dict[str, Any]] = None


@router.post("/email-coach")
async def live_email_coach(
    request: EmailCoachRequest,
    authorization: str = Header(...),
):
    """
    Fast real-time coaching as the rep types an email.
    Returns health impact preview, missing elements, and top suggestion.
    Optimised for debounced calls — typically < 1s.
    """
    session = _decode_session(authorization)

    # Build deal context from deal_id if not provided inline
    deal_context = request.deal_context or {}
    if request.deal_id and not deal_context:
        if _is_demo(session):
            matches = [d for d in SIMULATED_DEALS if d["id"] == request.deal_id]
            if matches:
                d = matches[0]
                health = score_deal_from_zoho(d)
                deal_context = {
                    "name": d.get("name"),
                    "stage": d.get("stage"),
                    "health_score": health.total_score,
                    "health_label": health.health_label,
                    "days_stalled": d.get("activity_count_30d", 0),
                }

    email_context = ""
    if request.deal_id:
        email_context = await _fetch_email_context(request.deal_id, session, limit=3)

    result = await analyse_email_draft(
        email_draft=request.email_draft,
        deal_context=deal_context,
        email_context=email_context,
    )
    return result


# ── Discount Heat Map ─────────────────────────────────────────────────────────

@router.post("/discount")
async def analyse_discount(
    email_thread: str,
    deal_id: Optional[str] = None,
    authorization: str = Header(...),
):
    _decode_session(authorization)
    raw = await analyse_discount_thread(email_thread)
    mentions = [
        DiscountMention(
            mention_index=m.get("mention_index", i + 1),
            context=m.get("context", ""),
            raised_by=m.get("raised_by", "unknown"),
            discount_value=m.get("discount_value"),
        )
        for i, m in enumerate(raw.get("mentions", []))
    ]
    return DiscountAnalysis(
        deal_id=deal_id or "unknown",
        total_mentions=len(mentions),
        mentions=mentions,
        pressure_level=raw.get("pressure_level", "normal"),
        benchmark_comparison=raw.get("benchmark_comparison", ""),
        recommendation=raw.get("recommendation", ""),
    )


# ── Advance / Close / Kill ────────────────────────────────────────────────────

@router.get("/ack/{deal_id}", response_model=ACKResult)
async def get_ack_recommendation(deal_id: str, authorization: str = Header(...)):
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        from routers.deals import get_fully_enriched_deal
        try:
            raw = await get_fully_enriched_deal(session["access_token"], deal_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Enrich with contact/persona data
    deal_with_health = dict(raw)
    contacts_block = ""
    if not simulated:
        try:
            from services.contact_intelligence import get_deal_contacts, format_contacts_for_ai
            import logging as _logging
            _log = _logging.getLogger(__name__)
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
            # Merge confirmed contact count into deal for health scoring
            total_confirmed = len(contacts_data.get("zoho_contacts", [])) + len(contacts_data.get("confirmed_personas", []))
            if total_confirmed:
                deal_with_health["contact_count"] = total_confirmed
                deal_with_health["contact_roles"] = contacts_data.get("zoho_contacts", []) + contacts_data.get("confirmed_personas", [])
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("analysis: contacts fetch failed deal=%s: %s", deal_id, e)

    # Fetch Outlook emails for communication-based scoring
    _outlook_emails_for_health: list = []
    if not simulated:
        try:
            from services.outlook_enrichment import get_enriched_emails
            _user_key = session.get("email") or session.get("user_id") or "default"
            _outlook_emails_for_health = await get_enriched_emails(
                deal_id=deal_id,
                zoho_token=session.get("access_token", ""),
                user_key=_user_key,
                limit=20,
            )
        except Exception:
            pass

    health = score_deal_from_zoho(deal_with_health, outlook_emails=_outlook_emails_for_health or None)

    last_activity = raw.get("last_activity_time")
    days_stalled = 0
    if last_activity:
        try:
            dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
            days_stalled = (datetime.now(timezone.utc) - dt).days
        except Exception:
            days_stalled = 0

    if health.health_label == "zombie":
        recommendation = "kill"
        reasoning = f"This deal has been stalled for {days_stalled} days with no buyer engagement. Removing it from pipeline will improve forecast accuracy."
    elif health.health_label == "critical" and days_stalled > 21:
        recommendation = "escalate"
        reasoning = f"Deal is in critical health and has stalled for {days_stalled} days. Manager review required before further rep action."
    elif health.total_score >= 50 and days_stalled <= 14:
        recommendation = "advance"
        reasoning = f"Deal signals are recoverable. Define a specific next step and contact within 48 hours."
    elif health.total_score < 50 and days_stalled > 14:
        recommendation = "escalate"
        reasoning = f"Below-average health score with {days_stalled} days of inactivity. Escalate for a fresh perspective."
    else:
        recommendation = "advance"
        reasoning = "Deal has stalled but fundamentals remain intact. Commit to a clear next action now."

    signals = [f"{s.name}: {s.detail}" for s in health.signals if s.label in ("critical", "warn")]

    return ACKResult(
        deal_id=deal_id,
        deal_name=raw.get("name", "Unknown Deal"),
        days_stalled=days_stalled,
        recommendation=recommendation,
        reasoning=reasoning,
        supporting_signals=signals[:4],
    )


@router.post("/ack/{deal_id}/decide")
async def log_ack_decision(
    deal_id: str,
    decision: ACKDecision,
    authorization: str = Header(...),
    db=Depends(get_db),
):
    session = _decode_session(authorization)
    user_email = session.get("email", "unknown")

    # Persist to DB (no-ops gracefully if DB unavailable)
    from services.decision_db import persist_decision
    await persist_decision(
        db,
        deal_zoho_id=deal_id,
        action=decision.decision,
        user_email=user_email,
        reasoning=decision.notes,
    )

    return {
        "deal_id": deal_id,
        "decision": decision.decision,
        "logged": True,
        "message": f"Decision '{decision.decision}' logged for deal {deal_id}.",
        "next_step": decision.next_step,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Deal Autopsy ──────────────────────────────────────────────────────────────

class AutopsyRequest(BaseModel):
    deal_id: str
    kill_reason: Optional[str] = None


@router.post("/autopsy")
async def run_deal_autopsy(
    request: AutopsyRequest,
    authorization: str = Header(...),
):
    """
    Generate a full post-mortem for a killed or lost deal.
    Returns structured learnings to prevent the same pattern repeating.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == request.deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        from routers.deals import get_fully_enriched_deal
        try:
            raw = await get_fully_enriched_deal(session["access_token"], request.deal_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    from routers.deals import build_deal_context
    health = score_deal_from_zoho(raw)
    deal_with_health = {
        **raw,
        "health_score": health.total_score,
        "health_label": health.health_label,
    }

    signals = [
        {"name": s.name, "score": s.score, "max_score": s.max_score, "label": s.label, "detail": s.detail}
        for s in health.signals
    ]

    emails = (
        SIMULATED_EMAILS.get(request.deal_id, []) if simulated
        else raw.get("_emails_raw", [])
    )
    email_context = _fmt_emails(emails)
    activity_context = _build_activity_context(deal_with_health)

    autopsy = await generate_deal_autopsy(
        deal=deal_with_health,
        health_signals=signals,
        kill_reason=request.kill_reason,
        email_context=email_context,
        activity_context=activity_context,
        deal_context=build_deal_context(deal_with_health),
    )

    return {
        "deal_id": request.deal_id,
        "autopsy": autopsy,
        "health_at_death": {"score": health.total_score, "label": health.health_label},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/autopsy/demo")
async def demo_autopsy():
    """Demo autopsy on the FinanceFlow zombie deal — no auth required."""
    demo_deal = next((d for d in SIMULATED_DEALS if d["id"] == "sim_004"), SIMULATED_DEALS[0])
    health = score_deal_from_zoho(demo_deal)
    deal_with_health = {**demo_deal, "health_score": health.total_score, "health_label": health.health_label}
    signals = [
        {"name": s.name, "score": s.score, "max_score": s.max_score, "label": s.label, "detail": s.detail}
        for s in health.signals
    ]
    autopsy = await generate_deal_autopsy(
        deal=deal_with_health,
        health_signals=signals,
        kill_reason="No response after 5 follow-ups. Buyer went silent after pricing discussion.",
    )


# ── Stage Drift Detection ─────────────────────────────────────────────────────

ZOHO_STAGES = [
    "Qualification",
    "Needs Analysis",
    "Value Proposition",
    "Id. Decision Makers",
    "Perception Analysis",
    "Proposal/Price Quote",
    "Negotiation/Review",
    "Contract Sent",
    "Closed Won",
    "Closed Lost",
]

# Stage keywords: if these phrases appear in emails/context, the deal is likely at that stage
_STAGE_SIGNALS: dict[str, list[str]] = {
    "Qualification":        ["intro call", "discovery call", "initial meeting", "first call", "qualify", "qualification"],
    "Needs Analysis":       ["requirements", "use case", "pain points", "needs analysis", "scoping", "current process"],
    "Value Proposition":    ["demo", "product demo", "demo done", "showed the product", "walkthrough", "product walk"],
    "Proposal/Price Quote": ["proposal", "quote", "pricing", "cost breakdown", "roi", "business case"],
    "Negotiation/Review":   ["negotiation", "negotiate", "counter", "revised pricing", "revised proposal", "legal review"],
    "Contract Sent":        ["contract", "agreement", "msa", "nda", "docusign", "signed", "order form", "statement of work", "sow"],
    "Closed Won":           ["purchase order", "po sent", "kicked off", "onboarding", "invoice"],
}


class StageCheckRequest(BaseModel):
    deal_id: str
    current_stage: str
    deal_name: Optional[str] = None
    account_name: Optional[str] = None


@router.post("/stage-check")
async def check_stage_drift(
    request: StageCheckRequest,
    authorization: str = Header(...),
):
    """
    Analyze recent emails + activities to detect if the CRM stage is stale.
    Returns suggested_stage + reasoning when drift is detected, or no_drift=True.
    """
    import logging
    import os
    _log = logging.getLogger(__name__)
    session = _decode_session(authorization)

    # ── 1. Fetch email context ────────────────────────────────────────────────
    email_context = await _fetch_email_context(request.deal_id, session, limit=10)

    # ── 2. Fast heuristic: keyword scan on email context ─────────────────────
    email_lower = email_context.lower()
    keyword_hits: dict[str, int] = {}
    for stage, keywords in _STAGE_SIGNALS.items():
        hits = sum(1 for kw in keywords if kw in email_lower)
        if hits:
            keyword_hits[stage] = hits

    # ── 3. Demo mode — lightweight path, no Groq call ────────────────────────
    if _is_demo(session):
        # Simulate a drift: if stage is "Value Proposition" (demo done), suggest contract stage
        demo_drift_map = {
            "Value Proposition": ("Contract Sent", "Emails mention contract review and docusign link shared with buyer."),
            "Needs Analysis":    ("Proposal/Price Quote", "Recent emails discuss pricing and ROI breakdown."),
            "Qualification":     ("Needs Analysis", "Emails show completed discovery and requirements discussion."),
        }
        if request.current_stage in demo_drift_map:
            sugg, reason = demo_drift_map[request.current_stage]
            return {
                "no_drift": False,
                "current_stage": request.current_stage,
                "suggested_stage": sugg,
                "confidence": "high",
                "reasoning": reason,
                "evidence": [f"Email context contains language consistent with {sugg} stage."],
            }
        return {"no_drift": True, "current_stage": request.current_stage}

    # ── 4. Call Groq for AI-powered detection ────────────────────────────────
    try:
        from services.ai_client import AsyncAnthropicCompat as AsyncGroq
        client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))

        prompt = f"""You are a CRM data quality checker for a B2B sales team.

TASK: Determine if the CRM deal stage is stale or accurate based on recent email activity.

DEAL: {request.deal_name or request.deal_id} ({request.account_name or "Unknown Account"})
CURRENT CRM STAGE: {request.current_stage}

VALID STAGES (in order):
{chr(10).join(f"  {i+1}. {s}" for i, s in enumerate(ZOHO_STAGES))}

RECENT EMAIL THREAD:
{email_context}

INSTRUCTIONS:
- Read the email thread carefully.
- If the emails clearly show the deal is at a DIFFERENT (usually more advanced) stage than CRM says, return that stage.
- Only flag drift if you are confident (emails contain clear, specific evidence like "sending the contract", "docusign link", "proposal attached", etc.)
- If emails are ambiguous or absent, return no_drift.
- Do NOT suggest Closed Won or Closed Lost unless there is explicit confirmation.

Respond ONLY with valid JSON — no markdown, no explanation:
{{
  "no_drift": true/false,
  "suggested_stage": "Exact stage name from the list above, or null if no_drift",
  "confidence": "high|medium|low",
  "reasoning": "One sentence. Cite specific email evidence.",
  "evidence": ["specific quote or signal from email 1", "signal 2"]
}}"""

        resp = await client.chat.completions.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            temperature=0.1,
            messages=[
                {"role": "system", "content": "You are a CRM data quality checker. Respond ONLY with valid JSON — no markdown, no explanation."},
                {"role": "user", "content": prompt},
            ],
        )

        raw = resp.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        result = json.loads(raw)

        # Validate suggested_stage is a real stage
        if not result.get("no_drift") and result.get("suggested_stage") not in ZOHO_STAGES:
            return {"no_drift": True, "current_stage": request.current_stage}

        # Don't flag if suggestion == current stage
        if result.get("suggested_stage") == request.current_stage:
            return {"no_drift": True, "current_stage": request.current_stage}

        return {"current_stage": request.current_stage, **result}

    except Exception as exc:
        _log.warning("stage-check Groq call failed deal=%s: %s", request.deal_id, exc)
        return {"no_drift": True, "current_stage": request.current_stage}
    return {"deal_id": "sim_004", "autopsy": autopsy, "health_at_death": {"score": health.total_score, "label": health.health_label}}
