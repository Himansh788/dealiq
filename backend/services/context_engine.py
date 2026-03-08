"""
DealIQ Context Engine
=====================
Multi-source context assembler for AI prompts.

The core insight: email specificity comes from data quality, not model quality.
This engine assembles all available deal intelligence into structured context
before any AI call — the same thing Gong's AI teams spend months building.

Sources assembled:
  1. CRM deal metadata (stage, amount, close date, owner, probability)
  2. Contacts + engagement status
  3. Health score + label
  4. Email thread (last N messages, direction-tagged)
  5. Transcript raw text (fallback when pre-processing is unavailable)
  6. Rep writing style (rules-based, zero AI tokens)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

import services.ai_router_ask as ai_router
from services.ask_dealiq_prompts import TRANSCRIPT_INTEL_SYSTEM_PROMPT

_log = logging.getLogger(__name__)

MAX_EMAIL_BODY_CHARS = 1500
MAX_TRANSCRIPT_CHARS = 3000

# Regex patterns to detect quoted-message headers inside body_full.
# Zoho only stores outbound emails; buyer replies live as quoted text.
_INLINE_QUOTE_RE = re.compile(
    r"From:\s*([^<\n]*?<[^>\n]+>|[^\n]{3,80}?)\s+"
    r"(?:Sent|Date):\s*([^\n]{5,60}?)\s+To:\s+[^\n]+",
    re.IGNORECASE,
)
_MULTILINE_QUOTE_RE = re.compile(
    r"^From:\s*(.+?)[\r\n]+(?:Sent|Date):\s*(.+?)[\r\n]+(?:To|Cc):",
    re.IGNORECASE | re.MULTILINE,
)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RepStyle:
    formality: str = "semi-formal"        # formal | semi-formal | casual
    greeting_pattern: str = "Hi {name},"  # detected from outbound emails
    signoff: str = "Best,"                # detected signoff
    uses_bullet_points: bool = False
    uses_numbered_lists: bool = False
    avg_word_count: int = 100
    emoji_user: bool = False
    sample_opener: str = ""               # first content sentence from last email


@dataclass
class DealContext:
    deal: dict
    emails: list
    transcript_text: Optional[str]
    rep_style: RepStyle
    contacts: list = field(default_factory=list)
    health_score: Optional[int] = None
    health_label: Optional[str] = None

    def to_prompt_context(
        self,
        transcript_intel: Optional[dict] = None,
        tone_override: Optional[str] = None,
        additional_context: Optional[str] = None,
        max_chars: int = 6000,
    ) -> str:
        parts: list[str] = []

        # 1. Deal overview
        deal = self.deal
        amount = deal.get("amount") or 0
        parts.append(
            "=== DEAL OVERVIEW ===\n"
            f"Name: {deal.get('name', 'Unknown')}\n"
            f"Company: {deal.get('account_name') or deal.get('company', 'Unknown')}\n"
            f"Stage: {deal.get('stage', 'Unknown')}\n"
            f"Amount: ${amount:,.0f}\n"
            f"Close Date: {deal.get('closing_date') or deal.get('close_date') or 'Not set'}\n"
            f"Health: {self.health_score or deal.get('health_score', 'N/A')}/100 "
            f"({self.health_label or deal.get('health_label', 'unknown')})\n"
            f"Probability: {deal.get('probability', 'N/A')}%\n"
            f"Owner: {deal.get('owner', 'Unknown')}\n"
            f"Next Step: {deal.get('next_step') or 'Not defined'}"
        )

        # 2. Contacts
        contacts = self.contacts or deal.get("contacts") or deal.get("contact_roles") or []
        if contacts:
            lines = []
            for c in contacts:
                name = c.get("name") or c.get("Full_Name") or "Unknown"
                role = c.get("role") or c.get("Role") or "No role"
                email = c.get("email") or c.get("Email") or ""
                eng = c.get("engagement", "")
                line = f"  • {name} ({role})"
                if email:
                    line += f" — {email}"
                if eng:
                    line += f" [{eng}]"
                lines.append(line)
            parts.append("=== KEY CONTACTS ===\n" + "\n".join(lines))
        else:
            parts.append("=== KEY CONTACTS ===\nNo contact data available.")

        # 3. Rep writing style
        rs = self.rep_style
        style_lines = [
            f"Tone: {rs.formality.title()}",
            f"Greeting: \"{rs.greeting_pattern}\"",
            f"Signoff: \"{rs.signoff}\"",
            f"Avg email length: ~{rs.avg_word_count} words",
            f"Uses bullet points: {'Yes' if rs.uses_bullet_points else 'No'}",
        ]
        if rs.sample_opener:
            style_lines.append(f"Sample opener: \"{rs.sample_opener}\"")
        if tone_override:
            style_lines.append(f"TONE OVERRIDE: Write in {tone_override} tone")
        parts.append("=== REP WRITING STYLE ===\n" + "\n".join(style_lines))

        # 4. Transcript intelligence (if pre-processed) or raw transcript fallback
        if transcript_intel:
            ti_lines = []
            if transcript_intel.get("call_summary"):
                ti_lines.append(f"Call summary: {transcript_intel['call_summary']}")
            if transcript_intel.get("rep_commitments"):
                ti_lines.append("Rep committed to:")
                for c in transcript_intel["rep_commitments"]:
                    ti_lines.append(f"  ✓ {c}")
            if transcript_intel.get("buyer_commitments"):
                ti_lines.append("Buyer committed to:")
                for c in transcript_intel["buyer_commitments"]:
                    ti_lines.append(f"  ✓ {c}")
            if transcript_intel.get("next_steps"):
                ti_lines.append("Next steps agreed:")
                for s in transcript_intel["next_steps"]:
                    ti_lines.append(f"  → {s}")
            if transcript_intel.get("objections_raised"):
                ti_lines.append("Objections raised:")
                for o in transcript_intel["objections_raised"]:
                    ti_lines.append(f"  ⚠ {o}")
            if transcript_intel.get("budget_info"):
                ti_lines.append(f"Budget: {transcript_intel['budget_info']}")
            if transcript_intel.get("competition_mentioned"):
                ti_lines.append(f"Competition: {', '.join(transcript_intel['competition_mentioned'])}")
            if transcript_intel.get("sentiment"):
                ti_lines.append(f"Call sentiment: {transcript_intel['sentiment']}")
            if ti_lines:
                parts.append("=== TRANSCRIPT INTELLIGENCE ===\n" + "\n".join(ti_lines))
        elif self.transcript_text:
            truncated = self.transcript_text[:MAX_TRANSCRIPT_CHARS]
            suffix = "\n... [truncated]" if len(self.transcript_text) > MAX_TRANSCRIPT_CHARS else ""
            parts.append("=== CALL TRANSCRIPT ===\n" + truncated + suffix)
        else:
            parts.append("=== CALL TRANSCRIPT ===\nNo transcript available.")

        # 5. Email thread — Zoho-returned emails + quoted-chain recovery
        #    Zoho only stores outbound emails; buyer replies exist only as quoted
        #    text inside body_full. We parse those chains to surface [← BUYER] context.
        internal_domains = ContextEngine._detect_internal_domains(self.emails)

        thread = sorted(
            self.emails,
            key=lambda e: e.get("sent_time") or e.get("date") or e.get("sent_at") or "",
        )
        email_lines: list[str] = []
        for e in thread:
            direction_val = (e.get("direction") or "").lower()
            # "delivered" = our normalised value for inbound emails (set by _normalise_zoho_email)
            is_buyer = direction_val in ("incoming", "received", "inbound", "delivered")
            tag = "← BUYER" if is_buyer else "→ REP"
            body = (
                e.get("body_full") or e.get("content") or e.get("body") or e.get("text_body") or ""
            )[:MAX_EMAIL_BODY_CHARS]
            sent_at = e.get("sent_time") or e.get("date") or e.get("sent_at") or "unknown date"
            subj = e.get("subject") or "No subject"
            from_addr = e.get("from") or ""
            header = f"[{tag}] {sent_at[:10]} | {subj}"
            if from_addr:
                header += f" | From: {from_addr}"
            email_lines.append(f"{header}\n{body}")

        # Recover buyer replies from quoted chains when they aren't in the flat list
        has_buyer = any("← BUYER" in ln for ln in email_lines)
        if not has_buyer and self.emails:
            quoted = ContextEngine._extract_quoted_replies(self.emails, internal_domains)
            for q in quoted:
                email_lines.append(
                    f"[{q['direction']} — quoted] {q['date']} | From: {q['sender']}\n{q['body']}"
                )

        if email_lines:
            # Cap to last 10 entries so we don't blow the token budget
            parts.append(
                "=== EMAIL THREAD (recent) ===\n\n"
                + "\n\n---\n\n".join(email_lines[-10:])
            )
        else:
            parts.append("=== EMAIL THREAD ===\nNo email history available.")

        # 6. Additional instructions from the user
        if additional_context:
            parts.append(f"=== ADDITIONAL INSTRUCTIONS ===\n{additional_context}")

        context = "\n\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars] + "\n\n[Context trimmed to fit token budget.]"
        return context


# ── Context engine ────────────────────────────────────────────────────────────

class ContextEngine:
    """Assembles DealContext from raw deal data, emails, and transcript."""

    @staticmethod
    def _detect_internal_domains(emails: list) -> list[str]:
        """
        Infer the rep's email domain(s) from the from-addresses of outbound emails.
        Falls back to ["vervotech.com"] if nothing can be detected.
        """
        import re as _re
        domains: set[str] = set()
        for e in emails:
            direction = (e.get("direction") or "").lower()
            if direction not in ("sent", "outgoing", "outbound"):
                continue
            from_str = e.get("from") or ""
            match = _re.search(r"@([\w.-]+)", from_str)
            if match:
                domains.add(match.group(1).lower())
        return list(domains) or ["vervotech.com"]

    @staticmethod
    def _extract_quoted_replies(emails: list, internal_domains: list[str]) -> list[dict]:
        """
        Parse quoted email chains from body_full to recover buyer replies.

        Zoho only stores outbound emails — inbound replies exist only as quoted text
        inside subsequent sent emails. This function surfaces them for the AI.
        Returns a list of dicts: {direction, sender, date, body} oldest-first.
        """
        if not emails:
            return []

        # Use the email with the longest body — it has the most complete chain
        richest = max(emails, key=lambda e: len(e.get("body_full") or e.get("content") or ""))
        body = richest.get("body_full") or richest.get("content") or ""
        if len(body) < 200:
            return []

        seen_positions: list[int] = []
        matches: list[dict] = []

        for pat in (_MULTILINE_QUOTE_RE, _INLINE_QUOTE_RE):
            for m in pat.finditer(body):
                # Deduplicate overlapping matches
                if any(abs(pos - m.start()) < 100 for pos in seen_positions):
                    continue
                seen_positions.append(m.start())
                sender = m.group(1).strip()
                date_str = m.group(2).strip()
                is_rep = any(d.lower() in sender.lower() for d in internal_domains)
                # Snippet: text after this header until the next header
                snippet_start = m.end()
                next_hdr = body.find("From:", snippet_start + 10)
                snippet = body[snippet_start: next_hdr if next_hdr > 0 else snippet_start + 800]
                # Strip nested quoted lines (">")
                snippet = "\n".join(
                    ln for ln in snippet.splitlines() if not ln.lstrip().startswith(">")
                ).strip()[:600]
                matches.append({
                    "pos": m.start(),
                    "direction": "→ REP" if is_rep else "← BUYER",
                    "sender": sender,
                    "date": date_str,
                    "body": snippet,
                })

        # Sort oldest-first (deepest in chain = highest position index in text)
        matches.sort(key=lambda x: x["pos"], reverse=True)
        return matches

    @staticmethod
    def build_deal_context(
        deal: dict,
        emails: list,
        transcript: Optional[str],
    ) -> DealContext:
        contacts = deal.get("contacts") or deal.get("contact_roles") or []
        # "sent" = our normalised direction for outbound; also keep legacy Zoho values
        outbound = [
            e for e in emails
            if (e.get("direction") or "").lower()
            in ("outgoing", "sent", "outbound")
            or e.get("sent") is True
        ]
        rep_style = ContextEngine._analyse_rep_style(outbound)
        return DealContext(
            deal=deal,
            emails=emails,
            transcript_text=transcript,
            rep_style=rep_style,
            contacts=contacts,
            health_score=deal.get("health_score"),
            health_label=deal.get("health_label"),
        )

    @staticmethod
    def _analyse_rep_style(outbound_emails: list) -> RepStyle:
        """
        Rules-based rep style detection — zero AI tokens.
        Reads outbound email bodies to infer tone, greeting, signoff, length.
        """
        style = RepStyle()
        if not outbound_emails:
            return style

        bodies = []
        for e in outbound_emails[-5:]:
            body = e.get("body_full") or e.get("content") or e.get("body") or e.get("text_body") or ""
            if body.strip():
                bodies.append(body.strip())

        if not bodies:
            return style

        combined = "\n".join(bodies)

        # Average word count
        word_counts = [len(b.split()) for b in bodies]
        style.avg_word_count = sum(word_counts) // len(word_counts)

        # List detection
        style.uses_bullet_points = bool(re.search(r"^[\s]*[-•*]", combined, re.MULTILINE))
        style.uses_numbered_lists = bool(re.search(r"^\s*\d+\.", combined, re.MULTILINE))

        # Emoji detection
        emoji_re = re.compile("[\U00010000-\U0010ffff]", flags=re.UNICODE)
        style.emoji_user = bool(emoji_re.search(combined))

        # Greeting + formality from most recent email
        last = bodies[-1]
        first_line = last.split("\n")[0].strip()

        if re.match(r"^(Hi|Hey|Hello)\s+\w+", first_line, re.IGNORECASE):
            match = re.match(r"^(Hi|Hey|Hello)\s+(\w+)[,!]?", first_line, re.IGNORECASE)
            if match:
                style.greeting_pattern = f"{match.group(1)} {{name}},"
            style.formality = "casual"
        elif re.match(r"^Dear\s+\w+", first_line, re.IGNORECASE):
            style.greeting_pattern = "Dear {name},"
            style.formality = "formal"
        else:
            style.formality = "semi-formal"

        # Signoff detection
        for pattern, value in [
            (r"Best regards", "Best regards,"),
            (r"Kind regards", "Kind regards,"),
            (r"\bBest,", "Best,"),
            (r"\bThanks,", "Thanks,"),
            (r"Thank you,", "Thank you,"),
            (r"\bCheers,", "Cheers,"),
            (r"\bRegards,", "Regards,"),
        ]:
            if re.search(pattern, combined, re.IGNORECASE):
                style.signoff = value
                break

        # Sample opener: first non-greeting content sentence
        for line in last.split("\n")[1:4]:
            stripped = line.strip()
            if stripped and len(stripped) > 20:
                style.sample_opener = stripped[:120]
                break

        return style


# ── Transcript pre-processor ──────────────────────────────────────────────────

async def pre_process_transcript(transcript_text: str) -> dict:
    """
    AI Pass 1: extract structured intelligence from a raw call transcript.
    Called once per transcript; result is reused for all downstream AI calls.
    Uses the quality model — accuracy matters here.
    Returns an empty dict on any failure (graceful degradation).
    """
    if not ai_router.is_configured():
        return {}

    try:
        result = await ai_router.generate_structured_analysis(
            system_prompt=TRANSCRIPT_INTEL_SYSTEM_PROMPT,
            context=f"TRANSCRIPT:\n{transcript_text[:6000]}",
            max_tokens=1500,
        )
        return result
    except Exception as exc:
        _log.warning("Transcript pre-processing failed (degrading gracefully): %s", exc)
        return {}
