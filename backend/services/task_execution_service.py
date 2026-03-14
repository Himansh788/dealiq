"""
Task Execution Service
======================
Generates executable content for each digest task type:
  - email      → AI-drafted email (subject + body_html + body_plain)
  - call       → AI call script with objection handlers
  - whatsapp   → Pre-written WhatsApp message + wa.me deep link
  - meeting    → Calendar invite draft
  - case_study → Vervotech content recommendations + draft email
  - contract / re_engage → Email follow-up

Called lazily from GET /digest/tasks/{task_id}/execution when a user expands a task.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
_SPEED_MODEL = "llama-3.1-8b-instant"

DEMO_CASE_STUDY_CONTENT = [
    {
        "title": "How a Leading TMC Improved Hotel Mapping Accuracy by 40%",
        "type": "case_study",
        "url": "https://vervotech.com/case-studies/",
        "relevance_reason": "Same client type and product focus — includes concrete ROI numbers",
        "key_stats": "40% accuracy improvement, 3× faster onboarding",
    },
    {
        "title": "Hotel Mapping Integration Guide",
        "type": "documentation",
        "url": "https://vervotech.com/documentation/",
        "relevance_reason": "Technical documentation for the evaluation stage",
        "key_stats": "",
    },
    {
        "title": "Why Travel Companies Are Switching to Automated Hotel Mapping",
        "type": "blog",
        "url": "https://vervotech.com/blogs/",
        "relevance_reason": "Thought leadership piece for decision makers",
        "key_stats": "",
    },
]


# --------------------------------------------------------------------------- #
# Groq helper
# --------------------------------------------------------------------------- #

async def _call_groq(prompt: str) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=GROQ_API_KEY)
        resp = await client.chat.completions.create(
            model=_SPEED_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.35,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("task_execution: Groq call failed: %s", e)
        return None


def _parse_json(raw: str) -> Optional[dict]:
    """Parse JSON from Groq response, stripping markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Per-type generators
# --------------------------------------------------------------------------- #

async def _gen_email(task: dict) -> dict:
    contact = task.get("contact_name") or "there"
    company  = task.get("company") or "your company"
    deal     = task.get("deal_name") or "your deal"
    stage    = task.get("stage") or ""
    amount   = task.get("amount_fmt") or ""
    ctx      = task.get("task_text") or ""
    reason   = task.get("reason") or ""

    prompt = f"""You are a B2B sales rep at Vervotech (hotel mapping & content API for travel companies).

Draft a concise follow-up email:
- Contact: {contact} at {company}
- Deal: {deal} ({stage}{', ' + amount if amount else ''})
- Situation: {ctx}
- Why flagged: {reason}

Rules:
- Under 120 words
- Specific — reference the deal stage and situation
- One clear CTA (schedule call, review doc, confirm next step)
- Warm professional tone; NOT "I hope this email finds you well"
- If following up late, acknowledge the gap briefly

Return ONLY valid JSON: {{"subject": "...", "body_html": "...", "body_plain": "..."}}"""

    raw = await _call_groq(prompt)
    data = _parse_json(raw) if raw else None

    if data and "subject" in data and "body_html" in data:
        return {
            "to": [{"email": "", "name": contact}],
            "subject": data["subject"],
            "body_html": data["body_html"],
            "body_plain": data.get("body_plain", data["body_html"]),
        }

    # Fallback template
    return {
        "to": [{"email": "", "name": contact}],
        "subject": f"Following up on {deal}",
        "body_html": (
            f"<p>Hi {contact},</p>"
            f"<p>{ctx}</p>"
            f"<p>Would you have 15 minutes this week to connect?</p>"
            f"<p>Best,<br/>[Your Name]</p>"
        ),
        "body_plain": f"Hi {contact},\n\n{ctx}\n\nWould you have 15 minutes this week to connect?\n\nBest,\n[Your Name]",
    }


