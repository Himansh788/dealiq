"""
Deal Autopsy Engine
====================
When a deal is killed or lost, the AI generates a full post-mortem:

1. What signals were missed early on
2. The behavioral pattern that led to the loss
3. The moment the deal was most at risk (and what could have been done)
4. What one thing could have saved it
5. Pattern learnings for similar live deals

This turns losses into institutional memory.
The autopsy is stored and surfaced on similar deals in the pipeline.
"""

from groq import AsyncGroq
import os
import json
import re
from typing import Dict, Any, List, Optional

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


MODEL = "llama-3.3-70b-versatile"


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found: {text[:200]}")


def _fmt(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${round(val/1_000)}K"
    return f"${round(val)}"


AUTOPSY_SYSTEM = """You are a revenue intelligence analyst and former VP of Sales conducting a post-mortem on a lost or killed B2B SaaS deal.

Your mandate:
- Be brutally honest about what went wrong — not diplomatic
- Identify the ROOT CAUSE, not surface symptoms
- Extract BEHAVIOURAL patterns the rep can change (not external factors they cannot)
- Find the EARLIEST possible intervention point
- Make every learning SPECIFIC and ACTIONABLE for the next deal

Your insights should make the rep think: "That's exactly right — I can see that now."
Avoid vague generalities. Use the deal data to be precise.

Return ONLY valid JSON."""


async def generate_deal_autopsy(
    deal: Dict[str, Any],
    health_signals: List[Dict[str, Any]],
    kill_reason: Optional[str] = None,
    timeline_events: Optional[List[Dict[str, Any]]] = None,
    email_context: str = "",
    activity_context: str = "",
    deal_context: str = "",
) -> Dict[str, Any]:
    """
    Generate a full autopsy for a dead or killed deal.
    Returns structured learnings that can be applied to similar live deals.
    """
    signals_text = "\n".join([
        f"- {s.get('name', '')}: {s.get('detail', '')} [Score: {s.get('score', 0)}/{s.get('max_score', 20)} — {s.get('label', 'unknown')}]"
        for s in health_signals
    ]) or "No signals available"

    timeline_text = ""
    if timeline_events:
        timeline_text = "\nTIMELINE:\n" + "\n".join([
            f"  [{e.get('days_ago', '?')} days ago] {e.get('label', '')}: {e.get('detail', '')}"
            for e in timeline_events[-10:]
        ])

    kill_reason_text = f"\nREP'S STATED KILL REASON: {kill_reason}" if kill_reason else ""

    prompt = f"""Conduct a full deal autopsy on this killed/lost deal. Be specific, honest, and constructive.

═══ DEAL DATA ═══
Deal: {deal.get('name', 'Unknown')}
Company: {deal.get('account_name', 'Unknown')}
Value: {_fmt(deal.get('amount', 0))}
Stage at death: {deal.get('stage', 'Unknown')}
Final health score: {deal.get('health_score', 0)}/100 ({deal.get('health_label', 'unknown')})
Days in pipeline: {deal.get('days_in_stage', 'Unknown')}
Contact count: {deal.get('contact_count', 1)} (economic buyer engaged: {deal.get('economic_buyer_engaged', False)})
Discount mentions: {deal.get('discount_mention_count', 0)}{kill_reason_text}

═══ HEALTH SIGNALS AT TIME OF DEATH ═══
{signals_text}{timeline_text}

═══ RECENT EMAIL CONTEXT (last 5 emails) ═══
{email_context or "No email history available — analysis based on CRM data only."}

═══ DEAL CONTEXT ═══
{deal_context or "No additional deal context available."}

═══ CLOSED ACTIVITIES & STAKEHOLDERS (from CRM) ═══
{activity_context or "No activity/contact data available."}

Think step by step:
1. What is the single clearest root cause?
2. When was the FIRST signal that should have triggered action?
3. What is the precise moment where a different decision would have changed the outcome?
4. What behavioural pattern in the rep's approach contributed to this?
5. What learnings transfer directly to other deals in the pipeline?

Return ONLY this JSON:
{{
  "cause_of_death": "One precise sentence — the primary root cause (name the specific failure, not a generic description)",
  "earliest_warning_sign": {{
    "signal": "The first concrete signal that should have triggered immediate action",
    "when": "How far before deal death this signal appeared (e.g., '3 weeks before kill')",
    "what_was_missed": "The specific action the rep should have taken when this signal appeared"
  }},
  "critical_moment": {{
    "description": "The single inflection point where the deal could most easily have been saved",
    "what_happened": "Exactly what the rep did (or failed to do) at this moment",
    "what_should_have_happened": "The specific alternative action with expected outcome"
  }},
  "behavioral_pattern": "The rep behaviour pattern that contributed most to this loss — be honest, specific, and constructive (2 sentences)",
  "what_would_have_saved_it": "The ONE specific action, taken at the right moment, with highest probability of saving this deal",
  "learnings": [
    "Actionable learning #1 — specific enough to apply to the next similar deal tomorrow",
    "Actionable learning #2 — tied to a specific signal or behaviour from this deal",
    "Actionable learning #3 — about process, not just this deal"
  ],
  "similar_live_deals_risk": "Which deals in the current pipeline likely have the same failure pattern, and what to watch for",
  "rep_coaching_note": "One sentence of growth-oriented coaching — not blame, but a specific skill or habit to build"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1400,
            temperature=0.2,
            messages=[
                {"role": "system", "content": AUTOPSY_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        result["deal_name"] = deal.get("name", "Unknown")
        result["deal_value"] = deal.get("amount", 0)
        result["stage_at_death"] = deal.get("stage", "Unknown")
        return result
    except Exception as e:
        return {
            "generated": False,
            "cause_of_death": f"Could not generate autopsy: {str(e)[:100]}",
            "earliest_warning_sign": {"signal": "", "when": "", "what_was_missed": ""},
            "critical_moment": {"description": "", "what_happened": "", "what_should_have_happened": ""},
            "behavioral_pattern": "",
            "what_would_have_saved_it": "",
            "learnings": [],
            "similar_live_deals_risk": "",
            "rep_coaching_note": "",
        }
