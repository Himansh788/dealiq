from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import base64
import json
from services.ai_rep import generate_next_best_action, generate_email_draft, handle_objection, generate_call_brief
from services.health_scorer import score_deal_from_zoho
from services.demo_data import SIMULATED_DEALS, SIMULATED_EMAILS
from datetime import datetime, timezone
# build_deal_context imported inline to avoid circular import at module load

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class NBARequest(BaseModel):
    deal_id: str
    rep_name: Optional[str] = "the sales rep"


class EmailDraftRequest(BaseModel):
    deal_id: str
    rep_name: Optional[str] = "the sales rep"
    email_objective: Optional[str] = "Re-engage buyer and establish clear next step"
    action_context: Optional[str] = ""


class EmailApprovalRequest(BaseModel):
    deal_id: str
    subject: str
    body: str
    rep_name: str
    approved: bool
    edits: Optional[str] = None


class ObjectionRequest(BaseModel):
    deal_id: str
    objection: str
    rep_name: Optional[str] = "the sales rep"


class ActionApprovalRequest(BaseModel):
    deal_id: str
    action_plan: Dict[str, Any]
    approved: bool
    rep_feedback: Optional[str] = None


class CallBriefRequest(BaseModel):
    deal_id: str
    rep_name: Optional[str] = "the sales rep"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


async def _get_deal(deal_id: str, session: dict) -> dict:
    if _is_demo(session):
        matches = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not matches:
            raise HTTPException(status_code=404, detail="Deal not found")
        return matches[0]
    else:
        from routers.deals import get_fully_enriched_deal
        try:
            return await get_fully_enriched_deal(session["access_token"], deal_id)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


def _get_health_signals(deal: dict) -> List[Dict[str, Any]]:
    result = score_deal_from_zoho(deal)
    return [
        {"name": s.name, "score": s.score, "max_score": s.max_score, "label": s.label, "detail": s.detail}
        for s in result.signals
    ]


