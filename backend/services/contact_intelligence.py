"""
Contact Intelligence
====================
Extracts stakeholders from matched Outlook emails for a deal, cross-references
against Zoho CRM contacts, and surfaces unknown participants as "potential personas"
for the rep to confirm or dismiss.

Public API
----------
    result = await get_deal_contacts(deal_id, zoho_token, user_key, db)
    await confirm_persona(deal_zoho_id, email, status, confirmed_by, db)
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_display_name(addr: str) -> tuple[str, str]:
    """
    Parse 'Display Name <email@domain.com>' or 'email@domain.com'.
    Returns (display_name, email_address).
    """
    m = re.match(r'^(.+?)\s*<([^>]+)>\s*$', addr.strip())
    if m:
        return m.group(1).strip().strip('"'), m.group(2).strip().lower()
    # bare address
    return "", addr.strip().lower()


def _is_internal(email_addr: str, internal_domain: str) -> bool:
    if not internal_domain or not email_addr:
        return False
    return email_addr.lower().endswith(f"@{internal_domain.lower()}")


def extract_outlook_personas(
    matched_emails: list[dict],
    zoho_contacts: list[dict],
    internal_domain: str = "",
) -> list[dict]:
    """
    Given a list of already-matched Outlook emails and the Zoho contacts for a deal,
    return a list of unknown participants (potential personas).

    Each returned dict has:
        email          str
        display_name   str (from email headers, may be empty)
        last_seen_at   str (ISO date of most recent email they appeared in)
        email_count    int (how many matched emails they appeared in)
        source         'outlook_discovered'
        status         'pending'
    """
    zoho_emails: set[str] = {
        c.get("email", "").lower() for c in zoho_contacts if c.get("email")
    }

    # Track unknown participants: email -> {display_name, dates: []}
    seen: dict[str, dict] = {}

    for msg in matched_emails:
        # Collect all participant addresses from normalised shape
        all_addrs: list[str] = []

        from_field = msg.get("from", "")
        if isinstance(from_field, str) and "@" in from_field:
            all_addrs.append(from_field)

        for field in ("to", "cc", "bcc"):
            entries = msg.get(field) or []
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, str) and "@" in e:
                        all_addrs.append(e)

        # Raw Graph shape fallback
        from_graph = msg.get("from") or {}
        if isinstance(from_graph, dict):
            addr = (from_graph.get("emailAddress") or {}).get("address", "")
            if addr:
                all_addrs.append(addr)
        for field in ("toRecipients", "ccRecipients", "bccRecipients"):
            for r in (msg.get(field) or []):
                addr = (r.get("emailAddress") or {}).get("address", "")
                name = (r.get("emailAddress") or {}).get("name", "")
                if addr:
                    all_addrs.append(f"{name} <{addr}>" if name else addr)

        # Get message date
        msg_date = (
            msg.get("receivedDateTime")
            or msg.get("sent_at")
            or msg.get("date")
            or ""
        )

        for raw_addr in all_addrs:
            display_name, email_addr = _parse_display_name(raw_addr)
            if not email_addr or "@" not in email_addr:
                continue
            if email_addr in zoho_emails:
                continue  # already a known Zoho contact
            if _is_internal(email_addr, internal_domain):
                continue  # rep's own org — not a prospect persona

            if email_addr not in seen:
                seen[email_addr] = {"display_name": display_name, "dates": [], "email_count": 0}
            else:
                # Update display name if we get a better one
                if display_name and not seen[email_addr]["display_name"]:
                    seen[email_addr]["display_name"] = display_name
            if msg_date:
                seen[email_addr]["dates"].append(msg_date)
            seen[email_addr]["email_count"] += 1

    personas = []
    for email_addr, meta in seen.items():
        last_seen = max(meta["dates"]) if meta["dates"] else ""
        personas.append({
            "email": email_addr,
            "display_name": meta["display_name"],
            "last_seen_at": last_seen,
            "email_count": meta["email_count"],
            "source": "outlook_discovered",
            "status": "pending",
        })

    # Sort: most active first
    personas.sort(key=lambda p: p["email_count"], reverse=True)
    return personas


async def get_deal_contacts(
    deal_id: str,
    zoho_token: str,
    user_key: str,
    db=None,
) -> dict:
    """
    Returns:
        {
            zoho_contacts: [...],        # confirmed CRM contacts with roles
            potential_personas: [...],   # Outlook-discovered, status=pending
            confirmed_personas: [...],   # rep-confirmed Outlook contacts
        }
    """
    from services.zoho_client import fetch_deal_contact_roles
    from services.outlook_enrichment import get_enriched_emails

    # ── 1. Fetch Zoho contacts ──────────────────────────────────────────────
    try:
        zoho_contacts = await fetch_deal_contact_roles(zoho_token, deal_id)
    except Exception as e:
        logger.warning("contact_intel: zoho contacts fetch failed deal=%s: %s", deal_id, e)
        zoho_contacts = []

    # ── 2. Fetch matched Outlook emails ────────────────────────────────────
    try:
        matched_emails = await get_enriched_emails(
            deal_id=deal_id,
            zoho_token=zoho_token,
            user_key=user_key,
            limit=50,
        )
    except Exception as e:
        logger.warning("contact_intel: outlook emails fetch failed deal=%s: %s", deal_id, e)
        matched_emails = []

    # ── 3. Extract unknown personas from Outlook ───────────────────────────
    discovered = extract_outlook_personas(matched_emails, zoho_contacts)

    # ── 4. Load DB state for this deal ─────────────────────────────────────
    db_personas: dict[str, dict] = {}
    if db:
        try:
            from sqlalchemy import select
            from database.models import DealPersona
            result = await db.execute(
                select(DealPersona).where(DealPersona.deal_zoho_id == deal_id)
            )
            rows = result.scalars().all()
            for row in rows:
                db_personas[row.email.lower()] = {
                    "email": row.email,
                    "name": row.name,
                    "display_name": row.display_name,
                    "role": row.role,
                    "source": row.source,
                    "status": row.status,
                    "confirmed_by": row.confirmed_by,
                    "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
                    "last_seen_at": row.last_seen_at,
                    "email_count": row.email_count,
                }
        except Exception as e:
            logger.warning("contact_intel: db fetch failed deal=%s: %s", deal_id, e)

    # ── 5. Merge DB state into discovered list ─────────────────────────────
    # Upsert discovered into DB (fire-and-forget)
    if db:
        try:
            await _upsert_personas(deal_id, discovered, db)
        except Exception as e:
            logger.warning("contact_intel: db upsert failed deal=%s: %s", deal_id, e)

    # Apply DB status overrides to discovered personas
    for p in discovered:
        db_state = db_personas.get(p["email"].lower())
        if db_state:
            p["status"] = db_state["status"]
            p["confirmed_by"] = db_state.get("confirmed_by")
            p["confirmed_at"] = db_state.get("confirmed_at")

    # Separate by status
    potential = [p for p in discovered if p["status"] == "pending"]
    confirmed = [p for p in discovered if p["status"] == "confirmed"]

    # Also include DB-confirmed personas that may not be in current email window
    for email_addr, db_state in db_personas.items():
        if db_state["status"] == "confirmed":
            already = any(p["email"].lower() == email_addr for p in confirmed)
            if not already:
                confirmed.append(db_state)

    return {
        "zoho_contacts": zoho_contacts,
        "potential_personas": potential,
        "confirmed_personas": confirmed,
    }


async def _upsert_personas(deal_zoho_id: str, personas: list[dict], db) -> None:
    """Insert new personas or update email_count / last_seen_at for existing ones."""
    from database.models import DealPersona
    from sqlalchemy import select

    for p in personas:
        email = p["email"].lower()
        try:
            result = await db.execute(
                select(DealPersona).where(
                    DealPersona.deal_zoho_id == deal_zoho_id,
                    DealPersona.email == email,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                # Update activity info but don't override rep decisions
                existing.email_count = p["email_count"]
                if p.get("last_seen_at"):
                    existing.last_seen_at = p["last_seen_at"]
                if p.get("display_name") and not existing.display_name:
                    existing.display_name = p["display_name"]
            else:
                db.add(DealPersona(
                    deal_zoho_id=deal_zoho_id,
                    email=email,
                    display_name=p.get("display_name"),
                    last_seen_at=p.get("last_seen_at"),
                    email_count=p.get("email_count", 1),
                    source="outlook_discovered",
                    status="pending",
                ))
        except Exception as e:
            logger.warning("contact_intel: upsert failed email=%s: %s", email, e)

    await db.commit()


def format_contacts_for_ai(
    zoho_contacts: list[dict],
    confirmed_personas: list[dict],
    potential_personas: list[dict],
) -> str:
    """
    Build a compact, AI-readable contact block for inclusion in any AI prompt.
    Example output:
        CONFIRMED CONTACTS:
          • Sarah Chen <sarah@acme.com> | Role: Economic Buyer | Source: CRM
          • Mike Torres <mike@acme.com> | Role: Unknown | Source: Outlook (confirmed by rep)
        POTENTIAL PERSONAS (unconfirmed — found in Outlook):
          • legal@acme.com | Appeared in 2 emails | Last seen: 2026-03-08
        NO CONTACTS: connect Outlook to discover personas.
    """
    lines = []

    confirmed_all = []
    for c in zoho_contacts:
        confirmed_all.append({
            "name": c.get("name") or "",
            "email": c.get("email") or "",
            "role": c.get("role") or "Unknown",
            "source": "CRM (Zoho)",
        })
    for p in confirmed_personas:
        confirmed_all.append({
            "name": p.get("display_name") or p.get("name") or "",
            "email": p.get("email") or "",
            "role": p.get("role") or "Unknown",
            "source": "Outlook (rep-confirmed)",
        })

    if confirmed_all:
        lines.append("CONFIRMED CONTACTS:")
        for c in confirmed_all:
            name_part = f"{c['name']} " if c['name'] else ""
            lines.append(f"  • {name_part}<{c['email']}> | Role: {c['role']} | Source: {c['source']}")
    else:
        lines.append("CONFIRMED CONTACTS: None — no CRM contacts linked and no Outlook personas confirmed yet.")

    if potential_personas:
        lines.append("POTENTIAL PERSONAS (seen in Outlook emails, not yet confirmed by rep):")
        for p in potential_personas[:5]:  # cap at 5 to keep prompt tight
            name_part = f"{p.get('display_name')} " if p.get("display_name") else ""
            last_seen = p.get("last_seen_at", "")[:10] if p.get("last_seen_at") else "unknown"
            count = p.get("email_count", 1)
            lines.append(f"  • {name_part}<{p['email']}> | {count} email(s) | Last seen: {last_seen}")

    return "\n".join(lines)


async def confirm_persona(
    deal_zoho_id: str,
    email: str,
    status: str,  # confirmed | rejected
    confirmed_by: str,
    db,
) -> bool:
    """Update the rep's decision for a persona. Returns True if record found."""
    if not db:
        return False
    from database.models import DealPersona
    from sqlalchemy import select

    email = email.lower()
    result = await db.execute(
        select(DealPersona).where(
            DealPersona.deal_zoho_id == deal_zoho_id,
            DealPersona.email == email,
        )
    )
    persona = result.scalar_one_or_none()
    if not persona:
        # Create it on the fly (rep confirming a Zoho contact explicitly)
        persona = DealPersona(
            deal_zoho_id=deal_zoho_id,
            email=email,
            source="outlook_discovered",
            status=status,
            confirmed_by=confirmed_by,
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(persona)
    else:
        persona.status = status
        persona.confirmed_by = confirmed_by
        persona.confirmed_at = datetime.now(timezone.utc)

    await db.commit()
    return True
