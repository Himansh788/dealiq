"""
Ask DealIQ Service
==================
Core Q&A engine — the DealIQ equivalent of Gong's Ask Anything.

Architecture:
1. User asks a question about a deal (or across all deals)
2. Service assembles context from available data (Zoho CRM or demo data)
3. Context is trimmed to token budget
4. Sends question + context to AI
5. Returns structured answer with source citations
"""

import re
import html
import time
import logging
from typing import Dict, Any, List, Optional

from services.ask_dealiq_prompts import (
    DEAL_QA_SYSTEM_PROMPT,
    MEDDIC_SYSTEM_PROMPT,
    DEAL_BRIEF_SYSTEM_PROMPT,
    FOLLOW_UP_EMAIL_SYSTEM_PROMPT,
    CROSS_DEAL_SYSTEM_PROMPT,
)
import services.ai_router_ask as ai_router

_log = logging.getLogger(__name__)


def sanitize_for_prompt(text: str | None) -> str:
    """
    Clean text for safe inclusion in LLM prompts and JSON payloads.
    Strips HTML, decodes entities, removes control characters that break JSON.
    """
    if not text:
        return ""
    # Strip HTML tags (email bodies are often HTML)
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode HTML entities (&amp; → &, &nbsp; → space, etc.)
    text = html.unescape(text)
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Tab → space
    text = text.replace("\t", " ")
    # Strip control chars that break JSON (keep \n = 0x0a)
    text = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", "", text)
    # Collapse excessive whitespace
    text = re.sub(r" {3,}", "  ", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


# ── Token budget constants (character-based approximation: ~4 chars per token) ──
CHARS_PER_TOKEN = 4
MAX_TOKENS_STANDARD = 6000
MAX_TOKENS_CROSS_DEAL = 4000
MAX_EMAIL_BODY_CHARS = 500
MAX_TRANSCRIPT_CHARS = 2000


def _estimate_chars(budget_tokens: int) -> int:
    return budget_tokens * CHARS_PER_TOKEN


def _fmt_contacts(contacts: list) -> str:
    if not contacts:
        return "No contact data available."
    lines = []
    for c in contacts:
        name = c.get("name") or c.get("Full_Name") or "Unknown"
        role = c.get("role") or c.get("Role") or "No role"
        email = c.get("email") or c.get("Email") or ""
        lines.append(f"  • {name} ({role})" + (f" — {email}" if email else ""))
    return "\n".join(lines)


def _fmt_emails(emails: list, limit: int = 10) -> str:
    if not emails:
        return "No email history available."
    lines = []
    for e in emails[-limit:]:
        direction_val = (e.get("direction") or e.get("type") or "").lower()
        is_buyer = direction_val in ("incoming", "received", "inbound")
        direction = "← BUYER" if is_buyer else "→ REP"
        raw_content = (
            e.get("content") or e.get("body") or e.get("html_body") or e.get("text_body") or ""
        )
        # Sanitize to remove control chars and HTML, then truncate
        content = sanitize_for_prompt(raw_content)
        if len(content) > MAX_EMAIL_BODY_CHARS:
            content = content[:MAX_EMAIL_BODY_CHARS] + "... [truncated]"
        sent_at = e.get("sent_time") or e.get("date") or "Unknown date"
        subject = sanitize_for_prompt(e.get("subject") or "No subject")
        lines.append(f"[{direction}] {sent_at} | {subject}\n{content}")
    return "\n\n".join(lines)


def _fmt_deal_meta(deal: dict) -> str:
    amount = deal.get("amount") or deal.get("Amount") or 0
    amount_fmt = f"${amount:,.0f}" if amount else "Not set"
    return (
        f"Deal: {deal.get('name', 'Unknown')}\n"
        f"Company: {deal.get('account_name') or deal.get('company', 'Unknown')}\n"
        f"Stage: {deal.get('stage', 'Unknown')}\n"
        f"Amount: {amount_fmt}\n"
        f"Close Date: {deal.get('closing_date') or deal.get('close_date') or 'Not set'}\n"
        f"Owner: {deal.get('owner', 'Unknown')}\n"
        f"Health Score: {deal.get('health_score', 'N/A')}/100 ({deal.get('health_label', 'unknown')})\n"
        f"Probability: {deal.get('probability', 'N/A')}%\n"
        f"Next Step: {deal.get('next_step') or deal.get('description') or 'Not defined'}\n"
        f"Last Activity: {deal.get('last_activity_time', 'Unknown')}\n"
        f"Discount Mentions: {deal.get('discount_mention_count', 0)}"
    )


def _assemble_deal_context(
    deal: dict,
    emails: list,
    transcript: Optional[str] = None,
    depth: str = "standard",
) -> str:
    """
    Assemble deal context into a single string for the AI prompt.
    depth: "minimal" | "standard" | "deep"
    """
    sections: List[str] = []

    # 1. Deal metadata — always included
    sections.append("=== DEAL METADATA ===\n" + _fmt_deal_meta(deal))

    # 2. Contacts — always included
    contacts = deal.get("contacts") or deal.get("contact_roles") or []
    sections.append("=== KEY CONTACTS ===\n" + _fmt_contacts(contacts))

    if depth == "minimal":
        return "\n\n".join(sections)

    # 3. Emails — standard and deep
    email_limit = 5 if depth == "standard" else 10
    sections.append(f"=== EMAIL HISTORY (last {email_limit}) ===\n" + _fmt_emails(emails, email_limit))

    # 4. Transcript — standard: most recent (truncated), deep: full
    if transcript:
        transcript = sanitize_for_prompt(transcript)
        max_chars = MAX_TRANSCRIPT_CHARS if depth == "standard" else MAX_TRANSCRIPT_CHARS * 3
        if len(transcript) > max_chars:
            transcript_section = transcript[:max_chars] + "\n... [transcript truncated for context window]"
        else:
            transcript_section = transcript
        sections.append("=== CALL TRANSCRIPT ===\n" + transcript_section)
    else:
        sections.append("=== CALL TRANSCRIPT ===\nNo transcript available for this deal.")

    return "\n\n".join(sections)


def _trim_to_budget(context: str, max_tokens: int) -> str:
    """Trim context to character budget, preserving structure."""
    max_chars = _estimate_chars(max_tokens)
    if len(context) <= max_chars:
        return context
    # Hard trim with note
    return context[:max_chars] + "\n\n[Context trimmed to fit token budget. Most recent data preserved.]"


# ── Public API ────────────────────────────────────────────────────────────────

async def ask_about_deal(
    deal: dict,
    emails: list,
    transcript: Optional[str],
    question: str,
) -> Dict[str, Any]:
    """
    Ask any natural language question about a specific deal.
    Returns structured answer with source citations.
    """
    if not ai_router.is_configured():
        return {
            "answer": "AI service not configured. Set ANTHROPIC_API_KEY to enable Ask DealIQ.",
            "sources_used": [],
            "confidence": "low",
            "deal_risks_detected": [],
            "suggested_next_step": None,
            "context_stats": {"emails_included": 0, "transcripts_included": 0, "health_scores_included": 0},
            "processing_time_ms": 0,
        }

    start = time.monotonic()

    context = _assemble_deal_context(deal, emails, transcript, depth="standard")
    context = _trim_to_budget(context, MAX_TOKENS_STANDARD)

    question_clean = sanitize_for_prompt(question)
    user_prompt = f"DEAL CONTEXT:\n{context}\n\nQUESTION: {question_clean}"

    # Safety check: ensure the assembled prompt is JSON-serializable before sending to LLM
    import json as _json
    try:
        _json.dumps({"content": user_prompt})
    except (ValueError, TypeError):
        # Nuclear fallback: strip all non-printable chars
        user_prompt = "".join(c for c in user_prompt if c.isprintable() or c == "\n")
        _log.warning("Prompt had non-serializable chars after sanitization — applied nuclear strip")

    try:
        result = await ai_router.ask_deal_question(
            system_prompt=DEAL_QA_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
        )
    except Exception as exc:
        _log.error("Ask deal question failed: %s", exc, exc_info=True)
        result = {
            "answer": "I wasn't able to process your question due to a data issue. Please try again — if the problem persists, try rephrasing your question.",
            "sources_used": [],
            "confidence": "low",
            "deal_risks_detected": [],
            "suggested_next_step": None,
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)

    email_count = min(len(emails), 5)
    health_signals = deal.get("signals") or []
    return {
        **result,
        "context_stats": {
            "emails_included": email_count,
            "transcripts_included": 1 if transcript else 0,
            "health_scores_included": len(health_signals) if health_signals else (1 if deal.get("health_score") else 0),
        },
        "processing_time_ms": elapsed_ms,
    }


async def ask_meddic_analysis(
    deal: dict,
    emails: list,
    transcript: Optional[str],
) -> Dict[str, Any]:
    """
    MEDDIC framework analysis of the most recent call transcript.
    Returns structured 6-element MEDDIC breakdown with evidence quotes.
    """
    if not ai_router.is_configured():
        return {"error": "AI service not configured. Set ANTHROPIC_API_KEY to enable MEDDIC analysis."}

    if not transcript:
        return {
            "error": "No transcript available for MEDDIC analysis.",
            "overall_score": "unknown",
            "gaps": ["No transcript data to analyse"],
            "recommended_questions_for_next_call": [],
        }

    start = time.monotonic()

    context_parts = [
        "=== DEAL CONTEXT ===",
        _fmt_deal_meta(deal),
        "\n=== CONTACTS ===",
        _fmt_contacts(deal.get("contacts") or deal.get("contact_roles") or []),
        "\n=== RECENT EMAILS (last 3) ===",
        _fmt_emails(emails, 3),
        "\n=== CALL TRANSCRIPT TO ANALYSE ===",
        transcript[:MAX_TRANSCRIPT_CHARS * 2],  # More generous for MEDDIC
    ]
    context = "\n".join(context_parts)
    context = _trim_to_budget(context, MAX_TOKENS_STANDARD)

    try:
        result = await ai_router.generate_structured_analysis(
            system_prompt=MEDDIC_SYSTEM_PROMPT,
            context=context,
            max_tokens=3000,
        )
    except Exception as exc:
        _log.error("MEDDIC analysis failed: %s", exc)
        return {"error": f"MEDDIC analysis unavailable: {str(exc)}"}

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {**result, "processing_time_ms": elapsed_ms}


async def generate_deal_brief(
    deal: dict,
    emails: list,
    transcript: Optional[str],
) -> Dict[str, Any]:
    """
    Generate a comprehensive deal brief (all sources, structured for manager review).
    """
    if not ai_router.is_configured():
        return {"error": "AI service not configured. Set ANTHROPIC_API_KEY to enable deal briefs."}

    start = time.monotonic()

    # Deep context for briefs
    context = _assemble_deal_context(deal, emails, transcript, depth="deep")
    context = _trim_to_budget(context, MAX_TOKENS_STANDARD)

    try:
        result = await ai_router.generate_structured_analysis(
            system_prompt=DEAL_BRIEF_SYSTEM_PROMPT,
            context=f"Generate a deal brief for the following deal:\n\n{context}",
            max_tokens=3000,
        )
    except Exception as exc:
        _log.error("Deal brief failed: %s", exc)
        return {"error": f"Deal brief unavailable: {str(exc)}"}

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {**result, "processing_time_ms": elapsed_ms}


async def suggest_follow_up_email(
    deal: dict,
    emails: list,
    transcript: Optional[str],
) -> Dict[str, Any]:
    """
    Generate a follow-up email from transcript (if available) or deal context + email history.
    Transcript is optional — falls back to CRM metadata and recent email thread.
    """
    if not ai_router.is_configured():
        return {"error": "AI service not configured. Set ANTHROPIC_API_KEY to enable email suggestions."}

    start = time.monotonic()

    outbound = [e for e in emails if (e.get("direction") or "").lower() in ("outgoing", "sent", "outbound")]

    context_parts = [
        "=== DEAL CONTEXT ===",
        _fmt_deal_meta(deal),
        "\n=== KEY CONTACTS ===",
        _fmt_contacts(deal.get("contacts") or deal.get("contact_roles") or []),
        "\n=== PREVIOUS EMAILS (rep tone reference — last 3 outbound) ===",
        _fmt_emails(outbound[-3:], 3),
    ]

    if transcript:
        context_parts.append("\n=== CALL TRANSCRIPT ===")
        context_parts.append(transcript[:MAX_TRANSCRIPT_CHARS])
        instruction = "Draft a follow-up email based on this call transcript and deal context:"
    else:
        context_parts.append("\n=== RECENT EMAIL THREAD (last 5) ===")
        context_parts.append(_fmt_emails(emails[-5:], 5))
        instruction = (
            "No call transcript is available. Draft a context-appropriate re-engagement email "
            "based on the deal stage, health score, and email history. "
            "If the deal appears stalled or at risk, write a recovery-style email with a clear next step."
        )

    context = "\n".join(context_parts)
    context = _trim_to_budget(context, 4000)

    try:
        result = await ai_router.generate_email_draft(
            system_prompt=FOLLOW_UP_EMAIL_SYSTEM_PROMPT,
            context=f"{instruction}\n\n{context}",
            max_tokens=1024,
        )
    except Exception as exc:
        _log.error("Follow-up email generation failed: %s", exc)
        return {"error": f"Email generation unavailable: {str(exc)}"}

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {**result, "processing_time_ms": elapsed_ms}


async def ask_across_deals(
    deals: list,
    question: str,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Ask a question across multiple deals (pipeline-level query).
    Uses summary-only context (no full email bodies) to stay within token budget.
    """
    if not ai_router.is_configured():
        return {
            "answer": "AI service not configured. Set ANTHROPIC_API_KEY to enable pipeline Q&A.",
            "deals_referenced": [],
            "confidence": "low",
        }

    start = time.monotonic()

    # Apply filters if provided
    filtered = deals
    if filters:
        if stage := filters.get("stage"):
            filtered = [d for d in filtered if (d.get("stage") or "").lower() == stage.lower()]
        if min_amount := filters.get("min_amount"):
            filtered = [d for d in filtered if (d.get("amount") or 0) >= min_amount]
        if owner := filters.get("owner_email"):
            filtered = [d for d in filtered if owner.lower() in (d.get("owner") or "").lower()]
        if health := filters.get("health_label"):
            filtered = [d for d in filtered if (d.get("health_label") or "").lower() == health.lower()]

    # Build compact summary for each deal
    deal_summaries: List[str] = []
    total_amount = 0
    for d in filtered:
        amount = d.get("amount") or 0
        total_amount += amount
        deal_id   = d.get("id") or d.get("deal_id") or "unknown"
        deal_name = d.get("name") or d.get("deal_name") or "Unnamed Deal"
        summary = (
            f"• [ID:{deal_id}] {deal_name} | Stage: {d.get('stage') or '?'} | "
            f"${amount:,.0f} | Health: {d.get('health_label') or 'unknown'} ({d.get('health_score') or '?'}/100) | "
            f"Owner: {d.get('owner') or '?'} | "
            f"Close date: {d.get('closing_date') or 'not set'} | "
            f"Last activity: {d.get('last_activity_time') or 'unknown'} | "
            f"Next step: {d.get('next_step') or d.get('description') or 'None defined'} | "
            f"Discounts mentioned: {d.get('discount_mention_count', 0)} | "
            f"Economic buyer engaged: {d.get('economic_buyer_engaged', False)}"
        )
        deal_summaries.append(summary)

    pipeline_summary = (
        f"PIPELINE SUMMARY:\n"
        f"Total deals: {len(filtered)} | Total value: ${total_amount:,.0f}\n\n"
        f"DEAL SUMMARIES:\n" + "\n".join(deal_summaries)
    )

    pipeline_summary = _trim_to_budget(pipeline_summary, MAX_TOKENS_CROSS_DEAL)

    user_prompt = f"{pipeline_summary}\n\nQUESTION: {question}"

    try:
        result = await ai_router.ask_pipeline_question(
            system_prompt=CROSS_DEAL_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1500,
        )
    except Exception as exc:
        _log.error("Cross-deal query failed: %s", exc)
        result = {
            "answer": f"Pipeline query failed: {str(exc)}",
            "deals_referenced": [],
            "confidence": "low",
        }

    elapsed_ms = int((time.monotonic() - start) * 1000)
    return {**result, "processing_time_ms": elapsed_ms}
