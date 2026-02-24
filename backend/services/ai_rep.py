"""
AI Sales Rep Clone
==================
This service makes the AI "become" the sales rep by:
1. Reading their deal history, stage, and signals
2. Adopting their communication style (from past notes/emails if available)
3. Generating a personalised Next Best Action plan
4. Drafting a follow-up email AS the rep — not generic, but specific

The rep approves or rejects before anything is sent.
"""

import openai
import json
import re
import os
from typing import Dict, Any, List, Optional

# Lazy client — only created on first AI call, never at import time.
_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in: {text[:300]}")


def _build_rep_persona(rep_name: str, deal_history: List[Dict] = None) -> str:
    """Build a persona prompt for the AI to become the sales rep."""
    base = f"""You are {rep_name}, an experienced B2B SaaS sales representative.

Your job is to:
- Think and communicate exactly like {rep_name} would
- Give specific, actionable advice based on THIS deal's actual data
- Draft emails that sound human, warm, and specific — not templated
- Always think about what moves money forward, not what sounds good
- Be direct. Skip pleasantries in your reasoning. Be warm in your emails.

Your philosophy:
- Every interaction must have ONE clear ask
- Never discount without getting something in return
- Silence from a buyer is not rejection — it's a signal to try a different angle
- The best follow-up is one that gives value before asking for anything
"""
    return base


NBA_PROMPT_TEMPLATE = """
{rep_persona}

You are analysing one of your deals. Here is the full context:

DEAL NAME: {deal_name}
COMPANY: {account_name}
STAGE: {stage}
DEAL VALUE: ${amount}
CLOSING DATE: {closing_date}
DAYS SINCE LAST ACTIVITY: {days_since_activity}
HEALTH SCORE: {health_score}/100
HEALTH STATUS: {health_label}
PROBABILITY: {probability}%
NEXT STEP ON FILE: {next_step}

HEALTH SIGNALS:
{signals_text}

Based on this, generate your Next Best Action plan.

Return ONLY valid JSON:
{{
  "situation_read": "2-3 sentences on what is actually happening with this deal right now. Be honest and specific.",
  "urgency_level": "low|medium|high|critical",
  "primary_action": {{
    "what": "The single most important thing to do in the next 24 hours",
    "why": "Why this specific action, not something else",
    "how": "Exactly how to execute this — specific words, specific ask, specific channel",
    "expected_outcome": "What you expect to happen if this works"
  }},
  "secondary_actions": [
    {{
      "action": "Second priority action",
      "timeline": "When to do this",
      "trigger": "Do this if primary action results in X"
    }},
    {{
      "action": "Third priority action",
      "timeline": "When to do this",
      "trigger": "Do this if primary action results in Y"
    }}
  ],
  "risk_if_no_action": "What happens to this deal if nothing is done in the next 7 days",
  "confidence_score": 75,
  "rep_note": "One honest sentence from you as the rep about what you think is really going on"
}}
"""

EMAIL_DRAFT_PROMPT_TEMPLATE = """
{rep_persona}

You need to write a follow-up email for this deal. Write it AS {rep_name} — in first person, warm but direct.

DEAL CONTEXT:
- Deal: {deal_name} at {account_name}
- Stage: {stage}
- Value: ${amount}
- Days silent: {days_since_activity}
- Health: {health_label} ({health_score}/100)
- Last known next step: {next_step}
- Closing date: {closing_date}

ACTION PLAN CONTEXT:
{action_context}

EMAIL OBJECTIVE: {email_objective}

Rules for the email:
- Subject line must be specific — never generic like "Following up"
- First line must NOT be "I hope this email finds you well"
- Reference something specific about their business or previous conversation
- ONE clear call to action — not three options
- Keep it under 150 words in the body
- Sound like a human who cares about their success, not a salesperson hitting quota
- Sign off as {rep_name}

Return ONLY valid JSON:
{{
  "subject": "Email subject line",
  "body": "Full email body — use \\n for line breaks",
  "tone": "warm|urgent|value-led|re-engagement",
  "cta": "The specific ask in the email",
  "why_this_approach": "One sentence on why you chose this angle"
}}
"""

OBJECTION_HANDLER_PROMPT = """
{rep_persona}

A buyer has raised an objection. Help {rep_name} respond to it perfectly.

DEAL: {deal_name} at {account_name} — ${amount} — Stage: {stage}
OBJECTION: "{objection}"

Return ONLY valid JSON:
{{
  "objection_type": "price|timing|competition|stakeholder|technical|trust|no_need",
  "real_concern_behind_objection": "What they are actually worried about (not what they said)",
  "response_strategy": "The approach to take",
  "exact_response": "Word-for-word what {rep_name} should say/write back",
  "follow_up_question": "The one question to ask after giving the response",
  "danger_signs": "What would signal this objection is actually a deal-killer"
}}
"""


