from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import base64
import json
from services.ai_rep import generate_next_best_action, generate_email_draft, handle_objection, generate_call_brief
from services.health_scorer import score_deal_from_zoho
from services.demo_data import SIMULATED_DEALS, SIMULATED_EMAILS
from datetime import datetime, timezone

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
        from routers.deals import _fetch_all_zoho_deals, _enrich_deal
        try:
            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            matches = [d for d in all_deals if d["id"] == deal_id]
            if not matches:
                raise HTTPException(status_code=404, detail="Deal not found")
            return _enrich_deal(matches[0])
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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/nba")
async def get_next_best_action(request: NBARequest, authorization: str = Header(...)):
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    signals = _get_health_signals(deal)
    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}

    # Fetch email thread for richer AI context
    email_thread: List[Dict] = []
    if _is_demo(session):
        email_thread = SIMULATED_EMAILS.get(request.deal_id, [])
    else:
        try:
            from services.zoho_client import fetch_deal_emails
            email_thread = await fetch_deal_emails(session["access_token"], request.deal_id)
        except Exception:
            email_thread = []

    action_plan = await generate_next_best_action(
        deal=deal_with_health,
        health_signals=signals,
        rep_name=rep_name,
        email_thread=email_thread,
    )

    return {
        "deal_id": request.deal_id,
        "deal_name": deal.get("name"),
        "rep_name": rep_name,
        "action_plan": action_plan,
        "health_score": health_result.total_score,
        "health_label": health_result.health_label,
        "email_thread_used": len(email_thread) > 0,
        "email_count": len(email_thread),
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
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}

    email = await generate_email_draft(
        deal=deal_with_health,
        rep_name=rep_name,
        email_objective=request.email_objective or "Re-engage buyer and establish next step",
        action_context=request.action_context or "",
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
    session = _decode_session(authorization)
    deal = await _get_deal(request.deal_id, session)
    rep_name = _rep_name_from(request.rep_name, session, deal)

    response = await handle_objection(deal=deal, objection=request.objection, rep_name=rep_name)

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

    health_result = score_deal_from_zoho(deal)
    deal_with_health = {**deal, "health_score": health_result.total_score, "health_label": health_result.health_label}
    signals = _get_health_signals(deal)

    brief = await generate_call_brief(deal=deal_with_health, health_signals=signals, rep_name=rep_name)

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