def _rep_name_from(request_rep: str, session: dict, deal: dict) -> str:
    if request_rep != "the sales rep":
        return request_rep
    return session.get("display_name") or deal.get("owner") or "the sales rep"


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
        return "No email history available."


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/nba")
async def get_next_best_action(request: NBARequest, authorization: str = Header(...)):
    from routers.deals import build_deal_context
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    signals = _get_health_signals(deal)
    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}

    # Use the enriched email context — Outlook primary, Zoho supplementary, with
    # recent/historical split and proper date normalization. This is the ONLY email
    # path for NBA — do not use _emails_raw which bypasses all of that logic.
    email_context = await _fetch_email_context(request.deal_id, session, limit=8)

    contacts_block = ""
    if not _is_demo(session):
        try:
            from services.contact_intelligence import get_deal_contacts, format_contacts_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            contacts_data = await get_deal_contacts(
                deal_id=request.deal_id,
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
            import logging
            logging.getLogger(__name__).warning("ai_rep: contacts fetch failed deal=%s: %s", request.deal_id, e)

    action_plan = await generate_next_best_action(
        deal=deal_with_health,
        health_signals=signals,
        rep_name=rep_name,
        email_context=email_context,
        deal_context=build_deal_context(deal_with_health),
        contacts_block=contacts_block,
    )

    return {
        "deal_id": request.deal_id,
        "deal_name": deal.get("name"),
        "rep_name": rep_name,
        "action_plan": action_plan,
        "health_score": health_result.total_score,
        "health_label": health_result.health_label,
        "email_thread_used": bool(email_context),
        "email_count": email_context.count("[→ REP]") + email_context.count("[← BUYER]"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_approval",
    }


@router.post("/approve-action")
async def approve_action_plan(request: ActionApprovalRequest, authorization: str = Header(...)):
    _decode_session(authorization)
    if request.approved:
        return {"deal_id": request.deal_id, "approved": True, "message": "Action plan approved. Proceeding to email draft.", "next_step": "generate_email", "rep_feedback": request.rep_feedback, "timestamp": datetime.now(timezone.utc).isoformat()}
    return {"deal_id": request.deal_id, "approved": False, "message": "Action plan rejected. No action taken.", "rep_feedback": request.rep_feedback, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/draft-email")
async def draft_email(request: EmailDraftRequest, authorization: str = Header(...)):
    from routers.deals import build_deal_context
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}

    email_context = await _fetch_email_context(request.deal_id, session, limit=5)

    contacts_block = ""
    if not _is_demo(session):
        try:
            from services.contact_intelligence import get_deal_contacts, format_contacts_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            contacts_data = await get_deal_contacts(
                deal_id=request.deal_id,
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
            import logging
            logging.getLogger(__name__).warning("ai_rep: contacts fetch failed deal=%s: %s", request.deal_id, e)

    email = await generate_email_draft(
        deal=deal_with_health,
        rep_name=rep_name,
        email_objective=request.email_objective or "Re-engage buyer and establish next step",
        action_context=request.action_context or "",
        email_context=email_context,
        deal_context=build_deal_context(deal_with_health),
        contacts_block=contacts_block,
    )

    return {
        "deal_id": request.deal_id,
        "deal_name": deal.get("name"),
        "rep_name": rep_name,
        "email": email,
        "status": "pending_approval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/approve-email")
async def approve_email(request: EmailApprovalRequest, authorization: str = Header(...)):
    _decode_session(authorization)
    if not request.approved:
        return {"deal_id": request.deal_id, "approved": False, "message": "Email rejected. No email sent."}
    final_body = request.edits if request.edits else request.body
    return {
        "deal_id": request.deal_id,
        "approved": True,
        "message": "Email approved and ready to send.",
        "final_email": {"subject": request.subject, "body": final_body, "rep": request.rep_name},
        "send_instructions": "Copy the subject and body above and send from your email client.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/handle-objection")
async def handle_objection_endpoint(request: ObjectionRequest, authorization: str = Header(...)):
    from routers.deals import build_deal_context
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    email_context = await _fetch_email_context(request.deal_id, session, limit=5)

    response = await handle_objection(
        deal=deal,
        objection=request.objection,
        rep_name=rep_name,
        email_context=email_context,
        deal_context=build_deal_context(deal),
    )

    return {
        "deal_id": request.deal_id,
        "deal_name": deal.get("name"),
        "objection": request.objection,
        "rep_name": rep_name,
        "response": response,
        "status": "pending_approval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/call-brief")
async def get_call_brief(request: CallBriefRequest, authorization: str = Header(...)):
    """
    Generate a pre-call intelligence brief for the rep.
    Includes: call objective, stakeholder intel, talking points, risk questions.
    """
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    from routers.deals import build_deal_context
    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}
    signals = _get_health_signals(deal)

    email_context = await _fetch_email_context(request.deal_id, session, limit=8)
    activity_context = _build_activity_context(deal_with_health)

    contacts_block = ""
    if not _is_demo(session):
        try:
            from services.contact_intelligence import get_deal_contacts, format_contacts_for_ai
            user_key = session.get("email") or session.get("user_id") or "default"
            contacts_data = await get_deal_contacts(
                deal_id=request.deal_id,
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
            import logging
            logging.getLogger(__name__).warning("ai_rep: contacts fetch failed deal=%s: %s", request.deal_id, e)

    brief = await generate_call_brief(
        deal=deal_with_health,
        health_signals=signals,
        rep_name=rep_name,
        email_context=email_context,
        activity_context=activity_context,
        deal_context=build_deal_context(deal_with_health),
        contacts_block=contacts_block,
    )

    return {
        "deal_id": request.deal_id,
        "deal_name": deal.get("name"),
        "rep_name": rep_name,
        "brief": brief,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/demo-nba")
async def demo_nba():
    demo_deal = {
        "id": "sim_004", "name": "FinanceFlow — Platform License", "account_name": "FinanceFlow Corp",
        "stage": "Negotiation/Review", "amount": 120000, "closing_date": "2026-03-15",
        "probability": 50, "next_step": None, "last_activity_days": 34,
        "days_since_buyer_response": 34, "health_score": 18, "health_label": "zombie",
        "contact_count": 1, "economic_buyer_engaged": False, "discount_mention_count": 5, "activity_count_30d": 0,
    }
    signals = _get_health_signals(demo_deal)
    action_plan = await generate_next_best_action(deal=demo_deal, health_signals=signals, rep_name="Sarah Chen")
    return {"deal_id": "sim_004", "deal_name": "FinanceFlow — Platform License", "rep_name": "Sarah Chen", "action_plan": action_plan, "health_score": 18, "health_label": "zombie", "status": "pending_approval"}


@router.get("/demo-call-brief")
async def demo_call_brief():
    """Demo call brief for Acme Corp — no auth required."""
    demo_deal = next((d for d in SIMULATED_DEALS if d["id"] == "sim_001"), SIMULATED_DEALS[0])
    health_result = score_deal_from_zoho(demo_deal)
    deal_with_health = {**demo_deal, "health_score": health_result.total_score, "health_label": health_result.health_label}
    signals = _get_health_signals(demo_deal)
    brief = await generate_call_brief(deal=deal_with_health, health_signals=signals, rep_name="Sarah Chen")
    return {"deal_id": "sim_001", "deal_name": demo_deal.get("name"), "rep_name": "Sarah Chen", "brief": brief}
