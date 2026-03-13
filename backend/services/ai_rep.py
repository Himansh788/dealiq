"""
AI Sales Rep Clone
==================
1. Reads deal history, stage, and signals
2. Generates a personalised Next Best Action plan
3. Drafts a follow-up email AS the rep
4. Handles buyer objections with exact response words
5. Generates a Pre-Call Intelligence Brief

The rep approves or rejects before anything is sent.
"""

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
import json
import re
import os
from typing import Dict, Any, List, Optional

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


MODEL = "claude-sonnet-4-6"


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in: {text[:300]}")


def _fmt(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${round(val/1_000)}K"
    return f"${round(val)}"


def _build_rep_persona(rep_name: str) -> str:
    return f"""You are {rep_name}, a high-performing B2B SaaS sales rep with a reputation for closing stuck deals.
You think in specifics, not generalities. You never say "follow up" without saying exactly what to say.
Your emails sound human — warm but purposeful, never corporate.
Core principles:
- Every touchpoint must have ONE clear ask with a specific date or deadline
- Match your energy to deal health: zombie deals get pattern interrupts, healthy deals get momentum
- You never discount without getting something in return (accelerated timeline, expanded scope, referral)
- You acknowledge the elephant in the room — silence, delays, concerns — instead of pretending they don't exist
- You think about what the BUYER needs to feel safe moving forward, not just what YOU need to close"""


NBA_PROMPT = """
{rep_persona}

You are analysing one of your deals and need to generate the highest-leverage next action.
You have access to the actual email thread — use it to understand what was said, what was promised, and where things broke down.

═══ DEAL DATA ═══
Deal: {deal_name}
Company: {account_name}
Stage: {stage}
Value: {amount}
Closing date: {closing_date}
Days since last buyer response: {days_since_buyer_response}
Next step in CRM: {next_step}
Contact count: {contact_count} | Economic buyer engaged: {economic_buyer_engaged}

STAKEHOLDERS:
{contacts_block}

Discount mentions: {discount_mention_count}
Activity last 30 days: {activity_count_30d}
Health score: {health_score}/100 ({health_label})

═══ DEAL CONTEXT ═══
{deal_context}

═══ HEALTH SIGNAL BREAKDOWN ═══
{signals_text}

═══ ACTUAL EMAIL THREAD ═══
IMPORTANT: The section labelled "MOST RECENT EMAILS" contains the latest conversation.
Your situation_read and primary_action MUST be based on these recent emails.
The "HISTORICAL CONTEXT" section is background only — do not use it to drive the next step.
When referencing emails in your analysis, always cite the specific date (e.g. "per the buyer's email on 2025-03-08").

{email_context}

Think step by step:
1. What is the DATE of the most recent email? What does it say? (cite it explicitly)
2. What does the most recent email thread reveal about the buyer's TRUE current sentiment?
3. What was promised but not delivered? What open loop is causing the stall?
4. What is the single highest-leverage action to take TODAY based on the MOST RECENT emails only?
5. What specific language from the buyer's most recent email should you reference or respond to?

Return ONLY this JSON:
{{
  "situation_read": "2-3 sentence honest assessment based on the MOST RECENT emails — cite the date of the last email (e.g. 'As of [date]...') so the rep knows you are working from current information",
  "urgency_level": "low|medium|high|critical",
  "email_insight": "The single most important thing the email thread reveals that the CRM data doesn't show",
  "primary_action": {{
    "what": "Specific action in 10 words or less — based on the email evidence",
    "why": "The specific reason from the email thread why THIS action will move THIS deal",
    "how": "Exact execution — what specific language to use, reference specific email content, channel, timing",
    "expected_outcome": "What success looks like in the next 48-72 hours"
  }},
  "secondary_actions": [
    {{
      "action": "Backup action if primary doesn't get a response",
      "timeline": "When to execute (e.g., 'If no reply in 3 business days')",
      "trigger": "The specific signal that triggers this action"
    }}
  ],
  "risk_if_no_action": "What happens to this deal if nothing is done in the next 5 business days",
  "confidence_score": 75,
  "rep_note": "One thing {rep_name} should remember about this specific buyer based on what you read in their emails"
}}"""


EMAIL_PROMPT = """
{rep_persona}

Write a sales follow-up email for this deal. You are writing AS {rep_name} — not on behalf of AI.

═══ DEAL CONTEXT ═══
Deal: {deal_name}
Company: {account_name}
Stage: {stage}
Value: {amount}
Health: {health_score}/100 ({health_label})
Days since last buyer response: {days_since_buyer_response}
CRM next step: {next_step}
Email objective: {email_objective}
Action context: {action_context}

RECIPIENT CONTEXT:
{contacts_block}

═══ DEAL CONTEXT ═══
{deal_context}

═══ RECENT EMAIL CONTEXT (last 5 emails) ═══
{email_context}

═══ EMAIL REQUIREMENTS ═══
- Subject line: specific, creates curiosity or references shared context — never generic
- Opening: no "Hope you're well" — reference something real (their last message, a shared context, the current situation)
- Body: max 4 short paragraphs — one clear message per paragraph
- CTA: ONE specific ask with a date or binary choice (e.g., "Does Thursday 3pm work, or is next week better?")
- Closing: warm but not sycophantic
- Tone must match health: {health_label} deals need {tone_guidance}
- Length: SHORT — under 150 words for zombie/critical, under 250 words for at_risk/healthy

Return ONLY this JSON:
{{
  "subject": "Email subject line",
  "body": "Full email body — use \\n for line breaks",
  "tone": "direct|warm|urgent|consultative",
  "cta": "The exact call-to-action",
  "why_this_approach": "One sentence explaining the strategic reasoning behind this email's approach"
}}"""


OBJECTION_PROMPT = """
{rep_persona}

A buyer just raised an objection on the deal: {deal_name} ({account_name}, {stage}, {amount}).
Deal health: {health_score}/100 ({health_label}).

OBJECTION: "{objection}"

═══ DEAL CONTEXT ═══
{deal_context}

═══ RECENT EMAIL CONTEXT (last 5 emails) ═══
{email_context}

Think step by step:
1. What is the REAL concern behind this objection? (people rarely say what they actually mean)
2. Is this a genuine concern or a negotiating tactic?
3. What is the most trust-building way to respond?
4. What question should you ask to advance the conversation?

Return ONLY this JSON:
{{
  "objection_type": "price|timing|authority|competition|value|internal_process|trust|other",
  "real_concern_behind_objection": "What the buyer actually means or fears (1-2 sentences — be insightful)",
  "is_genuine": true,
  "exact_response": "The exact words to say — conversational, not scripted-sounding. Under 50 words. Reference their specific concern.",
  "follow_up_question": "The one question to ask immediately after your response to move the conversation forward",
  "danger_signs": "Warning signs that this objection signals something deeper (or null if none)",
  "what_not_to_say": "The tempting response that would make things worse"
}}"""


CALL_BRIEF_PROMPT = """
{rep_persona}

You have a call coming up on deal: {deal_name} ({account_name}).
Prepare an elite pre-call intelligence brief so you walk in fully prepared.

═══ DEAL STATE ═══
Stage: {stage} | Value: {amount} | Health: {health_score}/100 ({health_label})
Days since last activity: {days_since_buyer_response}
Contact count: {contact_count} | Economic buyer engaged: {economic_buyer_engaged}
CRM next step: {next_step}

STAKEHOLDERS:
{contacts_block}

═══ DEAL CONTEXT ═══
{deal_context}

═══ HEALTH SIGNALS ═══
{signals_text}

═══ RECENT EMAIL CONTEXT (last 5 emails) ═══
{email_context}

═══ CLOSED ACTIVITIES & STAKEHOLDERS (from CRM) ═══
{activity_context}

Think like you're preparing for your most important call of the week.
What does the buyer need to feel? What do YOU need to walk away with?

Before writing the JSON, scan the email context above and extract EVERY concrete commitment, regardless of size:
- Scheduled meetings or calls with dates/times (e.g. "call Thursday 3pm", "demo next week")
- Documents sent or still pending (NDAs, contracts, proposals, pricing sheets, technical specs)
- People either side committed to adding or looping in (e.g. "I'll copy our CFO", "you'll introduce your CTO")
- Any action item either party agreed to, even small ones (e.g. "I'll send a calendar invite", "can you share the case study?")

List every one of these in what_was_promised — do not summarise them into a vague statement.
If the email context is empty or has no commitments, say so explicitly rather than inventing something.

Return ONLY this JSON:
{{
  "call_objective": "The single outcome you MUST achieve on this call (specific and measurable)",
  "situation_summary": "2-sentence honest summary of where this deal stands right now",
  "what_was_promised": "Bullet-point list of every concrete commitment from the emails — meetings with dates, docs sent/pending, people to be looped in, agreed action items. Example: '• Sent pricing proposal on [date] — awaiting response\\n• Promised to intro their CFO on next call\\n• Buyer asked for a case study — not yet sent'. If no emails or no commitments found, state that explicitly.",
  "stakeholder_intel": "What you know about the buyer's situation, pressures, and decision criteria",
  "talking_points": [
    "Talking point 1 — tied to their specific business context",
    "Talking point 2 — addresses the likely objection or concern",
    "Talking point 3 — creates urgency without pressure"
  ],
  "risk_questions": [
    "Question to uncover if budget is real: ...",
    "Question to uncover decision timeline: ...",
    "Question to uncover internal blockers: ..."
  ],
  "red_flags_to_watch": [
    "Signal that would tell you this deal is further gone than the CRM shows",
    "Signal that would tell you there's a competitor involved",
    "Signal that would tell you the champion has lost internal support"
  ],
  "opening_line": "Your exact suggested opening line for the call — specific, warm, not generic"
}}"""


async def generate_next_best_action(
    deal: Dict[str, Any],
    health_signals: List[Dict[str, Any]],
    rep_name: str,
    email_context: str = "",
    deal_context: str = "",
    contacts_block: str = "",
) -> Dict[str, Any]:
    signals_text = "\n".join([
        f"  [{s.get('label', '?').upper()}] {s.get('name', '')}: {s.get('detail', '')} ({s.get('score', 0)}/{s.get('max_score', 20)})"
        for s in health_signals
    ]) or "No signals available"

    email_context_text = email_context or "No email thread available — analysis based on CRM data only"

    # Hard cap on email context to prevent Anthropic 500s from oversized prompts
    MAX_EMAIL_CHARS = 3000
    if len(email_context_text) > MAX_EMAIL_CHARS:
        email_context_text = email_context_text[:MAX_EMAIL_CHARS] + "\n\n[... earlier emails truncated for length ...]"

    # Cap deal_context and contacts_block too
    deal_context_capped = (deal_context or "No additional deal context available.")[:1500]
    contacts_block_capped = (contacts_block or "No contact data available.")[:800]

    prompt = NBA_PROMPT.format(
        rep_persona=_build_rep_persona(rep_name),
        rep_name=rep_name,
        deal_name=deal.get("name", "Unknown"),
        account_name=deal.get("account_name", "Unknown"),
        stage=deal.get("stage", "Unknown"),
        amount=_fmt(deal.get("amount", 0)),
        closing_date=deal.get("closing_date", "Unknown"),
        days_since_buyer_response=deal.get("days_since_buyer_response", deal.get("last_activity_days", "Unknown")),
        next_step=deal.get("next_step") or "None set",
        contact_count=deal.get("contact_count", 1),
        economic_buyer_engaged=deal.get("economic_buyer_engaged", False),
        contacts_block=contacts_block_capped,
        discount_mention_count=deal.get("discount_mention_count", 0),
        activity_count_30d=deal.get("activity_count_30d", 0),
        health_score=deal.get("health_score", 0),
        health_label=deal.get("health_label", "unknown"),
        deal_context=deal_context_capped,
        signals_text=signals_text,
        email_context=email_context_text,
    )

    # Final safety cap — Anthropic 500s when prompt + max_tokens exceeds model limit
    MAX_PROMPT_CHARS = 28_000
    if len(prompt) > MAX_PROMPT_CHARS:
        # Trim from the email context section which is the most variable part
        overflow = len(prompt) - MAX_PROMPT_CHARS
        if len(email_context_text) > overflow + 200:
            trimmed = email_context_text[:len(email_context_text) - overflow - 200]
            trimmed += "\n\n[... emails truncated to fit context limit ...]"
            prompt = prompt.replace(email_context_text, trimmed)

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1400,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an elite B2B SaaS sales strategist. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "situation_read": f"Could not generate action plan: {str(e)[:100]}",
            "urgency_level": "high",
            "primary_action": {"what": "Review deal manually", "why": "AI unavailable", "how": "Check CRM notes", "expected_outcome": "Clarity on deal status"},
            "secondary_actions": [],
            "risk_if_no_action": "Deal may continue to stall without intervention.",
            "confidence_score": 0,
            "rep_note": "",
        }


