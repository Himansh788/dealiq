from fastapi import APIRouter, Header, HTTPException
from typing import Optional
import base64
import json
from services.claude_client import detect_narrative_mismatch, analyse_discount_thread, get_deal_ai_insights
from services.health_scorer import score_deal_from_zoho
from services.demo_data import SIMULATED_DEALS, DEMO_TRANSCRIPT, DEMO_EMAIL
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
    
    # Try base64 JSON decode (our session format)
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        pass
    
    # Raw Zoho token fallback
    if len(token) > 10:
        return {
            "user_id": "zoho_user",
            "display_name": "Zoho User",
            "email": "",
            "access_token": token,
            "refresh_token": "",
        }
    
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


# ── Narrative Mismatch ────────────────────────────────────────────────────────

@router.post("/mismatch", response_model=MismatchResult)
async def check_mismatch(
    request: MismatchRequest,
    authorization: str = Header(...),
):
    """
    Compare a call transcript against an email draft.
    Returns plain-language mismatch flags and health score impact.
    """
    _decode_session(authorization)  # Validate session

    if not request.transcript.strip() or not request.email_draft.strip():
        raise HTTPException(status_code=400, detail="Both transcript and email_draft are required")

    raw = await detect_narrative_mismatch(request.transcript, request.email_draft)

    flags = []
    for m in raw.get("mismatches", []):
        flags.append(MismatchFlag(
            category=m.get("category", "commitment"),
            description=m.get("description", ""),
            severity=m.get("severity", "medium"),
            suggested_fix=m.get("suggested_fix", "Review and add missing commitment to email."),
        ))

    return MismatchResult(
        mismatches=flags,
        deal_health_impact=raw.get("deal_health_impact", 0),
        clean=len(flags) == 0,
        summary=raw.get("summary", "Analysis complete."),
    )


@router.get("/mismatch/demo", response_model=MismatchResult)
async def demo_mismatch():
    """
    Run the mismatch demo with pre-loaded Acme Corp data.
    No auth required — for judges and testers.
    """
    raw = await detect_narrative_mismatch(DEMO_TRANSCRIPT, DEMO_EMAIL)
    flags = []
    for m in raw.get("mismatches", []):
        flags.append(MismatchFlag(
            category=m.get("category", "commitment"),
            description=m.get("description", ""),
            severity=m.get("severity", "medium"),
            suggested_fix=m.get("suggested_fix", ""),
        ))

    return MismatchResult(
        mismatches=flags,
        deal_health_impact=raw.get("deal_health_impact", 0),
        clean=len(flags) == 0,
        summary=raw.get("summary", ""),
    )


# ── Discount Heat Map ─────────────────────────────────────────────────────────

@router.post("/discount")
async def analyse_discount(
    email_thread: str,
    deal_id: Optional[str] = None,
    authorization: str = Header(...),
):
    """Analyse an email thread for discount pressure patterns."""
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
    """
    Get an Advance / Close / Kill recommendation for a stalled deal.
    """
    session = _decode_session(authorization)
    simulated = _is_demo(session)

    if simulated:
        raw_list = [d for d in SIMULATED_DEALS if d["id"] == deal_id]
        if not raw_list:
            raise HTTPException(status_code=404, detail="Deal not found")
        raw = raw_list[0]
    else:
        from services.zoho_client import fetch_deals, map_zoho_deal
        from routers.deals import _fetch_all_zoho_deals, _enrich_deal
        try:
            all_deals = await _fetch_all_zoho_deals(session["access_token"])
            raw_list = [d for d in all_deals if d["id"] == deal_id]
            if not raw_list:
                raise HTTPException(status_code=404, detail="Deal not found")
            raw = _enrich_deal(raw_list[0])
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    health = score_deal_from_zoho(raw)

    # Calculate days stalled
    last_activity = raw.get("last_activity_time")
    days_stalled = 0
    if last_activity:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
            days_stalled = (datetime.now(timezone.utc) - dt).days
        except Exception:
            days_stalled = 0

    # Determine recommendation
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
        supporting_signals=signals[:4],  # Top 4 signals
    )


@router.post("/ack/{deal_id}/decide")
async def log_ack_decision(
    deal_id: str,
    decision: ACKDecision,
    authorization: str = Header(...),
):
    """Log a rep's ACK decision. In production this would update CRM."""
    _decode_session(authorization)

    # In production: update Zoho deal stage / notes via API
    # For demo: just return confirmation
    return {
        "deal_id": deal_id,
        "decision": decision.decision,
        "logged": True,
        "message": f"Decision '{decision.decision}' logged for deal {deal_id}.",
        "next_step": decision.next_step,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
