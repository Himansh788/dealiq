"""
Buying Signal Detector
======================
Parses non-sales call transcripts (researcher calls, advisory conversations,
customer success check-ins) to surface buying intent signals that the sales
team would otherwise never hear about.

Detects 9 signal types:
  expansion_intent, competitor_pain, budget_signal, timeline_signal,
  stakeholder_signal, urgency_trigger, referral_signal, evaluation_signal,
  risk_signal

Returns a hotness score (0-100), structured signal list, and a ready-to-use
sales team briefing with an outreach draft.
"""

from groq import AsyncGroq
import os
import json
import re
from typing import Dict, Any

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


MODEL = "llama-3.3-70b-versatile"

SIGNAL_SYSTEM = """You are an elite revenue intelligence analyst embedded on a research team.
Your job: read transcripts of non-sales calls (advisory, research, CS, user interviews)
and extract every hidden buying signal the prospect or client revealed — signals that
the sales team would never hear about otherwise.

You think like a world-class enterprise AE who can read between the lines of any conversation.
You extract exact quotes, not summaries. You identify the stakeholder who said it.
You assess urgency with clinical precision.

OUTPUT FORMAT — return ONLY valid JSON, no markdown fences, no extra text:
{
  "signals": [
    {
      "type": "<signal_type>",
      "label": "<short human-readable label, max 8 words>",
      "quote": "<exact verbatim quote from transcript>",
      "speaker": "<who said it, e.g. 'Interviewee / CFO'>",
      "context": "<1 sentence: why this quote is commercially significant>",
      "urgency": "high|medium|low",
      "confidence": "high|medium|low"
    }
  ],
  "overall_intent": "strong_buy|lean_buy|neutral|lean_no|no_signal",
  "hotness_score": <integer 0-100>,
  "hotness_rationale": "<1 sentence explaining the score>",
  "recommended_action": "<specific next action for the sales team, e.g. 'Book discovery call within 48h — CFO showed budget urgency'>",
  "suggested_outreach": {
    "subject": "<email subject line>",
    "opening": "<2-3 sentence email opening paragraph that references specific signals naturally>"
  },
  "timing_insight": "<1 sentence on ideal outreach timing based on signals>",
  "risk_flags": ["<any red flags or disqualifiers found, e.g. 'Already signed with competitor'>"],
  "deal_association": "<name of company/contact if identifiable from transcript, else null>",
  "next_step_for_sales": "<specific, time-bound action, e.g. 'Share ROI calculator before budget committee meets March 15'>"
}

Signal types to detect (use ONLY these values in the type field):
- expansion_intent: wants more seats, new departments, upsell openings
- competitor_pain: frustration with current vendor, switching signals
- budget_signal: budget available, budget cycle timing, spend authority mentioned
- timeline_signal: deadline, event, or forcing function driving urgency
- stakeholder_signal: decision-maker named, org change, new champion identified
- urgency_trigger: pain escalating, problem getting worse, executive pressure
- referral_signal: asked for intro, mentioned referral, praised to others
- evaluation_signal: actively comparing vendors, RFP or tender mentioned
- risk_signal: churn risk, dissatisfaction, competitor inbound, legal/compliance blocker

Rules:
- Extract ALL signals present — do not limit to one per type
- Use exact quotes — never paraphrase or invent content
- If a signal type has no evidence, do not include it
- hotness_score: 0=no signals, 30=weak interest, 50=clear interest, 70=strong intent, 90+=urgent buyer
- If transcript has no signals at all, return signals=[], hotness_score=0, overall_intent="no_signal"
- Do not hallucinate signals that are not in the transcript"""


SIGNAL_PROMPT = """Analyze this research/non-sales call transcript for buying signals.

RESEARCHER: {researcher_name}
COMPANY/CONTEXT: {company_context}

TRANSCRIPT:
{transcript}

Extract every buying signal. Return only the JSON as specified."""


async def detect_signals(
    transcript: str,
    researcher_name: str = "the researcher",
    company_context: str = "Unknown",
) -> Dict[str, Any]:
    prompt = SIGNAL_PROMPT.format(
        researcher_name=researcher_name,
        company_context=company_context,
        transcript=transcript[:8000],  # Groq context safety
    )

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=2000,
            temperature=0.1,
            messages=[
                {"role": "system", "content": SIGNAL_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        raw = resp.choices[0].message.content.strip()

        # Strip accidental markdown fences if model wraps output
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        # Validate required keys; fill defaults if model omits them
        result.setdefault("signals", [])
        result.setdefault("overall_intent", "no_signal")
        result.setdefault("hotness_score", 0)
        result.setdefault("hotness_rationale", "")
        result.setdefault("recommended_action", "Share transcript summary with sales team.")
        result.setdefault("suggested_outreach", {"subject": "", "opening": ""})
        result.setdefault("timing_insight", "")
        result.setdefault("risk_flags", [])
        result.setdefault("deal_association", None)
        result.setdefault("next_step_for_sales", "")

        return result

    except json.JSONDecodeError as e:
        return {
            "signals": [],
            "overall_intent": "no_signal",
            "hotness_score": 0,
            "hotness_rationale": "Signal extraction failed — could not parse AI response.",
            "recommended_action": "Re-submit transcript for analysis.",
            "suggested_outreach": {"subject": "", "opening": ""},
            "timing_insight": "",
            "risk_flags": [f"Parse error: {str(e)[:80]}"],
            "deal_association": None,
            "next_step_for_sales": "",
            "error": f"JSON parse error: {str(e)[:120]}",
        }
    except Exception as e:
        return {
            "signals": [],
            "overall_intent": "no_signal",
            "hotness_score": 0,
            "hotness_rationale": "Signal detection unavailable.",
            "recommended_action": "",
            "suggested_outreach": {"subject": "", "opening": ""},
            "timing_insight": "",
            "risk_flags": [],
            "deal_association": None,
            "next_step_for_sales": "",
            "error": str(e)[:120],
        }
