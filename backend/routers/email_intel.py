"""
Email Intelligence router — full email threads with bodies + AI analysis.

Source priority for real sessions:
  1. Zoho CRM v8 — paginated fetch with full body per email
  2. Outlook     — supplementary if MS token connected
  3. Empty       — graceful degradation

Demo mode → SIMULATED_EMAILS from demo_data.py
"""

import base64
import json
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_db
from database.models import EmailExtraction
from services.demo_data import SIMULATED_EMAILS

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"access_token": token}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _user_key(session: dict) -> str:
    return session.get("email") or session.get("user_id") or "default"


async def _get_ms_token(user_key: str) -> str | None:
    try:
        from routers.ms_auth import get_user_token
        tokens = await get_user_token(user_key)
        return tokens.get("access_token") if tokens else None
    except Exception:
        return None


def _get_internal_domain(ms_tokens: dict | None) -> str:
    """Derive the rep's internal email domain from their MS account email."""
    if not ms_tokens:
        return ""
    ms_email = ms_tokens.get("ms_email") or ""
    if "@" in ms_email:
        return ms_email.split("@")[-1].lower()
    return ""


# ── Normalisation ──────────────────────────────────────────────────────────────

def _addr(val) -> str:
    if isinstance(val, dict):
        name  = val.get("user_name") or val.get("name") or ""
        email = val.get("email") or ""
        return f"{name} <{email}>" if name and email else email or name
    return str(val) if val else ""


def _addr_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, str):
        return [val]
    if isinstance(val, list):
        return [_addr(v) for v in val if v]
    return []


_INTERNAL_DOMAINS = ("vervotech.com",)


def _classify_direction(raw: dict, from_addr: str) -> str:
    """
    Determine email direction ('sent' | 'delivered').

    Priority order:
    1. Zoho's 'direction' field when it says 'incoming'/'received'/'inbound' — reliable for inbound.
    2. 'from' email domain check — most reliable signal overall.
       Zoho often returns direction='sent' for ALL emails on a Deal record (even buyer replies),
       so we trust the from-address over Zoho's 'sent'/'outgoing' direction claim.
    3. Zoho's boolean 'sent' flag — secondary fallback.
    4. Default to 'delivered' (inbound) to avoid over-counting sent.
    """
    direction_raw = (raw.get("direction") or "").lower()
    sent_flag = raw.get("sent")

    # If Zoho explicitly flags it as inbound, trust that.
    if direction_raw in ("incoming", "received", "inbound"):
        return "delivered"

    # Check the from address — most accurate signal.
    if from_addr:
        from_lower = from_addr.lower()
        if any(f"@{d}" in from_lower for d in _INTERNAL_DOMAINS):
            return "sent"
        # Has a from address that's NOT internal → inbound.
        return "delivered"

    # No from address: fall back to Zoho flags.
    if direction_raw in ("outgoing", "sent", "outbound"):
        return "sent"
    if isinstance(sent_flag, bool):
        return "sent" if sent_flag else "delivered"

    return "delivered"


def _normalise_zoho_email(raw: dict) -> dict:
    """
    Map a raw Zoho email (v2 or v8) to the unified frontend shape.
    Zoho fields: subject, from, to, sent_time, direction, sent (bool),
                 content (plain), html_content, message_id, thread_id
    """
    from_addr = _addr(raw.get("from") or raw.get("From") or raw.get("sender"))
    status = _classify_direction(raw, from_addr)

    # Prefer the enriched full-body fields set by _fetch_emails_for_record
    html_content = raw.get("html_content") or ""  # raw HTML — frontend renders via DOMPurify
    body_full    = raw.get("body_full") or raw.get("content") or raw.get("description") or raw.get("summary") or ""
    body_preview = raw.get("body_preview") or raw.get("snippet") or body_full[:300]
    snippet      = body_preview[:300].strip() if body_preview else ""

    return {
        "subject":      raw.get("subject") or raw.get("Subject") or "(no subject)",
        "from":         from_addr,
        "to":           _addr_list(raw.get("to") or raw.get("To") or []),
        "date":         raw.get("sent_time") or raw.get("time") or raw.get("date") or raw.get("Created_Time") or "",
        "snippet":      snippet,
        "body_preview": snippet,
        "body_full":    body_full,
        "html_content": html_content,
        "status":       status,
        "direction":    status,
        "sent_at":      raw.get("sent_time") or raw.get("time") or raw.get("date") or "",
        "thread_id":    raw.get("thread_id") or raw.get("message_id") or "",
        "message_id":   raw.get("message_id") or raw.get("id") or "",
    }