async def generate_email_draft(
    deal: Dict[str, Any],
    rep_name: str,
    email_objective: str,
    action_context: str,
    email_context: str = "",
    deal_context: str = "",
    contacts_block: str = "",
) -> Dict[str, Any]:
    tone_guidance = {
        "zombie": "a bold pattern interrupt — short, direct, unexpected",
        "critical": "urgent acknowledgment of the silence with a very low-friction ask",
        "at_risk": "consultative — reconnect on value and propose a specific next step",
        "healthy": "confident and momentum-building",
    }.get(deal.get("health_label", ""), "professional and purposeful")

    prompt = EMAIL_PROMPT.format(
        rep_persona=_build_rep_persona(rep_name),
        rep_name=rep_name,
        deal_name=deal.get("name", "Unknown"),
        account_name=deal.get("account_name", "Unknown"),
        stage=deal.get("stage", "Unknown"),
        amount=_fmt(deal.get("amount", 0)),
        health_score=deal.get("health_score", 0),
        health_label=deal.get("health_label", "unknown"),
        days_since_buyer_response=deal.get("days_since_buyer_response", deal.get("last_activity_days", "Unknown")),
        next_step=deal.get("next_step") or "None set",
        email_objective=email_objective,
        action_context=action_context or "No specific context provided",
        contacts_block=contacts_block or "No contact data available.",
        tone_guidance=tone_guidance,
        deal_context=deal_context or "No additional deal context available.",
        email_context=email_context or "No email history available — analysis based on CRM data only.",
    )

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1000,
            temperature=0.4,
            messages=[
                {"role": "system", "content": "You are an elite B2B sales email writer. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        return _extract_json(resp.choices[0].message.content)
    except Exception as e:
        return {
            "subject": "Following up",
            "body": f"Could not generate email: {str(e)[:100]}",
            "tone": "professional",
            "cta": "Let me know your availability.",
            "why_this_approach": "Fallback — AI unavailable.",
        }


async def handle_objection(
    deal: Dict[str, Any],
    objection: str,
    rep_name: str,
    email_context: str = "",
    deal_context: str = "",
) -> Dict[str, Any]:
    prompt = OBJECTION_PROMPT.format(
        rep_persona=_build_rep_persona(rep_name),
        deal_name=deal.get("name", "Unknown"),
        account_name=deal.get("account_name", "Unknown"),
        stage=deal.get("stage", "Unknown"),
        amount=_fmt(deal.get("amount", 0)),
        health_score=deal.get("health_score", 0),
        health_label=deal.get("health_label", "unknown"),
        objection=objection,
        deal_context=deal_context or "No additional deal context available.",
        email_context=email_context or "No email history available — analysis based on CRM data only.",
    )

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=800,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an elite B2B sales coach. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        return _extract_json(resp.choices[0].message.content)
    except Exception as e:
        return {
            "objection_type": "other",
            "real_concern_behind_objection": "Could not analyse objection.",
            "is_genuine": True,
            "exact_response": "I understand your concern. Can you tell me more about what's driving that?",
            "follow_up_question": "What would need to be true for this to work for you?",
            "danger_signs": None,
            "what_not_to_say": "",
        }


async def generate_call_brief(
    deal: Dict[str, Any],
    health_signals: List[Dict[str, Any]],
    rep_name: str,
    email_context: str = "",
    activity_context: str = "",
    deal_context: str = "",
    contacts_block: str = "",
) -> Dict[str, Any]:
    signals_text = "\n".join([
        f"  [{s.get('label', '?').upper()}] {s.get('name', '')}: {s.get('detail', '')} ({s.get('score', 0)}/{s.get('max_score', 20)})"
        for s in health_signals
    ]) or "No signals available"

    prompt = CALL_BRIEF_PROMPT.format(
        rep_persona=_build_rep_persona(rep_name),
        deal_name=deal.get("name", "Unknown"),
        account_name=deal.get("account_name", "Unknown"),
        stage=deal.get("stage", "Unknown"),
        amount=_fmt(deal.get("amount", 0)),
        health_score=deal.get("health_score", 0),
        health_label=deal.get("health_label", "unknown"),
        days_since_buyer_response=deal.get("days_since_buyer_response", deal.get("last_activity_days", "Unknown")),
        contact_count=deal.get("contact_count", 1),
        economic_buyer_engaged=deal.get("economic_buyer_engaged", False),
        next_step=deal.get("next_step") or "None set",
        contacts_block=contacts_block or "No contact data available.",
        deal_context=deal_context or "No additional deal context available.",
        signals_text=signals_text,
        email_context=email_context or "No email history available — analysis based on CRM data only.",
        activity_context=activity_context or "No activity/contact data available — analysis based on CRM deal fields only.",
    )

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1400,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are an elite B2B sales strategist and call preparation expert. Return ONLY valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "call_objective": "Could not generate brief.",
            "situation_summary": str(e)[:100],
            "what_was_promised": "",
            "stakeholder_intel": "",
            "talking_points": [],
            "risk_questions": [],
            "red_flags_to_watch": [],
            "opening_line": "",
        }