async def _gen_call_script(task: dict) -> dict:
    contact = task.get("contact_name") or "them"
    company  = task.get("company") or "the prospect"
    deal     = task.get("deal_name") or "the deal"
    stage    = task.get("stage") or ""
    ctx      = task.get("task_text") or ""
    reason   = task.get("reason") or ""
    amount   = task.get("amount_fmt") or ""

    prompt = f"""Coach a B2B sales rep at Vervotech (hotel mapping API for travel companies) for a phone call.

Situation:
- Contact: {contact} at {company}
- Deal: {deal} ({stage}{', ' + amount if amount else ''})
- Reason: {ctx}
- Context: {reason}

Generate (each component ≤ 50 words, conversational not scripted):
- opening: natural opening referencing last interaction
- if_positive: how to advance if they're engaged
- if_objection_price: ROI-focused response
- if_objection_timing: response that keeps door open
- close: clear next-step question
- key_talking_points: array of 3 short bullet strings

Return ONLY valid JSON with those exact keys."""

    raw = await _call_groq(prompt)
    data = _parse_json(raw) if raw else None

    if data and "opening" in data:
        return {
            "contact": {"name": contact, "phone": None},
            "script": {
                "opening":               data.get("opening", ""),
                "if_positive":           data.get("if_positive", ""),
                "if_objection_price":    data.get("if_objection_price", ""),
                "if_objection_timing":   data.get("if_objection_timing", ""),
                "close":                 data.get("close", ""),
            },
            "key_talking_points": data.get("key_talking_points", []),
        }

    return {
        "contact": {"name": contact, "phone": None},
        "script": {
            "opening":             f"Hi {contact}, this is [Your Name] from Vervotech. I'm following up on {deal} — do you have a moment?",
            "if_positive":         "Great! What would be the best next step from your side?",
            "if_objection_price":  "I understand budget is a factor. Let me share ROI data from a similar client — saw strong returns in Q1.",
            "if_objection_timing": "Totally fair. When would be a better time to revisit this?",
            "close":               "What would be the best next step from your end?",
        },
        "key_talking_points": [
            f"Deal at {stage} stage — needs forward momentum",
            f"Context: {reason}",
            "Vervotech hotel mapping improves accuracy and speeds onboarding",
        ],
    }


async def _gen_whatsapp(task: dict) -> dict:
    contact = task.get("contact_name") or "there"
    deal    = task.get("deal_name") or "our deal"
    stage   = task.get("stage") or ""
    ctx     = task.get("task_text") or ""

    prompt = f"""Draft a WhatsApp follow-up message for a B2B sales rep at Vervotech.

Contact: {contact}
Deal: {deal} ({stage})
Context: {ctx}

Rules: under 80 words, casual but professional, one emoji max, friendly ask, not pushy.
Return ONLY the message text."""

    raw = await _call_groq(prompt)
    message = raw.strip() if raw else (
        f"Hi {contact}, hope you're doing well! Just checking in on {deal} — "
        "let me know if you have any questions or if there's anything I can help with. 🙌"
    )

    encoded = urllib.parse.quote(message)
    return {
        "contact": {"name": contact, "phone": None},
        "message": message,
        "whatsapp_deep_link": f"https://wa.me/?text={encoded}",
    }


async def _gen_meeting_draft(task: dict) -> dict:
    contact = task.get("contact_name") or "prospect"
    company = task.get("company") or "the prospect"
    deal    = task.get("deal_name") or "deal"
    stage   = task.get("stage") or ""
    ctx     = task.get("task_text") or ""

    subject = f"Vervotech — {stage} discussion for {company}" if stage else f"Vervotech — next steps for {company}"
    body_html = (
        f"<p>Hi {contact},</p>"
        f"<p>I'd love to schedule a quick call to discuss next steps for {deal}.</p>"
        f"<p>{ctx}</p>"
        f"<p>Looking forward to connecting!</p>"
        f"<p>Best,<br/>[Your Name]</p>"
    )
    return {
        "subject": subject,
        "attendees": [{"email": "", "name": contact}],
        "duration_minutes": 30,
        "body_html": body_html,
        "is_online": True,
    }