def _normalise_outlook_email(raw: dict) -> dict:
    sender_addr = (raw.get("from") or {}).get("emailAddress", {}).get("address", "")
    sender_name = (raw.get("from") or {}).get("emailAddress", {}).get("name", "")
    user_email  = os.getenv("OUTLOOK_USER_EMAIL", "").lower()
    status = "sent" if sender_addr.lower() == user_email else "delivered"

    to_list = [
        (r.get("emailAddress") or {}).get("address", "")
        for r in (raw.get("toRecipients") or [])
    ]
    snippet = (raw.get("bodyPreview") or "")[:300]
    from_str = f"{sender_name} <{sender_addr}>" if sender_name else sender_addr

    return {
        "subject":      raw.get("subject") or "(no subject)",
        "from":         from_str,
        "to":           to_list,
        "date":         raw.get("receivedDateTime") or "",
        "snippet":      snippet,
        "body_preview": snippet,
        "status":       status,
        "direction":    status,
        "sent_at":      raw.get("receivedDateTime") or "",
        "thread_id":    raw.get("conversationId") or "",
        "message_id":   raw.get("id") or "",
    }


def _group_into_threads(emails: list[dict]) -> list[dict]:
    """
    Group emails by thread_id. Each thread gets a list of messages
    sorted chronologically (oldest first within the thread).
    Returns threads sorted by most-recent-message descending.
    """
    threads: dict[str, list[dict]] = {}
    for e in emails:
        tid = e.get("thread_id") or e.get("message_id") or e.get("subject") or "ungrouped"
        threads.setdefault(tid, []).append(e)

    result = []
    for tid, messages in threads.items():
        messages.sort(key=lambda m: m.get("date") or m.get("sent_at") or "")
        latest = messages[-1]
        result.append({
            "thread_id":     tid,
            "subject":       messages[0].get("subject", "(no subject)"),
            "message_count": len(messages),
            "latest_date":   latest.get("date") or latest.get("sent_at") or "",
            "participants":  list({m.get("from", "") for m in messages if m.get("from")}),
            "messages":      messages,
        })

    result.sort(key=lambda t: t.get("latest_date") or "", reverse=True)
    return result


# ── AI analysis ───────────────────────────────────────────────────────────────

_ANALYSIS_SYSTEM = """You are a sales intelligence assistant analyzing email threads for a B2B sales rep.
Be specific and actionable. Use names, companies, and exact details from the thread.
Do NOT say vague things like "follow up with the client" — say exactly who, what, and when.

Return ONLY valid JSON in this exact shape (no markdown, no explanation):
{
  "summary": "2-3 sentence executive summary of where this deal stands. Be specific — mention real names, companies, and what was actually discussed or agreed.",
  "sentiment": "positive|neutral|negative|at_risk",
  "momentum": "accelerating|steady|stalling|gone_cold",
  "next_step": "One specific, concrete action the rep should take RIGHT NOW. Include who to contact, what to say or ask, and ideally by when. Example: 'Email Darryl (CEO) today to confirm call times — he asked for 2-3 options between 9-12pm UK time.'",
  "commitments": [
    {"by": "person name or company", "what": "the specific promise or commitment", "deadline": "date string or null", "status": "pending|overdue|fulfilled"}
  ],
  "open_questions": ["Specific unanswered question or unresolved blocker from the thread"],
  "deadlines": [
    {"what": "what is due", "date": "date string", "urgency": "high|medium|low"}
  ],
  "buying_signals": ["Specific positive indicator from the thread — quote or paraphrase real content"],
  "risk_signals": ["Specific concern or negative indicator — be concrete, not generic"],
  "key_contacts": [
    {"name": "Full Name", "role": "Job title or role in deal", "email": "email if mentioned", "engagement": "high|medium|low"}
  ],
  "relationship_map": "One paragraph describing who introduced whom, who are the decision makers vs champions vs potential blockers, and the relationship dynamics."
}"""


