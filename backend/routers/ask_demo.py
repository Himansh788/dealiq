"""
Ask DealIQ — Demo Endpoints
============================
All /ask/demo/* routes. No auth, no database, no Zoho required.
Uses hardcoded demo scenario from ask_demo_data.py.
Still calls the real AI if GROQ_API_KEY is set; falls back to hardcoded responses if not.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from services.ask_demo_data import (
    DEMO_TRANSCRIPT,
    DEMO_EMAILS,
    DEMO_DEAL,
    FALLBACK_QA_RESPONSE,
    FALLBACK_MEDDIC_RESPONSE,
    FALLBACK_BRIEF_RESPONSE,
)
from services.ask_dealiq_prompts import PRESET_QUESTIONS
from services.ask_dealiq_service import (
    ask_about_deal,
    ask_meddic_analysis,
    generate_deal_brief,
)
from services.email_generator import EmailGenerator
import services.ai_router_ask as ai_router

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/ask/demo", tags=["Ask DealIQ — Demo"])


class DemoDealQuestionRequest(BaseModel):
    deal_id: str = "demo_1"
    question: str


class DemoMeddicRequest(BaseModel):
    deal_id: str = "demo_1"


class DemoBriefRequest(BaseModel):
    deal_id: str = "demo_1"


class DemoFollowUpRequest(BaseModel):
    deal_id: str = "demo_1"


@router.get("/presets")
def get_demo_presets():
    """Return preset questions for the UI quick-action buttons."""
    return PRESET_QUESTIONS


@router.post("/deal")
async def demo_ask_deal(request: DemoDealQuestionRequest):
    """
    Ask any question about the demo deal.
    Uses DEMO_TRANSCRIPT + DEMO_EMAILS + DEMO_DEAL as context.
    Calls real AI if GROQ_API_KEY is set; returns hardcoded response if not.
    """
    if not ai_router.is_configured():
        _log.info("GROQ_API_KEY not set — returning hardcoded demo response")
        return {
            **FALLBACK_QA_RESPONSE,
            "deal_id": request.deal_id,
            "question": request.question,
            "demo_mode": True,
            "ai_used": False,
        }

    try:
        result = await ask_about_deal(
            deal=DEMO_DEAL,
            emails=DEMO_EMAILS,
            transcript=DEMO_TRANSCRIPT,
            question=request.question,
        )
        return {**result, "deal_id": request.deal_id, "demo_mode": True}
    except Exception as exc:
        _log.error("Demo Q&A failed: %s", exc)
        return {
            **FALLBACK_QA_RESPONSE,
            "deal_id": request.deal_id,
            "question": request.question,
            "demo_mode": True,
            "ai_used": False,
            "error_note": str(exc),
        }


@router.post("/meddic")
async def demo_meddic(request: DemoMeddicRequest):
    """
    MEDDIC analysis of the demo call transcript.
    Calls real AI if GROQ_API_KEY is set; returns hardcoded MEDDIC if not.
    """
    if not ai_router.is_configured():
        return {
            **FALLBACK_MEDDIC_RESPONSE,
            "deal_id": request.deal_id,
            "demo_mode": True,
            "ai_used": False,
        }

    try:
        result = await ask_meddic_analysis(
            deal=DEMO_DEAL,
            emails=DEMO_EMAILS,
            transcript=DEMO_TRANSCRIPT,
        )
        return {**result, "deal_id": request.deal_id, "demo_mode": True}
    except Exception as exc:
        _log.error("Demo MEDDIC failed: %s", exc)
        return {
            **FALLBACK_MEDDIC_RESPONSE,
            "deal_id": request.deal_id,
            "demo_mode": True,
            "ai_used": False,
        }


@router.post("/brief")
async def demo_brief(request: DemoBriefRequest):
    """
    Full deal brief for the demo deal.
    Calls real AI if GROQ_API_KEY is set; returns hardcoded brief if not.
    """
    if not ai_router.is_configured():
        return {
            **FALLBACK_BRIEF_RESPONSE,
            "deal_id": request.deal_id,
            "demo_mode": True,
            "ai_used": False,
        }

    try:
        result = await generate_deal_brief(
            deal=DEMO_DEAL,
            emails=DEMO_EMAILS,
            transcript=DEMO_TRANSCRIPT,
        )
        return {**result, "deal_id": request.deal_id, "demo_mode": True}
    except Exception as exc:
        _log.error("Demo brief failed: %s", exc)
        return {
            **FALLBACK_BRIEF_RESPONSE,
            "deal_id": request.deal_id,
            "demo_mode": True,
            "ai_used": False,
        }


@router.post("/follow-up-email")
async def demo_follow_up_email(request: DemoFollowUpRequest):
    """Generate a follow-up email from the demo call transcript."""
    if not ai_router.is_configured():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set GROQ_API_KEY to enable follow-up email generation.",
        )

    try:
        result = await EmailGenerator().generate(
            deal=DEMO_DEAL,
            emails=DEMO_EMAILS,
            transcript=DEMO_TRANSCRIPT,
        )
        return {**result, "deal_id": request.deal_id, "demo_mode": True}
    except Exception as exc:
        _log.error("Demo follow-up email failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
