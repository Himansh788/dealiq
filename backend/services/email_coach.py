"""
Live Email Coach
================
Real-time analysis of an email draft as the rep types.
Provides instant feedback on:
- Deal health score impact preview
- Missing next steps
- Tone alignment with deal stage
- Specific improvement suggestions

Designed to be called on debounced keystrokes — must be fast.
Uses llama-3.1-8b-instant for sub-second response.
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


MODEL = "llama-3.1-8b-instant"  # Speed-optimised for real-time debounced calls


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found: {text[:200]}")


COACH_SYSTEM = """You are an elite B2B SaaS email coach with 15 years of enterprise sales experience.
You review sales email drafts in real-time as reps type and give sharp, specific feedback.

Your coaching philosophy:
- Every email must have ONE clear ask with a specific date/time
- Personalization beats templates — use the buyer's language
- Match urgency to deal health — zombie deals need pattern interrupts, not soft check-ins
- Subject lines must create curiosity or reference a shared context, never be generic
- Closing sentences must reduce friction to replying (yes/no questions, specific options)

Return ONLY valid JSON — no markdown, no text outside JSON."""


async def analyse_email_draft(
    email_draft: str,
    deal_context: Dict[str, Any],
    email_context: str = "",
) -> Dict[str, Any]:
    """
    Fast real-time analysis of an email draft in the context of a specific deal.
    Called on debounce as the rep types — optimised for speed.
    """
    if not email_draft or len(email_draft.strip()) < 20:
        return {
            "health_delta": 0,
            "has_next_step": False,
            "missing_elements": [],
            "strengths": [],
            "top_suggestion": "Start typing your email to see live coaching.",
            "readiness_score": 0,
            "send_ready": False,
            "tone_match": "weak",
        }

    deal_name = deal_context.get("name", "this deal")
    stage = deal_context.get("stage", "unknown")
    health_label = deal_context.get("health_label", "unknown")
    health_score = deal_context.get("health_score", 50)
    days_stalled = deal_context.get("days_stalled", 0)

    # Tone guidance by deal health
    tone_guide = {
        "zombie": "This deal needs a PATTERN INTERRUPT — not another soft check-in. The email should be unexpected, short, and create curiosity.",
        "critical": "High urgency. The email must acknowledge the silence directly and propose a very specific, low-friction next step.",
        "at_risk": "Moderate urgency. Reframe value, address likely objection, and end with a specific date-bound ask.",
        "healthy": "Momentum email. Affirm progress, preview next milestone, and confirm next meeting details.",
    }.get(health_label, "Write a clear, professional follow-up with a specific call to action.")

    email_ctx_section = f"\nRECENT EMAIL HISTORY (last 3):\n{email_context}\n" if email_context else ""

    prompt = f"""Coach this sales email draft in real-time.

DEAL: {deal_name} | Stage: {stage} | Health: {health_label} ({health_score}/100) | Days stalled: {days_stalled}
TONE REQUIREMENT: {tone_guide}{email_ctx_section}
EMAIL DRAFT:
---
{email_draft[:1500]}
---

Evaluate and return ONLY this JSON:
{{
  "health_delta": <integer -20 to +10 — negative if email is weak/generic/missing key elements, positive if strong and targeted>,
  "has_next_step": <true if email contains a clear next action with specific date OR specific question that forces a response>,
  "missing_elements": ["max 3 specific things — e.g., 'No proposed meeting time', 'Missing reference to their stated concern about pricing'"],
  "strengths": ["max 2 things this email does well — be specific"],
  "top_suggestion": "The single highest-impact edit — under 20 words, actionable, specific. E.g., 'Change CTA to: Are you free Thursday 3pm for a 15-min call?'",
  "readiness_score": <0-100 — how ready is this to send right now>,
  "send_ready": <true only if readiness_score >= 75>,
  "tone_match": "strong|acceptable|weak — does the tone match what a {health_label} deal needs?"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=500,
            temperature=0.2,
            messages=[
                {"role": "system", "content": COACH_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return _extract_json(resp.choices[0].message.content)
    except Exception as e:
        return {
            "health_delta": 0,
            "has_next_step": False,
            "missing_elements": [],
            "strengths": [],
            "top_suggestion": "Coach unavailable — write your email normally.",
            "readiness_score": 50,
            "send_ready": True,
            "tone_match": "acceptable",
        }
