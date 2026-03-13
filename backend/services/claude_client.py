"""
AI Client — Narrative Mismatch, Discount Analysis, Deal Insights
================================================================
Uses Anthropic (claude-sonnet-4-6) for fast, high-quality B2B sales intelligence.
"""

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
import json
import os
import re
from typing import Dict, Any

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


MODEL = "claude-sonnet-4-6"

MISMATCH_SYSTEM = """You are a senior deal intelligence analyst specialising in B2B SaaS sales integrity.
Your role is to forensically compare what was said on a sales call versus what was written in the follow-up email.

You are looking for ANY gap between verbal commitments and written follow-up across these dimensions:
1. PRICING — exact figures, tiers, discounts, payment terms
2. TIMELINE — go-live dates, implementation schedules, contract deadlines
3. NEXT STEPS — specific actions with owners and dates
4. PRODUCT/FEATURE — capabilities promised, integrations mentioned, scope agreed
5. SUPPORT/ONBOARDING — dedicated support, SLAs, training promised
6. LEGAL/COMPLIANCE — SOC2, security docs, contract terms discussed

SEVERITY GUIDE:
- high: Directly threatens deal trust or creates legal exposure (wrong price, wrong date, missing commitment)
- medium: Could cause friction or confusion if buyer notices (minor timeline shift, vague next step)
- low: Cosmetic difference, easy to correct, minimal buyer impact

Return ONLY valid JSON — no markdown, no explanation outside JSON:
{"mismatches": [{"category": "pricing|timeline|next_step|feature_promise|commitment|support","description": "Specific gap written as: 'You said X on the call but wrote Y in the email'","severity": "high|medium|low","suggested_fix": "Exact corrected language to use"}],"deal_health_impact": -15,"summary": "One direct sentence on overall integrity of this follow-up"}

If the email accurately mirrors all call commitments, return:
{"mismatches": [], "deal_health_impact": 0, "summary": "Email accurately reflects all call commitments — safe to send."}"""

DISCOUNT_SYSTEM = """You are a pricing intelligence analyst for a B2B SaaS company.
Analyse this email thread for every discount mention, negotiation signal, and pricing pressure indicator.

For each discount mention extract:
- Exact context (word-for-word excerpt, max 15 words)
- Who raised it: rep (bad — rep volunteered discount), buyer (normal — buyer asked), unknown
- The specific value if mentioned (e.g., "15%", "$5K off", "waived setup fee")

Classify overall pressure:
- normal: Buyer asked once, rep held firm or gave minor concession with justification
- elevated: Multiple mentions, rep showing willingness to negotiate, discount creep visible
- critical: Rep leading with discounts, giving without getting, deal economics at risk

Return ONLY valid JSON:
{"mentions": [{"mention_index": 1,"context": "exact 10-15 word excerpt","raised_by": "rep|buyer|unknown","discount_value": "15% or null"}],"pressure_level": "normal|elevated|critical","benchmark_comparison": "How this compares to healthy deal pricing behaviour (1 sentence)","recommendation": "One specific action the rep should take on pricing right now"}"""


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found: {text[:200]}")


async def detect_narrative_mismatch(transcript: str, email_draft: str) -> Dict[str, Any]:
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1200,
            temperature=0.1,
            messages=[
                {"role": "system", "content": MISMATCH_SYSTEM},
                {"role": "user", "content": f"CALL TRANSCRIPT:\n{transcript}\n\nFOLLOW-UP EMAIL DRAFT:\n{email_draft}"},
            ],
        )
        return _extract_json(response.choices[0].message.content)
    except Exception as e:
        return {"mismatches": [], "deal_health_impact": 0, "summary": f"Analysis unavailable: {str(e)}"}


async def get_deal_ai_insights(deal_signals: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signals_text = "\n".join([f"- {k}: {v}" for k, v in deal_signals.items()])
        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=600,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a B2B SaaS deal intelligence analyst. Return ONLY valid JSON."},
                {"role": "user", "content": f"Deal signals:\n{signals_text}\n\nReturn ONLY JSON: {{\"recommendation\": \"specific one-sentence action\", \"action_required\": true, \"risk_summary\": \"2-3 sentence risk assessment with specific signals\"}}"},
            ],
        )
        return _extract_json(response.choices[0].message.content)
    except Exception as e:
        return {"recommendation": "Review manually.", "action_required": True, "risk_summary": "AI unavailable."}


async def analyse_discount_thread(email_thread: str) -> Dict[str, Any]:
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1200,
            temperature=0.1,
            messages=[
                {"role": "system", "content": DISCOUNT_SYSTEM},
                {"role": "user", "content": f"EMAIL THREAD TO ANALYSE:\n{email_thread}"},
            ],
        )
        return _extract_json(response.choices[0].message.content)
    except Exception as e:
        return {"mentions": [], "pressure_level": "normal", "benchmark_comparison": "Unavailable.", "recommendation": "Review manually."}