async def generate_next_best_action(
    deal: Dict[str, Any],
    health_signals: List[Dict[str, Any]],
    rep_name: str,
) -> Dict[str, Any]:
    """Generate a personalised Next Best Action plan for a specific deal."""
    try:
        signals_text = "\n".join([
            f"- {s.get('name', '')}: {s.get('detail', '')} [{s.get('label', '').upper()}]"
            for s in health_signals
        ])

        days_since = deal.get("last_activity_days") or deal.get("days_since_buyer_response") or "Unknown"

        prompt = NBA_PROMPT_TEMPLATE.format(
            rep_persona=_build_rep_persona(rep_name),
            deal_name=deal.get("name", "Unknown Deal"),
            account_name=deal.get("account_name", "Unknown Company"),
            stage=deal.get("stage", "Unknown"),
            amount=deal.get("amount", 0),
            closing_date=deal.get("closing_date", "Not set"),
            days_since_activity=days_since,
            health_score=deal.get("health_score", 0),
            health_label=deal.get("health_label", "unknown"),
            probability=deal.get("probability", 0),
            next_step=deal.get("next_step") or "None defined",
            signals_text=signals_text,
        )

        response = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return _extract_json(response.choices[0].message.content)

    except Exception as e:
        return {
            "situation_read": f"Could not generate AI analysis: {str(e)}",
            "urgency_level": "medium",
            "primary_action": {
                "what": "Review deal manually and define next step",
                "why": "AI analysis unavailable",
                "how": "Open deal in CRM and schedule a follow-up call",
                "expected_outcome": "Re-establish contact with buyer"
            },
            "secondary_actions": [],
            "risk_if_no_action": "Deal may continue to stall",
            "confidence_score": 0,
            "rep_note": "Manual review required"
        }


async def generate_email_draft(
    deal: Dict[str, Any],
    rep_name: str,
    email_objective: str,
    action_context: str = "",
) -> Dict[str, Any]:
    """Draft a personalised follow-up email AS the sales rep."""
    try:
        days_since = deal.get("last_activity_days") or deal.get("days_since_buyer_response") or "Unknown"

        prompt = EMAIL_DRAFT_PROMPT_TEMPLATE.format(
            rep_persona=_build_rep_persona(rep_name),
            rep_name=rep_name,
            deal_name=deal.get("name", "Unknown Deal"),
            account_name=deal.get("account_name", "Unknown Company"),
            stage=deal.get("stage", "Unknown"),
            amount=deal.get("amount", 0),
            closing_date=deal.get("closing_date", "Not set"),
            days_since_activity=days_since,
            health_score=deal.get("health_score", 0),
            health_label=deal.get("health_label", "unknown"),
            next_step=deal.get("next_step") or "None defined",
            email_objective=email_objective,
            action_context=action_context or "Re-engage buyer and establish next step",
        )

        response = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return _extract_json(response.choices[0].message.content)

    except Exception as e:
        return {
            "subject": f"Following up on {deal.get('name', 'our discussion')}",
            "body": f"Hi,\n\nI wanted to follow up on our recent conversation.\n\nWould you have 15 minutes this week to connect?\n\nBest,\n{rep_name}",
            "tone": "warm",
            "cta": "Schedule a 15-minute call",
            "why_this_approach": f"Fallback template — AI error: {str(e)}"
        }


async def handle_objection(
    deal: Dict[str, Any],
    objection: str,
    rep_name: str,
) -> Dict[str, Any]:
    """Generate a specific objection handling response."""
    try:
        prompt = OBJECTION_HANDLER_PROMPT.format(
            rep_persona=_build_rep_persona(rep_name),
            rep_name=rep_name,
            deal_name=deal.get("name", "Unknown Deal"),
            account_name=deal.get("account_name", "Unknown Company"),
            amount=deal.get("amount", 0),
            stage=deal.get("stage", "Unknown"),
            objection=objection,
        )

        response = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return _extract_json(response.choices[0].message.content)

    except Exception as e:
        return {
            "objection_type": "unknown",
            "real_concern_behind_objection": "Could not analyse objection",
            "response_strategy": "Acknowledge and ask clarifying question",
            "exact_response": "I hear you. Can you help me understand what's driving that concern?",
            "follow_up_question": "What would need to be true for this to move forward?",
            "danger_signs": f"AI error: {str(e)}"
        }
