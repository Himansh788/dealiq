from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from services.signal_detector import detect_signals

router = APIRouter()


class SignalDetectRequest(BaseModel):
    transcript: str
    researcher_name: Optional[str] = "the researcher"
    company_context: Optional[str] = "Unknown"


# ── Demo transcript — a rich research call with 6+ signal types ───────────────

DEMO_TRANSCRIPT = """
[Product Research Interview — Rahul Mehta, Head of Operations, GlobalRetail Ltd]
[Interviewed by: Priya (DealIQ Research Team) | Date: Feb 20, 2026]

Priya: Thanks for your time today, Rahul. We're just doing a routine check-in on
how your team is managing pipeline visibility.

Rahul: Sure, happy to chat. Honestly, things have gotten pretty painful lately.
We switched to our current tool — Pipedrive — about 18 months ago and the
reporting is just terrible. My CEO asks me every Monday for a forecast update
and I'm basically doing it manually in Excel. It's embarrassing.

Priya: That sounds frustrating. What would a better solution look like for you?

Rahul: We need something that can actually do AI-based forecasting. Our CFO just
approved a $50K budget for pipeline tools this quarter — she wants to see ROI
within 6 months or the budget gets cut. The thing is, our board meeting is
March 15th and I need to walk in with a credible forecast. That's basically my
deadline to have something working.

Priya: Are you looking at other options right now?

Rahul: We looked at Clari but it's way too expensive for a company our size.
I've heard good things about your product from Neha at HealthTech — she said
it changed how her team does deals. That kind of recommendation carries a lot
of weight with me. I also need to get our VP of Sales, Vikram, involved —
he'll be the one approving the final purchase.

Priya: Any concerns that might slow things down?

Rahul: The main risk is IT sign-off — we had a nightmare with our last
integration and our CTO is very cautious about new vendors now. But honestly
if the demo goes well I think we can move fast. Our current contract with
Pipedrive renews in April and I'd rather not renew if there's a better option.

Priya: What would make you feel confident moving forward?

Rahul: A strong ROI case and a clean integration story. If someone from your
side could walk Vikram through the numbers before March 10th, I think we
could make a decision before the board meeting.
"""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/detect")
async def detect_buying_signals(request: SignalDetectRequest):
    """
    Analyse a non-sales call transcript for buying signals.
    No auth required — transcript is ephemeral and not stored.
    """
    result = await detect_signals(
        transcript=request.transcript,
        researcher_name=request.researcher_name or "the researcher",
        company_context=request.company_context or "Unknown",
    )
    return {
        **result,
        "researcher": request.researcher_name,
        "company_context": request.company_context,
        "analysed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/demo")
async def demo_signal_detection():
    """Demo buying signal detection — no auth required."""
    result = await detect_signals(
        transcript=DEMO_TRANSCRIPT,
        researcher_name="Priya (Research Team)",
        company_context="GlobalRetail Ltd — Head of Operations",
    )
    return {
        **result,
        "researcher": "Priya (Research Team)",
        "company_context": "GlobalRetail Ltd — Head of Operations",
        "analysed_at": datetime.now(timezone.utc).isoformat(),
        "is_demo": True,
    }
