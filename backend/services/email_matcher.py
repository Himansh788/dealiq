"""
Email Attribution Engine
========================
Determines which Outlook emails belong to a specific deal using multi-signal
scoring.  Prevents wrong context from being fed into AI analysis.

Three-stage pipeline
--------------------
  Stage 1: Hard gates   — reject emails that clearly don't belong to this deal
  Stage 2: Scoring      — score surviving emails against five deal signals
  Stage 3: Tagging      — attach confidence + attribution metadata to each email

Public API
----------
    matched = match_outlook_emails(outlook_emails, deal_context, internal_domain)

    deal_context keys:
        deal_id       str
        deal_name     str
        account_name  str        (Zoho Account_Name field)
        created_time  str        (ISO 8601 — hard lower bound for emails)
        closing_date  str | None (ISO 8601 — upper bound = closing_date + 14d)
        stage         str
        contacts      list[{email, name, role}]   (from Zoho Contact_Roles)
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Stages where the deal is finished — emails still shown in timeline but
# marked post_close so they're excluded from live health scoring.
_CLOSED_STAGES = {
    "closed won", "closed lost", "closed - won", "closed - lost",
    "closed won", "lost",
}

# Minimum attribution score to include an email.
# Lower threshold applies when we have a confirmed exact contact email match.
_THRESHOLD_DEFAULT = 40
_THRESHOLD_CONTACT_MATCH = 25   # relax when exact contact email matched


# ── Utility helpers ────────────────────────────────────────────────────────

def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _extract_domain(email_addr: str) -> str:
    """Extract lowercase domain from 'name@domain.com' or 'Name <name@domain.com>'."""
    if not email_addr or "@" not in email_addr:
        return ""
    # Strip display-name wrappers
    match = re.search(r"<([^>]+)>", email_addr)
    addr = match.group(1) if match else email_addr
    return addr.split("@")[-1].lower().strip()


def account_name_to_domain(account_name: str) -> str:
    """
    Heuristic: 'Acme Corporation' → 'acme.com'
    Used as a soft signal only — domain matching gives bonus points, not a gate.
    """
    if not account_name:
        return ""
    # Remove common legal suffixes
    cleaned = re.sub(
        r"\b(inc|corp|corporation|ltd|limited|llc|gmbh|pvt|private|co|company"
        r"|group|holdings|technologies|technology|solutions|services|software"
        r"|systems|global|international|enterprises|ventures)\b",
        "",
        account_name.lower(),
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^a-z0-9]", "", cleaned).strip()
    return f"{cleaned}.com" if cleaned else ""


def _extract_participants(raw_msg: dict) -> list[str]:
    """
    Extract all email addresses from a message dict.
    Handles both:
      - Raw Microsoft Graph API shape (from.emailAddress, toRecipients, etc.)
      - Already-normalised shape produced by outlook_client.py
    Returns a de-duplicated lowercase list.
    """
    addrs: list[str] = []

    # Raw Graph shape
    from_field = raw_msg.get("from") or {}
    if isinstance(from_field, dict):
        addr = (from_field.get("emailAddress") or {}).get("address", "")
        if addr:
            addrs.append(addr.lower())

    for field in ("toRecipients", "ccRecipients", "bccRecipients"):
        for r in (raw_msg.get(field) or []):
            addr = (r.get("emailAddress") or {}).get("address", "")
            if addr:
                addrs.append(addr.lower())

    # Normalised shape (string "from" and list "to")
    if not addrs:
        from_str = raw_msg.get("from", "")
        if isinstance(from_str, str) and "@" in from_str:
            m = re.search(r"<([^>]+)>", from_str)
            addrs.append((m.group(1) if m else from_str).lower())

        for to_entry in (raw_msg.get("to") or []):
            if isinstance(to_entry, str) and "@" in to_entry:
                m = re.search(r"<([^>]+)>", to_entry)
                addrs.append((m.group(1) if m else to_entry).lower())

    return list(set(addrs))


def _is_internal_only(participants: list[str], internal_domain: str) -> bool:
    """True only if every participant belongs to the rep's internal domain."""
    if not participants or not internal_domain:
        return False
    return all(_extract_domain(p) == internal_domain.lower() for p in participants)


