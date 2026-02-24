import anthropic
import json
import os
import re
from typing import Dict, Any

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

MISMATCH_PROMPT = """You are a deal intelligence assistant for B2B SaaS sales teams.
Compare the transcript and email. Identify anything MISSING or INCONSISTENT:
1. Pricing commitments or discounts
2. Timeline or delivery promises
3. Agreed next steps with dates
4. Feature or product promises
5. Any explicit commitment made to the buyer

Return ONLY valid JSON, no markdown:
{"mismatches": [{"category": "pricing|timeline|next_step|feature_promise|commitment","description": "Under 30 words directed at rep as You...","severity": "high|medium|low","suggested_fix": "Under 20 words"}],"deal_health_impact": -15,"summary": "One sentence"}

If clean: {"mismatches": [], "deal_health_impact": 0, "summary": "Your email accurately reflects all commitments. Good to send."}
"""

DISCOUNT_PROMPT = """Analyse email thread for discount patterns. Return ONLY valid JSON:
{"mentions": [{"mention_index": 1,"context": "10-word excerpt","raised_by": "rep|buyer|unknown","discount_value": "10% or null"}],"pressure_level": "normal|elevated|critical","benchmark_comparison": "One sentence","recommendation": "One sentence"}
"""


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found: {text[:200]}")


async def detect_narrative_mismatch(transcript: str, email_draft: str) -> Dict[str, Any]:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=MISMATCH_PROMPT,
            messages=[
                {"role": "user", "content": f"TRANSCRIPT:\n{transcript}\n\nEMAIL DRAFT:\n{email_draft}"}
            ],
            temperature=0,
        )
        return _extract_json(response.content[0].text)
    except Exception as e:
        return {"mismatches": [], "deal_health_impact": 0, "summary": f"Analysis unavailable: {str(e)}"}


async def get_deal_ai_insights(deal_signals: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signals_text = "\n".join([f"- {k}: {v}" for k, v in deal_signals.items()])
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[
                {"role": "user", "content": f"Deal signals:\n{signals_text}\nReturn ONLY JSON: {{\"recommendation\": \"one sentence\", \"action_required\": true, \"risk_summary\": \"2-3 sentences\"}}"}
            ],
            temperature=0,
        )
        return _extract_json(response.content[0].text)
    except Exception as e:
        return {"recommendation": "Review manually.", "action_required": True, "risk_summary": "AI unavailable."}


async def analyse_discount_thread(email_thread: str) -> Dict[str, Any]:
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=DISCOUNT_PROMPT,
            messages=[
                {"role": "user", "content": f"EMAIL THREAD:\n{email_thread}"}
            ],
            temperature=0,
        )
        return _extract_json(response.content[0].text)
    except Exception as e:
        return {"mentions": [], "pressure_level": "normal", "benchmark_comparison": "Unavailable.", "recommendation": "Review manually."}