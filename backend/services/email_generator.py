"""
DealIQ Email Generator
======================
Generates context-rich follow-up emails using the Context Engine.

Two-pass approach:
  Pass 1 (context_engine.pre_process_transcript): extracts structured intel from transcript (1 AI call)
  Pass 2 (this file.generate):                   uses all assembled context for email draft (1 AI call)

The result is a Gong-quality email that:
  - Matches the rep's writing style (tone, greeting, signoff, word count)
  - Covers ALL commitments made on the call
  - Has a specific, dated next step
  - Flags anything needing approval before sending
"""

import logging
import time
from typing import Optional

import services.ai_router_ask as ai_router
from services.context_engine import ContextEngine, pre_process_transcript
from services.ask_dealiq_prompts import CONTEXT_EMAIL_SYSTEM_PROMPT

_log = logging.getLogger(__name__)


def _check_commitment_coverage(body: str, commitments: list[str]) -> list[dict]:
    """
    Lightweight check: are each call commitment's key words present in the email body?
    Returns [{commitment, covered}] for display in the frontend.
    """
    body_lower = body.lower()
    results = []
    for commitment in commitments:
        key_words = [w for w in commitment.lower().split() if len(w) > 4]
        # Covered if at least 2 key words appear (avoids false positives from stop words)
        match_count = sum(1 for w in key_words if w in body_lower)
        covered = match_count >= min(2, len(key_words)) if key_words else False
        results.append({"commitment": commitment, "covered": covered})
    return results


class EmailGenerator:
    """
    Context-aware email generator. Single public method: generate().
    Stateless — safe to instantiate per-request.
    """

    async def generate(
        self,
        deal: dict,
        emails: list,
        transcript: Optional[str],
        tone_override: Optional[str] = None,
        additional_context: Optional[str] = None,
    ) -> dict:
        start = time.monotonic()

        # Pass 1: Build structured deal context — zero AI tokens, rules-based only
        ctx = ContextEngine.build_deal_context(deal, emails, transcript)

        # Pass 2: Pre-process transcript if available (1 AI call for intelligence extraction)
        transcript_intel: dict = {}
        if transcript:
            transcript_intel = await pre_process_transcript(transcript)

        # Assemble the rich prompt context from all sources
        prompt_context = ctx.to_prompt_context(
            transcript_intel=transcript_intel or None,
            tone_override=tone_override,
            additional_context=additional_context,
            max_chars=6000,
        )

        has_emails = bool(emails)
        has_quoted = bool(ctx.emails)  # emails with quoted-chain context

        if transcript:
            instruction = (
                "Draft a follow-up email based on the transcript intelligence and deal context above."
            )
        elif has_emails or has_quoted:
            instruction = (
                "No call transcript is available. Draft a follow-up email that continues the existing "
                "conversation naturally. "
                "CRITICAL: reference the EMAIL THREAD — acknowledge the last topic discussed, "
                "address any unanswered buyer questions, and propose a concrete next step with a specific date. "
                "Mirror the rep's detected writing style exactly (greeting, signoff, length). "
                "If buyer replies are tagged [← BUYER], address their most recent message directly. "
                "If the deal appears stalled, write a value-add re-engagement — reference something "
                "specific from the thread, not a generic 'just checking in'."
            )
        else:
            instruction = (
                "No call transcript or email history is available. "
                "Draft a personalised re-engagement email using ONLY the deal context above: "
                "mention the deal stage, company name, and any deal-specific details. "
                "Do NOT write a generic 'just checking in' email — reference the deal stage "
                "and propose a specific next step with a concrete date. "
                "Keep it under 120 words. Be direct and value-focused."
            )

        try:
            result = await ai_router.generate_email_draft(
                system_prompt=CONTEXT_EMAIL_SYSTEM_PROMPT,
                context=f"{prompt_context}\n\nINSTRUCTION: {instruction}",
                max_tokens=2000,
            )
        except Exception as exc:
            _log.error("Context email generation failed: %s", exc)
            return {
                "error": f"Email generation unavailable: {str(exc)}",
                "subject": "",
                "body": "",
                "commitments_included": [],
                "next_step": "",
                "warnings": [],
                "commitment_coverage": [],
                "context_meta": {},
            }

        # Validate commitment coverage and warn about uncovered items
        rep_commitments: list[str] = transcript_intel.get("rep_commitments", []) if transcript_intel else []
        if rep_commitments:
            coverage = _check_commitment_coverage(result.get("body", ""), rep_commitments)
            result["commitment_coverage"] = coverage
            uncovered = [c["commitment"] for c in coverage if not c["covered"]]
            if uncovered:
                existing = result.get("warnings") or []
                for u in uncovered:
                    existing.append(f"Commitment not covered in draft: {u}")
                result["warnings"] = existing
        else:
            result["commitment_coverage"] = []

        # Context metadata for the frontend display panel
        contacts = deal.get("contacts") or deal.get("contact_roles") or []
        # Count buyer replies recovered from quoted chains
        from services.context_engine import ContextEngine as _CE
        internal_domains = _CE._detect_internal_domains(emails)
        quoted_replies = _CE._extract_quoted_replies(emails, internal_domains)
        buyer_replies_in_chain = sum(1 for q in quoted_replies if q["direction"] == "← BUYER")

        result["context_meta"] = {
            "transcript_available": transcript is not None,
            "transcript_intel_extracted": bool(transcript_intel),
            "email_history_available": len(emails) > 0,
            "email_count": len(emails),
            "buyer_replies_in_chain": buyer_replies_in_chain,
            "contacts_available": len(contacts),
            "rep_style_detected": ctx.rep_style.formality,
            "deal_health": deal.get("health_label", "unknown"),
            "tone_applied": tone_override or ctx.rep_style.formality,
        }

        result["processing_time_ms"] = int((time.monotonic() - start) * 1000)
        return result