def _get_email_dt(raw_msg: dict) -> Optional[datetime]:
    dt_str = (
        raw_msg.get("receivedDateTime")
        or raw_msg.get("sent_at")
        or raw_msg.get("date")
    )
    return _parse_dt(dt_str)


# ── Stage 2: scoring ───────────────────────────────────────────────────────

def _score_email_for_deal(
    raw_msg: dict,
    participants: list[str],
    deal_context: dict,
    email_dt: datetime,
    contact_emails: set[str],
    contact_domains: set[str],
    account_domain: str,
) -> tuple[int, list[str]]:
    """
    Score one email against this deal. Returns (score, [reason, ...]).

    Signal breakdown (max 100):
      +30  Temporal window — email falls within deal lifecycle
      +25  Account domain match — participant @domain matches deal account
      +20  Subject relevance — subject contains account name or deal name
      +15  Exact contact email match — participant is a confirmed deal contact
      +10  Contact domain match — participant domain matches a contact's domain
    """
    score = 0
    reasons: list[str] = []

    # ── Temporal window (+30) ──────────────────────────────────────────────
    created_time = _parse_dt(deal_context.get("created_time"))
    closing_date_str = deal_context.get("closing_date")
    closing_dt = _parse_dt(closing_date_str) if closing_date_str else None
    upper_bound = (
        (closing_dt + timedelta(days=14))
        if closing_dt
        else (datetime.now(timezone.utc) + timedelta(days=30))
    )

    if created_time and email_dt >= created_time and email_dt <= upper_bound:
        score += 30
        reasons.append("temporal_window")

    # ── Exact contact email match (+15) ───────────────────────────────────
    if any(p in contact_emails for p in participants):
        score += 15
        reasons.append("contact_email_match")

    # ── Contact domain match (+10) ────────────────────────────────────────
    # Catches john@acme.com ↔ john.smith@acme.com mismatches in CRM
    participant_domains = {_extract_domain(p) for p in participants if _extract_domain(p)}
    if contact_domains & participant_domains:
        score += 10
        reasons.append("contact_domain_match")

    # ── Account domain match (+25) ────────────────────────────────────────
    if account_domain and account_domain in participant_domains:
        score += 25
        reasons.append("account_domain_match")

    # ── Subject relevance (+20 / +15) ─────────────────────────────────────
    subject = (raw_msg.get("subject") or "").lower()
    account_name = (deal_context.get("account_name") or "").lower().strip()
    deal_name = (deal_context.get("deal_name") or "").lower().strip()

    if account_name and len(account_name) > 3 and account_name in subject:
        score += 20
        reasons.append("subject_account_match")
    elif deal_name and len(deal_name) > 3 and deal_name in subject:
        score += 15
        reasons.append("subject_deal_match")

    return score, reasons


# ── Public entry point ─────────────────────────────────────────────────────

