"""
Deal Health AI Analysis
=======================
Generates structured, context-aware AI analysis for deal health using Groq.
Called from the /deals/{id}/health endpoint after signals are computed.
Falls back gracefully to empty dict on any error — never blocks the health response.
"""

import json
import logging
import os
from typing import Optional, List

from groq import AsyncGroq

logger = logging.getLogger(__name__)

_client: AsyncGroq | None = None

MODEL = "llama-3.3-70b-versatile"


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def _format_signals(signals: list) -> str:
    lines = []
    for s in signals:
        lines.append(f"  - {s.name}: {s.score}/{s.max_score} [{s.label.upper()}] — {s.detail}")
    return "\n".join(lines) if lines else "  No signal data"


async def generate_deal_health_analysis(
    deal_name: str,
    deal_stage: str,
    deal_amount: Optional[float],
    deal_age_days: Optional[int],
    deal_owner: Optional[str],
    contact_name: Optional[str],
    signals: list,
    health_label: str,
    total_score: int,
    timeline_analysis: dict,
    activity_summary: dict,
) -> dict:
    """
    Generate structured AI analysis for a deal's health.

    Returns a dict with keys: analysis_summary, key_risk, root_cause,
    deal_status_assessment, win_probability_estimate, escalation_needed,
    recommended_actions (list of dicts).

    Returns {} on any error — caller should handle gracefully.
    """
    days_silent = (
        timeline_analysis.get("days_since_last_human_activity")
        or activity_summary.get("days_since_any_activity")
    )
    # Sanitize sentinel values
    if isinstance(days_silent, int) and days_silent >= 999:
        days_silent = None

    last_email_subject = timeline_analysis.get("last_email_subject") or "N/A"
    days_since_email = timeline_analysis.get("days_since_last_email")
    stage_progression = timeline_analysis.get("stage_progression", [])

    emails_out = activity_summary.get("emails_outbound", 0)
    emails_in = activity_summary.get("emails_inbound", 0)
    total_contacts = activity_summary.get("total_contacts", 0)

    if stage_progression:
        moves = [
            f"{p['old_stage']} → {p['new_stage']} ({p.get('direction', '?')})"
            for p in stage_progression[-3:]
        ]
        stage_progression_text = ", ".join(moves)
    else:
        stage_progression_text = "No stage movement recorded"

    signals_text = _format_signals(signals)
    critical_count = sum(1 for s in signals if s.label == "critical")
    amount_str = f"${deal_amount:,.0f}" if deal_amount else "Unknown"

    prompt = f"""You are a senior sales strategist analyzing CRM deal data for a B2B sales rep.
Be SPECIFIC — reference the contact name, email subject, stage name, and silence duration exactly as given.

## Deal
- Name: {deal_name}
- Stage: {deal_stage}
- Amount: {amount_str}
- Age: {deal_age_days or "Unknown"} days
- Owner: {deal_owner or "Unknown"}
- Primary Contact: {contact_name or "Unknown"}

## Health: {total_score}/100 ({health_label.upper()}) — {critical_count} critical signals

## Signals
{signals_text}

## Communication
- Emails sent by us: {emails_out}
- Emails from buyer: {emails_in}
- Contacts engaged: {total_contacts}
- Days since any activity: {days_silent or "Unknown"}
- Days since last email: {days_since_email or "Unknown"}
- Last email subject: {last_email_subject}

## Stage Movement
{stage_progression_text}

STRICT WRITING RULES — violating these makes the output useless:
1. analysis_summary: EXACTLY 3 sentences. Structure: (1) current state — what is happening right now, (2) root cause — what specifically caused this, (3) consequence — what happens if nothing changes this week. Never repeat a fact across sentences. No filler openings like "The deal..." or "Given the...".
2. key_risk: One sentence, one concrete fact. No vague phrases like "continued lack of engagement".
3. root_cause: One sentence naming the specific failure point (missed follow-up, no champion, pricing stall, etc.).
4. template_hint: NEVER start with "hoping you're doing well", "I wanted to follow up", "just checking in", or "I hope this email finds you". Start with a specific reference to the last topic discussed or a direct question. Max 2 sentences. End with exactly one question.

BAD template_hint: "Hi {contact_name or 'there'}, hoping you're doing well. I wanted to follow up on our previous discussion. Is this still a priority?"
GOOD template_hint: "Hi {contact_name or 'there'} — are you still evaluating [topic from last email subject]? I'd like to pick up where we left off and understand what changed."

Respond ONLY with valid JSON (no markdown fences, no explanation outside the JSON):
{{
  "analysis_summary": "Exactly 3 sentences. Current state. Root cause. Consequence.",
  "key_risk": "Single concrete risk sentence.",
  "root_cause": "One sentence naming the specific failure point.",
  "deal_status_assessment": "saveable | at_risk | likely_dead",
  "win_probability_estimate": "low | medium | high",
  "escalation_needed": true or false,
  "recommended_actions": [
    {{
      "priority": 1,
      "action": "Specific action referencing actual contact name, email subject, or deal detail",
      "reasoning": "Why this addresses the root cause",
      "urgency": "today | this_week | this_month",
      "template_hint": "A direct 1-2 sentence email opener. No filler. Starts with a reference to last email topic or a direct question."
    }},
    {{
      "priority": 2,
      "action": "...",
      "reasoning": "...",
      "urgency": "...",
      "template_hint": "..."
    }}
  ]
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=800,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content.strip()

        # Strip markdown code fences if model adds them
        if text.startswith("```"):
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]

        result = json.loads(text)
        return result

    except Exception as e:
        logger.warning("deal_health_ai: analysis failed for '%s': %s", deal_name, e)
        return {}