async def _analyse_thread(thread_text: str, deal_name: str) -> dict | None:
    """Send combined thread text to Groq and return structured analysis."""
    try:
        from services.ai_router_ask import generate_structured_analysis
        prompt = f"Deal: {deal_name}\n\n--- EMAIL THREAD ---\n{thread_text[:8000]}"
        return await generate_structured_analysis(_ANALYSIS_SYSTEM, prompt, max_tokens=1200)
    except Exception as e:
        logger.warning("Thread AI analysis failed: %s", e)
        return None


def _build_thread_text(messages: list[dict]) -> str:
    """
    Join messages chronologically into a readable transcript for the AI.
    Uses body_full when available (contains full quoted thread history from Zoho),
    falling back to body_preview / snippet for metadata-only emails.
    """
    parts = []
    for m in messages:
        sender = m.get("from") or "Unknown"
        date   = m.get("date") or m.get("sent_at") or ""
        # body_full may contain the entire thread quoted — ideal for AI context
        body = m.get("body_full") or m.get("body_preview") or m.get("snippet") or "(no body)"
        # Cap per-message to 3000 chars to keep total prompt size reasonable
        parts.append(f"[{date[:10]}] FROM: {sender}\n{body[:3000]}")
    return "\n\n---\n\n".join(parts)


async def _get_db_extraction(deal_id: str, db) -> dict | None:
    if db is None:
        return None
    try:
        row = (await db.execute(
            select(EmailExtraction)
            .where(EmailExtraction.deal_zoho_id == deal_id)
            .order_by(EmailExtraction.created_at.desc())
            .limit(1)
        )).scalars().first()
        if row:
            return {
                "next_step":      row.next_step,
                "commitments":    row.commitments or [],
                "open_questions": row.open_questions or [],
                "sentiment":      row.sentiment,
            }
    except Exception:
        pass
    return None


# ── Fetch helpers ─────────────────────────────────────────────────────────────

async def _fetch_zoho_emails(zoho_token: str, deal_id: str) -> list[dict]:
    from services.zoho_client import fetch_deal_emails
    raw = await fetch_deal_emails(zoho_token, deal_id)
    return [_normalise_zoho_email(e) for e in raw]


async def _fetch_and_match_outlook_emails(
    ms_token: str,
    deal_context: dict,
    internal_domain: str,
    zoho_message_ids: set[str],
) -> list[dict]:
    """
    Fetch Outlook emails for the deal's contact email addresses, run them through
    the attribution engine, normalise, and de-duplicate against what Zoho already has.

    Returns a list of normalised email dicts (same shape as Zoho emails) that are
    NOT already in Zoho, each tagged with _outlook_match attribution metadata.
    """
    from services.outlook_client import sync_emails_for_deal
    from services.email_matcher import match_outlook_emails

    contacts = deal_context.get("contacts") or []
    contact_emails = []
    for c in contacts:
        val = c.get("email") or c.get("Email") or ""
        if isinstance(val, dict):
            val = val.get("email") or val.get("address") or ""
        if val and isinstance(val, str):
            contact_emails.append(val.strip().lower())

    if not contact_emails and not deal_context.get("account_name"):
        logger.info(
            "email_intel: deal=%s no contacts or account — skipping Outlook fetch",
            deal_context.get("deal_id"),
        )
        return []

    # Fetch from Graph API scoped to deal's contact emails
    raw_outlook = await sync_emails_for_deal(
        ms_token,
        deal_context.get("deal_id", ""),
        contact_emails,
    )
    logger.info(
        "email_intel: deal=%s outlook_raw=%d",
        deal_context.get("deal_id"), len(raw_outlook),
    )

    if not raw_outlook:
        return []

    # Run attribution engine — filters + scores each email
    matched = match_outlook_emails(raw_outlook, deal_context, internal_domain)

    # Normalise and de-duplicate against Zoho emails (by message_id first, then subject+date)
    results: list[dict] = []
    seen_subjects_dates: set[tuple] = set()

    for raw in matched:
        n = _normalise_outlook_email(raw)
        # Carry attribution metadata forward
        n["_outlook_match"] = raw.get("_outlook_match", {})
        n["source"] = "outlook"

        msg_id = n.get("message_id", "")
        # Skip if Zoho already has this message
        if msg_id and msg_id in zoho_message_ids:
            continue

        # Fallback de-dup by subject + date (first 10 chars)
        key = (n.get("subject", ""), (n.get("date") or "")[:10])
        if key in seen_subjects_dates:
            continue

        seen_subjects_dates.add(key)
        results.append(n)

    logger.info(
        "email_intel: deal=%s outlook_matched=%d after_dedup=%d",
        deal_context.get("deal_id"), len(matched), len(results),
    )
    return results