def match_outlook_emails(
    outlook_emails: list[dict],
    deal_context: dict,
    internal_domain: str = "",
) -> list[dict]:
    """
    Filter and score Outlook emails for a specific deal.

    Args:
        outlook_emails:  Raw messages from Microsoft Graph API (or normalised).
        deal_context:    Dict with keys:
                           deal_id, deal_name, account_name, created_time,
                           closing_date, stage, contacts (list[{email,name,role}])
        internal_domain: Rep's work email domain (e.g. 'acme-internal.com').
                         Used to classify internal-only threads.

    Returns:
        Filtered list of emails that confidently belong to this deal.
        Each email has an '_outlook_match' key with:
          confidence   int        0-100
          attribution  str        '+'-joined list of signals that fired
          in_zoho      bool       always False for Outlook-sourced emails
          source       str        'outlook_matched'
          is_internal  bool       True if thread has no external participants
          post_close   bool       True if email is after deal closed
    """
    if not outlook_emails:
        return []

    contacts = deal_context.get("contacts") or []
    contact_emails: set[str] = {
        c["email"].lower() for c in contacts if c.get("email")
    }
    contact_domains: set[str] = {
        _extract_domain(c["email"]) for c in contacts if c.get("email")
    }
    # Confirmed personas get a lower attribution threshold
    confirmed_contact_emails: set[str] = {
        c["email"].lower() for c in contacts
        if c.get("email") and c.get("status") in ("confirmed", "zoho")
    }
    # All Zoho contacts are treated as confirmed
    zoho_source_emails: set[str] = {
        c["email"].lower() for c in contacts
        if c.get("email") and c.get("source") == "zoho"
    }
    confirmed_contact_emails |= zoho_source_emails
    account_name = deal_context.get("account_name") or ""
    account_domain = account_name_to_domain(account_name)
    stage = (deal_context.get("stage") or "").lower()
    is_closed_deal = any(s in stage for s in _CLOSED_STAGES)

    # If we have nothing to match against at all, bail out early
    if not contact_emails and not account_domain:
        logger.warning(
            "email_matcher: deal=%s has no contacts and no resolvable account domain"
            " — Outlook emails cannot be attributed",
            deal_context.get("deal_id"),
        )
        return []

    results: list[dict] = []
    n_gate1 = 0
    n_score = 0

    for raw in outlook_emails:
        participants = _extract_participants(raw)
        if not participants:
            n_gate1 += 1
            continue

        # ── Stage 1 Gate G1.1: participant must match a contact email or account domain ──
        has_contact_match = bool(contact_emails & set(participants))
        participant_domains = {_extract_domain(p) for p in participants if p}
        has_domain_match = bool(account_domain and account_domain in participant_domains)

        if not has_contact_match and not has_domain_match:
            n_gate1 += 1
            continue

        # ── Stage 1 Gate G1.2: email must post-date deal creation ──────────
        email_dt = _get_email_dt(raw)
        if email_dt is None:
            n_gate1 += 1
            continue

        created_time = _parse_dt(deal_context.get("created_time"))
        if created_time and email_dt < created_time:
            n_gate1 += 1
            continue

        # G1.3: classify internal-only (don't reject — still valuable for activity feed)
        is_internal = _is_internal_only(participants, internal_domain)

        # ── Stage 2: Score ──────────────────────────────────────────────────
        score, reasons = _score_email_for_deal(
            raw, participants, deal_context, email_dt,
            contact_emails, contact_domains, account_domain,
        )

        # Apply threshold — relaxed further for confirmed personas
        has_confirmed_match = bool(confirmed_contact_emails & set(participants))
        if has_confirmed_match:
            threshold = 15  # very high confidence — confirmed stakeholder
        elif has_contact_match:
            threshold = _THRESHOLD_CONTACT_MATCH
        else:
            threshold = _THRESHOLD_DEFAULT
        if score < threshold:
            n_score += 1
            continue

        # ── Stage 3: Tag ────────────────────────────────────────────────────
        enriched = dict(raw)
        enriched["_outlook_match"] = {
            "confidence": min(100, score),
            "attribution": "+".join(reasons) if reasons else "domain_fallback",
            "in_zoho": False,
            "source": "outlook_matched",
            "is_internal": is_internal,
            "post_close": is_closed_deal,
        }
        results.append(enriched)

    logger.info(
        "email_matcher: deal=%s total=%d accepted=%d rejected_gate1=%d rejected_score=%d",
        deal_context.get("deal_id"),
        len(outlook_emails),
        len(results),
        n_gate1,
        n_score,
    )
    return results
