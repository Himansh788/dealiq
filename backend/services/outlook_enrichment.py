"""
Outlook Enrichment — Shared Email Fetch Service
================================================
Single entry point for any router that needs deal email data.

Returns merged emails: Outlook (primary, attributed) + Zoho (supplementary,
BCC-captured). Every caller gets the same enriched, de-duplicated, ordered
list without duplicating fetch or attribution logic.

Usage
-----
    from services.outlook_enrichment import get_enriched_emails, fmt_emails_for_ai

    emails = await get_enriched_emails(deal_id, zoho_token, user_key)
    context_str = fmt_emails_for_ai(emails, limit=8)

Edge cases handled
------------------
- Outlook not connected        → returns Zoho emails only (graceful)
- Zoho emails missing (no BCC) → returns Outlook emails only
- Deal has no contacts in Zoho → domain-level matching still attempted
- Token expired                → ms_auth auto-refreshes before fetch
- Redis / DB unavailable       → falls back to direct API calls
- Demo mode                    → returns [] (callers use SIMULATED_EMAILS)
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Public entry point ─────────────────────────────────────────────────────────

async def get_enriched_emails(
    deal_id: str,
    zoho_token: str,
    user_key: str,
    limit: int = 25,
) -> list[dict]:
    """
    Return merged + attributed emails for a deal, newest first.

    Each email dict has:
      source          str   'outlook' | 'zoho'
      direction       str   'sent' | 'delivered'
      subject         str
      from            str
      date / sent_at  str   ISO 8601
      body_preview    str
      body_full       str   (Zoho emails only; Outlook has bodyPreview)
      _outlook_match  dict  {confidence, attribution, in_zoho, is_internal}
                            present only for Outlook-sourced emails

    Results are cached in Redis per (user_key, deal_id) for 5 minutes.
    Cache is user-scoped — no cross-user leakage.
    """
    if not deal_id or not zoho_token:
        return []

    # ── Redis cache — user + deal scoped ──────────────────────────────────
    _cache_key = None
    try:
        from services.cache import cache_get, cache_set, cache_key as _ck, TTL_EMAIL_ENRICHMENT
        _safe_user = (user_key or "anon").replace(":", "_")
        _cache_key = _ck("emails", _safe_user, deal_id)
        _cached = await cache_get(_cache_key)
        # Only return cached result if it's non-empty — empty cache means a previous
        # failed fetch was stored; re-try so we don't silently return [] forever.
        if _cached:
            logger.info("outlook_enrichment: cache hit user=%s deal=%s count=%d", _safe_user, deal_id, len(_cached))
            return _cached[:limit]
        elif _cached is not None:
            logger.info("outlook_enrichment: cached empty result for deal=%s — bypassing cache to retry", deal_id)
    except Exception as e:
        logger.warning("outlook_enrichment: cache read error deal=%s: %s", deal_id, e)
        _cache_key = None

    # ── Step 1: build deal context for the attribution engine ──────────────
    deal_context: dict = {}
    try:
        from services.deal_context_builder import build_deal_context
        deal_context = await build_deal_context(zoho_token, deal_id)
    except Exception as e:
        logger.warning("outlook_enrichment: context build failed deal=%s: %s", deal_id, e)

    # ── Step 2: fetch Outlook emails (primary) ─────────────────────────────
    outlook_matched: list[dict] = []
    ms_token: str | None = None
    internal_domain = ""

    try:
        from routers.ms_auth import get_user_token
        ms_tokens_dict = await get_user_token(user_key)
        logger.info(
            "outlook_enrichment: deal=%s user_key=%s ms_tokens_dict_keys=%s",
            deal_id, user_key, list(ms_tokens_dict.keys()) if ms_tokens_dict else None,
        )
        if ms_tokens_dict:
            ms_token = ms_tokens_dict.get("access_token")
            ms_email = ms_tokens_dict.get("ms_email") or ""
            if "@" in ms_email:
                internal_domain = ms_email.split("@")[-1].lower()
        else:
            logger.warning("outlook_enrichment: no MS token found for user_key=%s", user_key)
    except Exception as e:
        logger.warning("outlook_enrichment: MS token lookup failed: %s", e)

    logger.info(
        "outlook_enrichment: deal=%s ms_token_present=%s internal_domain=%s deal_context_keys=%s",
        deal_id, bool(ms_token), internal_domain, list(deal_context.keys()) if deal_context else [],
    )

    if ms_token and deal_context:
        try:
            contacts = deal_context.get("contacts") or []
            # Log raw contact shapes to aid debugging
            logger.info(
                "outlook_enrichment: deal=%s contacts_raw=%s",
                deal_id,
                [{k: v for k, v in c.items() if any(x in k.lower() for x in ("mail", "email", "id", "name"))} for c in contacts],
            )
            contact_emails = []
            for c in contacts:
                email = c.get("email") or c.get("Email") or c.get("email_address") or c.get("Email_Address") or ""
                if isinstance(email, dict):
                    email = email.get("email") or email.get("address") or email.get("Email") or ""
                if isinstance(email, list):
                    email = email[0].get("address", "") if email else ""
                if not isinstance(email, str):
                    email = str(email) if email else ""
                email = email.strip().lower()
                if email and "@" in email:
                    contact_emails.append(email)
            logger.info(
                "outlook_enrichment: deal=%s contact_emails=%s",
                deal_id, contact_emails,
            )

            from services.outlook_client import sync_emails_for_deal
            raw_outlook = await sync_emails_for_deal(ms_token, deal_id, contact_emails)
            logger.info(
                "outlook_enrichment: deal=%s raw_outlook_count=%d",
                deal_id, len(raw_outlook),
            )

            if raw_outlook:
                from services.email_matcher import match_outlook_emails
                matched = match_outlook_emails(raw_outlook, deal_context, internal_domain)

                # Normalise each matched email to unified shape
                from routers.email_intel import _normalise_outlook_email
                for raw in matched:
                    n = _normalise_outlook_email(raw)
                    n["_outlook_match"] = raw.get("_outlook_match", {})
                    n["source"] = "outlook"
                    outlook_matched.append(n)

                logger.info(
                    "outlook_enrichment: deal=%s outlook_matched=%d",
                    deal_id, len(outlook_matched),
                )
        except Exception as e:
            logger.warning("outlook_enrichment: Outlook fetch failed deal=%s: %s", deal_id, e)

    # ── Step 3: fetch Zoho emails (supplementary) ─────────────────────────
    zoho_emails: list[dict] = []
    outlook_msg_ids = {e.get("message_id", "") for e in outlook_matched if e.get("message_id")}

    try:
        from services.zoho_client import fetch_deal_emails
        from routers.email_intel import _normalise_zoho_email
        raw_zoho = await fetch_deal_emails(zoho_token, deal_id)
        for raw in raw_zoho:
            n = _normalise_zoho_email(raw)
            mid = n.get("message_id", "")
            # Skip if Outlook already has this (prefer Outlook copy — has richer body)
            if mid and mid in outlook_msg_ids:
                continue
            n["source"] = "zoho"
            zoho_emails.append(n)
        logger.info("outlook_enrichment: deal=%s zoho_emails=%d", deal_id, len(zoho_emails))
    except Exception as e:
        logger.warning("outlook_enrichment: Zoho fetch failed deal=%s: %s", deal_id, e)

    # ── Step 4: merge, sort, cap ───────────────────────────────────────────
    merged = outlook_matched + zoho_emails
    merged.sort(key=lambda e: e.get("date") or e.get("sent_at") or "", reverse=True)
    result = merged[:limit]

    # ── Step 5: write to Redis cache (only cache non-empty results) ───────
    logger.info("outlook_enrichment: deal=%s final merged_count=%d (outlook=%d zoho=%d)",
        deal_id, len(result),
        sum(1 for e in result if e.get("source") == "outlook"),
        sum(1 for e in result if e.get("source") == "zoho"),
    )
    try:
        if _cache_key and result:
            from services.cache import cache_set, TTL_EMAIL_ENRICHMENT
            await cache_set(_cache_key, result, ttl=TTL_EMAIL_ENRICHMENT)
    except Exception as e:
        logger.warning("outlook_enrichment: cache write error deal=%s: %s", deal_id, e)

    return result


# ── AI prompt formatter ────────────────────────────────────────────────────────

def fmt_emails_for_ai(emails: list[dict], limit: int = 8) -> str:
    """
    Format merged emails into a rich context string for AI prompts.

    Shows direction, source, date, subject, and body.
    Skips internal-only threads (is_internal=True) — they're not buyer communication.
    Annotates Outlook-only emails so the AI knows they weren't in CRM.
    """
    if not emails:
        return "No email history available — analysis based on CRM metadata only."

    lines: list[str] = []
    count = 0

    for e in emails:
        if count >= limit:
            break

        # Skip internal-only Outlook emails — not buyer communication
        match_meta = e.get("_outlook_match") or {}
        if match_meta.get("is_internal"):
            continue

        direction_raw = (e.get("direction") or e.get("status") or "").lower()
        is_buyer = direction_raw in ("delivered", "received", "inbound", "incoming")
        arrow = "← BUYER" if is_buyer else "→ REP"

        source = e.get("source", "zoho")
        source_tag = "[Outlook — not in CRM]" if (source == "outlook" and match_meta.get("in_zoho") is False) else ""

        date_str = (e.get("date") or e.get("sent_at") or "")[:16].replace("T", " ")
        subject = e.get("subject") or "(no subject)"
        sender = e.get("from") or ""

        # Prefer full body, then preview, then snippet
        body = (
            e.get("body_full")
            or e.get("body_preview")
            or e.get("snippet")
            or ""
        )
        # Strip HTML tags
        if body and "<" in body:
            body = re.sub(r"<[^>]+>", " ", body)
            body = re.sub(r"\s+", " ", body).strip()
        body = body[:500] if body else "(no body)"

        header = f"[{arrow}] {date_str} {source_tag}"
        if sender:
            header += f" | From: {sender}"
        header += f" | Subject: {subject}"

        lines.append(f"{header}\n  {body}")
        count += 1

    if not lines:
        return "No buyer email communication found."

    n_outlook = sum(1 for e in emails[:limit] if e.get("source") == "outlook")
    n_crm_gap = sum(
        1 for e in emails[:limit]
        if e.get("source") == "outlook"
        and (e.get("_outlook_match") or {}).get("in_zoho") is False
    )

    header_note = f"[{len(lines)} emails shown"
    if n_crm_gap:
        header_note += f" — {n_crm_gap} from Outlook not captured in CRM (rep did not BCC)"
    header_note += "]"

    return header_note + "\n\n" + "\n\n---\n\n".join(lines)