async def _write_outlook_gap_note(zoho_token: str, deal_id: str, emails: list[dict]) -> None:
    """
    Write a single CRM note summarising Outlook emails that weren't BCC'd to Zoho.
    Uses the existing zoho_writer if available; silently no-ops if it fails.
    """
    try:
        from services.zoho_client import ZOHO_API_BASE
        import httpx

        # Build a concise note body
        lines = ["[DealIQ Auto-Enriched] The following emails were found in Outlook but are not in Zoho CRM:"]
        lines.append(f"Total emails not in CRM: {len(emails)}")
        lines.append("")
        for e in emails[:5]:   # cap at 5 to keep note readable
            date_str = (e.get("sent_at") or e.get("date") or "")[:10]
            subject = e.get("subject") or "(no subject)"
            from_addr = e.get("from") or ""
            conf = (e.get("_outlook_match") or {}).get("confidence", "?")
            lines.append(f"• [{date_str}] From: {from_addr} | Subject: {subject} | Confidence: {conf}%")
        if len(emails) > 5:
            lines.append(f"  … and {len(emails) - 5} more.")
        lines.append("")
        lines.append("Action: Ask rep to enable BCC to Zoho or forward these threads to the CRM dropbox.")
        note_content = "\n".join(lines)

        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{ZOHO_API_BASE}/Notes",
                headers={
                    "Authorization": f"Zoho-oauthtoken {zoho_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "data": [{
                        "Note_Title": f"[DealIQ] {len(emails)} email(s) found in Outlook not in CRM",
                        "Note_Content": note_content,
                        "Parent_Id": deal_id,
                        "$se_module": "Deals",
                    }]
                },
            )
        logger.info("email_intel: CRM gap note written for deal=%s emails=%d", deal_id, len(emails))
    except Exception as e:
        logger.warning("email_intel: CRM gap note failed deal=%s: %s", deal_id, e)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/threads/{deal_id}")