async def _gen_case_study(task: dict) -> dict:
    contact = task.get("contact_name") or "there"
    company = task.get("company") or "the prospect"
    deal    = task.get("deal_name") or "the deal"
    stage   = task.get("stage") or "Evaluation"

    # Try DB
    recommended = await _query_content_library(limit=3)
    if not recommended:
        recommended = DEMO_CASE_STUDY_CONTENT

    li_items = "".join(
        f"<li><a href='{c['url']}'>{c['title']}</a>"
        + (f" — {c.get('key_stats', '')}" if c.get("key_stats") else "")
        + "</li>"
        for c in recommended
    )
    subject  = f"Resources for your {stage.lower()} — {company}"
    body_html = (
        f"<p>Hi {contact},</p>"
        f"<p>I've put together some resources relevant to your evaluation of Vervotech for {deal}:</p>"
        f"<ul>{li_items}</ul>"
        f"<p>Happy to walk through any of these on a quick call. Would you have 15 minutes this week?</p>"
        f"<p>Best,<br/>[Your Name]</p>"
    )
    body_plain = (
        f"Hi {contact},\n\n"
        f"Here are some resources for your evaluation of Vervotech for {deal}:\n"
        + "\n".join(f"- {c['title']}: {c['url']}" for c in recommended)
        + "\n\nHappy to connect on a quick call.\n\nBest,\n[Your Name]"
    )

    return {
        "recommended_content": recommended,
        "draft_email": {
            "to": [{"email": "", "name": contact}],
            "subject": subject,
            "body_html": body_html,
            "body_plain": body_plain,
        },
    }


async def _query_content_library(limit: int = 3) -> list[dict]:
    try:
        from database.connection import get_db
        from sqlalchemy import text
        async for db in get_db():
            if db is None:
                return []
            result = await db.execute(text(
                "SELECT url, title, content_type, summary "
                "FROM vervotech_content "
                "ORDER BY has_specific_numbers DESC, scraped_at DESC "
                f"LIMIT {limit}"
            ))
            rows = result.fetchall()
            return [
                {
                    "title": r.title,
                    "type": r.content_type,
                    "url": r.url,
                    "relevance_reason": r.summary or "",
                    "key_stats": "",
                }
                for r in rows
            ]
    except Exception as e:
        logger.debug("content_library DB query failed: %s", e)
    return []


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

async def generate_execution(task: dict, outlook_connected: bool = False) -> dict:
    """
    Generate execution payload for one digest task.
    Returns an `execution` dict to attach to the task response.
    """
    task_type = task.get("task_type", "email")

    try:
        if task_type == "email":
            draft = await _gen_email(task)
            return {"type": "email", "ready_to_send": False, "draft": draft, "can_send_via_outlook": outlook_connected}

        if task_type == "call":
            data = await _gen_call_script(task)
            return {"type": "call_script", **data}

        if task_type == "whatsapp":
            data = await _gen_whatsapp(task)
            return {"type": "whatsapp_message", **data}

        if task_type == "meeting":
            data = await _gen_meeting_draft(task)
            return {"type": "calendar_invite", "draft": data, "can_create_via_outlook": outlook_connected}

        if task_type == "case_study":
            data = await _gen_case_study(task)
            return {"type": "content_recommendation", **data, "can_send_via_outlook": outlook_connected}

        # contract / re_engage / fallback → email
        draft = await _gen_email(task)
        return {"type": "email", "ready_to_send": False, "draft": draft, "can_send_via_outlook": outlook_connected}

    except Exception as e:
        logger.warning("task_execution: generate_execution failed task=%s: %s", task.get("id"), e)
        return {"type": "error", "error": str(e)}