async def get_email_thread(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
    force_refresh: bool = False,
):
    """
    Return full email threads with bodies for a deal.
    Flat list + thread-grouped list returned together.
    AI analysis runs inline on the most active thread.
    Results are cached in Redis for 15 min. Pass ?force_refresh=true to bypass.
    """
    session = _decode_session(authorization)
    user_key = _user_key(session)

    # ── Redis cache (skip for demo, skip when force_refresh=true) ─────────────
    if not _is_demo(session) and not force_refresh:
        try:
            from services.cache import cache_get, cache_key as _ck
            _cache_key = _ck("email_intel", user_key, deal_id)
            cached = await cache_get(_cache_key)
            if cached and cached.get("thread_count", 0) > 0:
                logger.info("email_intel: cache hit user=%s deal=%s thread_count=%d", user_key, deal_id, cached.get("thread_count"))
                return cached
            elif cached is not None:
                logger.info("email_intel: cached empty result for deal=%s — bypassing to retry", deal_id)
        except Exception as _ce:
            logger.warning("email_intel: cache_get error deal=%s: %s", deal_id, _ce)

    # ── Demo ──────────────────────────────────────────────────────────────────
    if _is_demo(session) or deal_id.startswith("sim_"):
        raw_emails = SIMULATED_EMAILS.get(deal_id, [])
        emails = [_normalise_zoho_email(e) for e in raw_emails]
        threads = _group_into_threads(emails)

        # Quick AI analysis on demo emails
        extracted = await _get_db_extraction(deal_id, db)
        if not extracted and threads:
            thread_text = _build_thread_text(threads[0]["messages"])
            extracted = await _analyse_thread(thread_text, f"Demo deal {deal_id}")

        return {
            "deal_id":      deal_id,
            "thread_count": len(emails),
            "emails":       emails,
            "threads":      threads,
            "extracted":    extracted,
            "source":       "demo",
        }

    # ── Real session ──────────────────────────────────────────────────────────
    zoho_token = session.get("access_token", "")
    emails: list[dict] = []

    # ── Step 1: Build deal context (needed for Outlook attribution) ────────
    deal_context: dict = {}
    if zoho_token:
        try:
            from services.deal_context_builder import build_deal_context
            deal_context = await build_deal_context(zoho_token, deal_id)
        except Exception as e:
            logger.warning("email_intel: deal_context fetch failed deal=%s: %s", deal_id, e)

    # ── Step 2: Outlook (PRIMARY source for email communication) ──────────
    # Outlook has the real conversation even when reps don't BCC Zoho.
    # We fetch first and use the attribution engine to ensure only deal-relevant
    # emails are included. Zoho then fills gaps (BCC'd emails).
    ms_tokens_dict: dict | None = None
    ms_token: str | None = None
    internal_domain = ""

    try:
        from routers.ms_auth import get_user_token as _get_ms_tokens
        ms_tokens_dict = await _get_ms_tokens(user_key)
        if ms_tokens_dict:
            ms_token = ms_tokens_dict.get("access_token")
            internal_domain = _get_internal_domain(ms_tokens_dict)
    except Exception as e:
        logger.warning("email_intel: MS token lookup failed: %s", e)

    outlook_emails: list[dict] = []
    if ms_token and deal_context:
        try:
            outlook_emails = await _fetch_and_match_outlook_emails(
                ms_token, deal_context, internal_domain, set()
            )
            emails.extend(outlook_emails)
            logger.info(
                "email_intel: deal=%s outlook_emails_after_match=%d",
                deal_id, len(outlook_emails),
            )
        except Exception as e:
            logger.warning("email_intel: Outlook fetch failed deal=%s: %s", deal_id, e)

    # ── Step 3: Zoho (SUPPLEMENTARY — BCC'd emails + emails that predate Outlook sync) ──
    # Build a set of Outlook message IDs so we can skip exact duplicates.
    outlook_message_ids = {e.get("message_id", "") for e in outlook_emails if e.get("message_id")}

    if zoho_token:
        try:
            zoho_emails = await _fetch_zoho_emails(zoho_token, deal_id)
            for e in zoho_emails:
                mid = e.get("message_id", "")
                # Skip if Outlook already has this (prefer Outlook version — has full body)
                if mid and mid in outlook_message_ids:
                    continue
                e["source"] = "zoho"
                emails.append(e)
            logger.info(
                "email_intel: deal=%s zoho_emails=%d merged_total=%d",
                deal_id, len(zoho_emails), len(emails),
            )
        except Exception as e:
            logger.warning("email_intel: Zoho fetch failed deal=%s: %s", deal_id, e)

    # Sort flat list newest first
    emails.sort(key=lambda e: e.get("date") or e.get("sent_at") or "", reverse=True)

    # Group into threads
    threads = _group_into_threads(emails)

    # ── 4. Zoho write-back: log high-confidence Outlook-only emails as CRM notes ──
    # This closes the BCC gap — even Zoho-only tools will see the conversation.
    # Fire-and-forget: we don't block the response on this.
    crm_gap_emails = [
        e for e in outlook_emails
        if (e.get("_outlook_match") or {}).get("confidence", 0) >= 80
    ]
    if crm_gap_emails and zoho_token:
        try:
            import asyncio as _asyncio
            _asyncio.ensure_future(
                _write_outlook_gap_note(zoho_token, deal_id, crm_gap_emails)
            )
        except Exception:
            pass

    # ── 5. AI analysis — run on the most active thread (most messages) ────
    # Skip DB cache when force_refresh=True so analysis reflects fresh emails
    extracted = None if force_refresh else await _get_db_extraction(deal_id, db)
    if not extracted and threads:
        biggest = max(threads, key=lambda t: t["message_count"])
        thread_text = _build_thread_text(biggest["messages"])
        if thread_text.strip():
            deal_name = deal_context.get("deal_name") or biggest["subject"]
            extracted = await _analyse_thread(thread_text, deal_name)

    # Build source breakdown for the frontend to display
    n_outlook = sum(1 for e in emails if e.get("source") == "outlook")
    n_zoho = sum(1 for e in emails if e.get("source") == "zoho")
    n_crm_gap = sum(
        1 for e in emails
        if e.get("source") == "outlook"
        and (e.get("_outlook_match") or {}).get("in_zoho") is False
    )

    source_summary = {
        "outlook": n_outlook,
        "zoho": n_zoho,
        "crm_gap": n_crm_gap,   # emails the rep sent but never BCC'd to CRM
        "outlook_connected": ms_token is not None,
    }

    response = {
        "deal_id":        deal_id,
        "thread_count":   len(emails),
        "emails":         emails,
        "threads":        threads,
        "extracted":      extracted,
        "source":         "outlook+zoho" if (n_outlook and n_zoho) else ("outlook" if n_outlook else ("zoho" if n_zoho else "empty")),
        "source_summary": source_summary,
    }

    # ── Persist AI extraction to DB (write-back so next load skips Groq) ─────
    if extracted and db is not None:
        try:
            from database.models import EmailExtraction
            from sqlalchemy import select as _select
            # Upsert: delete old row for this deal then insert new one
            existing = (await db.execute(
                _select(EmailExtraction)
                .where(EmailExtraction.deal_zoho_id == deal_id)
                .order_by(EmailExtraction.created_at.desc())
                .limit(1)
            )).scalars().first()
            if existing is None:
                import uuid as _uuid
                new_row = EmailExtraction(
                    id=str(_uuid.uuid4()),
                    deal_zoho_id=deal_id,
                    next_step=extracted.get("next_step"),
                    commitments=[c if isinstance(c, str) else str(c) for c in (extracted.get("commitments") or [])],
                    open_questions=extracted.get("open_questions") or [],
                    sentiment=extracted.get("sentiment"),
                )
                db.add(new_row)
                await db.commit()
                logger.debug("email_intel: saved AI extraction to DB for deal=%s", deal_id)
            else:
                # Update existing row so stale analysis doesn't persist
                existing.next_step = extracted.get("next_step")
                existing.commitments = [c if isinstance(c, str) else str(c) for c in (extracted.get("commitments") or [])]
                existing.open_questions = extracted.get("open_questions") or []
                existing.sentiment = extracted.get("sentiment")
                await db.commit()
                logger.debug("email_intel: updated AI extraction in DB for deal=%s", deal_id)
        except Exception as _dbe:
            logger.debug("email_intel: DB write-back failed deal=%s: %s", deal_id, _dbe)

    # ── Cache the full response in Redis (15 min TTL) ─────────────────────────
    try:
        from services.cache import cache_set, cache_key as _ck, TTL_EMAIL_INTEL
        _cache_key = _ck("email_intel", user_key, deal_id)
        await cache_set(_cache_key, response, ttl=TTL_EMAIL_INTEL)
        logger.debug("email_intel: cached response user=%s deal=%s ttl=900", user_key, deal_id)
    except Exception as _ce:
        logger.debug("email_intel: cache_set error: %s", _ce)

    return response


@router.post("/analyse/{deal_id}")
async def analyse_thread(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Force re-analyse email threads for a deal.
    Fetches fresh emails, joins all threads, runs AI analysis.
    """
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"deal_id": deal_id, "extracted": None, "message": "Demo mode"}

    zoho_token = session.get("access_token", "")
    emails: list[dict] = []

    if zoho_token:
        try:
            emails = await _fetch_zoho_emails(zoho_token, deal_id)
        except Exception as e:
            logger.warning("analyse: Zoho fetch failed: %s", e)

    if not emails:
        raise HTTPException(status_code=404, detail="No emails found for this deal to analyse")

    threads = _group_into_threads(emails)
    # Build combined text from ALL threads for comprehensive analysis
    all_text_parts = []
    for t in threads:
        all_text_parts.append(f"=== Thread: {t['subject']} ===\n{_build_thread_text(t['messages'])}")
    combined = "\n\n".join(all_text_parts)

    # Get deal name for context
    deal_name = deal_id
    if zoho_token:
        try:
            from services.zoho_client import fetch_single_deal
            deal = await fetch_single_deal(zoho_token, deal_id)
            if deal:
                deal_name = deal.get("name", deal_id)
        except Exception:
            pass

    extracted = await _analyse_thread(combined, deal_name)
    return {"deal_id": deal_id, "extracted": extracted, "thread_count": len(threads)}


# ── Sync endpoint ─────────────────────────────────────────────────────────────

class SyncEmailsPayload(BaseModel):
    deal_id: str
    contact_emails: list[str] = []


@router.post("/sync")
async def sync_emails(
    payload: SyncEmailsPayload,
    authorization: str = Header(...),
):
    """Force a fresh pull from Zoho + Outlook for a deal."""
    session = _decode_session(authorization)

    if _is_demo(session):
        return {"deal_id": payload.deal_id, "threads_found": 0, "message": "Demo mode — sync not available"}

    zoho_token = session.get("access_token", "")
    user_key = _user_key(session)
    emails: list[dict] = []

    # Build deal context for proper attribution
    deal_context: dict = {}
    if zoho_token:
        try:
            from services.deal_context_builder import build_deal_context
            deal_context = await build_deal_context(zoho_token, payload.deal_id)
        except Exception:
            pass

    # Outlook first (primary)
    ms_token = await _get_ms_token(user_key)
    if ms_token and deal_context:
        try:
            internal_domain = _get_internal_domain(
                await __import__("routers.ms_auth", fromlist=["get_user_token"]).get_user_token(user_key)
            )
            outlook_emails = await _fetch_and_match_outlook_emails(
                ms_token, deal_context, internal_domain, set()
            )
            emails.extend(outlook_emails)
        except Exception as e:
            logger.warning("sync: Outlook failed deal=%s: %s", payload.deal_id, e)

    # Zoho supplementary
    outlook_ids = {e.get("message_id", "") for e in emails if e.get("message_id")}
    if zoho_token:
        try:
            for e in await _fetch_zoho_emails(zoho_token, payload.deal_id):
                if not (e.get("message_id") and e["message_id"] in outlook_ids):
                    e["source"] = "zoho"
                    emails.append(e)
        except Exception as e:
            logger.warning("sync: Zoho failed deal=%s: %s", payload.deal_id, e)

    emails.sort(key=lambda e: e.get("date") or "", reverse=True)

    return {
        "deal_id":       payload.deal_id,
        "threads_found": len(emails),
        "emails":        emails,
        "threads":       _group_into_threads(emails),
    }


# ── Debug endpoint ────────────────────────────────────────────────────────────

@router.get("/debug/{deal_id}")
async def debug_email_fetch(
    deal_id: str,
    authorization: str = Header(...),
):
    """
    Debug endpoint — dumps the raw Zoho email list response and the first email's
    raw body response so you can see exactly what the API is returning.
    GET /email-intel/debug/{deal_id}
    """
    import httpx as _httpx
    session = _decode_session(authorization)
    if _is_demo(session):
        return {"error": "not available in demo mode"}

    zoho_token = session.get("access_token", "")
    if not zoho_token:
        return {"error": "no zoho token"}

    from services.zoho_client import ZOHO_API_V8, ZOHO_API_BASE
    headers = {"Authorization": f"Zoho-oauthtoken {zoho_token}"}
    result: dict = {"deal_id": deal_id}

    # Step 1: raw email list (v8)
    async with _httpx.AsyncClient(timeout=15) as client:
        list_resp = await client.get(
            f"{ZOHO_API_V8}/Deals/{deal_id}/Emails",
            headers=headers,
        )
    result["list_status"] = list_resp.status_code
    result["list_url"] = f"{ZOHO_API_V8}/Deals/{deal_id}/Emails"

    if list_resp.status_code == 200:
        list_data = list_resp.json()
        emails = list_data.get("data", list_data.get("Emails", []))
        result["email_count"] = len(emails)
        result["first_email_keys"] = list(emails[0].keys()) if emails else []
        result["first_email_metadata"] = emails[0] if emails else None

        # Step 2: raw body for first email
        if emails:
            first = emails[0]
            message_id = first.get("message_id") or first.get("id")
            owner = first.get("owner") or {}
            user_id = owner.get("id") if isinstance(owner, dict) else None
            result["message_id_used"] = message_id
            result["user_id_used"] = user_id

            body_url = f"{ZOHO_API_V8}/Deals/{deal_id}/Emails/{message_id}"
            async with _httpx.AsyncClient(timeout=10) as client:
                body_resp = await client.get(
                    body_url,
                    headers=headers,
                    params={"user_id": user_id} if user_id else {},
                )
            result["body_status"] = body_resp.status_code
            result["body_url"] = body_url
            if body_resp.status_code == 200:
                body_data = body_resp.json()
                result["body_response_keys"] = list(body_data.keys())
                # Check if content exists
                content = (
                    body_data.get("content")
                    or body_data.get("html_body")
                    or (body_data.get("data") or [{}])[0].get("content") if isinstance(body_data.get("data"), list) else None
                )
                result["content_found"] = bool(content)
                result["content_length"] = len(content) if content else 0
                result["content_preview"] = content[:500] if content else None
                result["raw_body_response"] = str(body_data)[:2000]
            else:
                result["body_error"] = body_resp.text[:500]
    else:
        result["list_error"] = list_resp.text[:500]

    return result
