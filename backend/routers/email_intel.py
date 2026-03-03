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


def _get_ms_token(user_key: str) -> str | None:
    try:
        from routers.ms_auth import get_user_token
        tokens = get_user_token(user_key)
        return tokens.get("access_token") if tokens else None
    except Exception:
        return None


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


def _normalise_zoho_email(raw: dict) -> dict:
    """
    Map a raw Zoho email (v2 or v8) to the unified frontend shape.
    Zoho fields: subject, from, to, sent_time, direction, sent (bool),
                 content (plain), html_content, message_id, thread_id
    """
    direction_raw = (raw.get("direction") or "").lower()
    sent_flag = raw.get("sent")
    if direction_raw in ("outgoing", "sent", "outbound"):
        status = "sent"
    elif direction_raw in ("incoming", "received", "inbound"):
        status = "delivered"
    elif isinstance(sent_flag, bool):
        status = "sent" if sent_flag else "delivered"
    else:
        status = "delivered"

    # Prefer the enriched full-body fields set by _fetch_emails_for_record
    body_full = raw.get("body_full") or raw.get("content") or raw.get("description") or raw.get("summary") or ""
    body_preview = raw.get("body_preview") or raw.get("snippet") or body_full[:300]
    snippet = body_preview[:300].strip() if body_preview else ""

    return {
        "subject":      raw.get("subject") or raw.get("Subject") or "(no subject)",
        "from":         _addr(raw.get("from") or raw.get("From") or raw.get("sender")),
        "to":           _addr_list(raw.get("to") or raw.get("To") or []),
        "date":         raw.get("sent_time") or raw.get("date") or raw.get("Created_Time") or "",
        "snippet":      snippet,
        "body_preview": snippet,
        "body_full":    body_full,
        "status":       status,
        "direction":    status,
        "sent_at":      raw.get("sent_time") or raw.get("date") or "",
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

_ANALYSIS_SYSTEM = """You are a sales intelligence AI. Analyse this email thread for a B2B sales deal.
Return ONLY valid JSON in this exact shape:
{
  "summary": "2-3 sentence plain-English summary of what was discussed",
  "next_step": "single most important action the rep should take now",
  "commitments": ["list of promises made by either party"],
  "open_questions": ["unanswered questions or blockers"],
  "sentiment": "positive|neutral|negative|mixed",
  "sentiment_progression": "improving|stable|declining",
  "key_topics": ["price", "legal", "timeline", ...],
  "deadlines": ["any dates or deadlines mentioned"]
}"""


async def _analyse_thread(thread_text: str, deal_name: str) -> dict | None:
    """Send combined thread text to Groq and return structured analysis."""
    try:
        from services.ai_router_ask import generate_structured_analysis
        prompt = f"Deal: {deal_name}\n\n--- EMAIL THREAD ---\n{thread_text[:6000]}"
        return await generate_structured_analysis(_ANALYSIS_SYSTEM, prompt, max_tokens=800)
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


async def _fetch_outlook_emails(
    ms_token: str, zoho_token: str, deal_id: str, existing: list[dict]
) -> list[dict]:
    contact_emails: list[str] = []
    if zoho_token:
        try:
            from services.zoho_client import get_contacts_for_deal
            contacts = await get_contacts_for_deal(zoho_token, deal_id)
            contact_emails = [c["email"] for c in contacts if c.get("email")]
        except Exception:
            pass

    from services.outlook_client import get_messages_for_deal
    raw_outlook = await get_messages_for_deal(ms_token, contact_emails)

    existing_keys = {(e["subject"], (e.get("date") or "")[:10]) for e in existing}
    added = []
    for msg in raw_outlook:
        n = _normalise_outlook_email(msg)
        key = (n["subject"], n["date"][:10])
        if key not in existing_keys:
            added.append(n)
            existing_keys.add(key)
    return added


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/threads/{deal_id}")
async def get_email_thread(
    deal_id: str,
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Return full email threads with bodies for a deal.
    Flat list + thread-grouped list returned together.
    AI analysis runs inline on the most active thread.
    """
    session = _decode_session(authorization)

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

    # 1. Zoho CRM (primary — v8 with full bodies)
    if zoho_token:
        try:
            emails = await _fetch_zoho_emails(zoho_token, deal_id)
            logger.info("email_intel: deal=%s zoho_emails=%d (with bodies)", deal_id, len(emails))
        except Exception as e:
            logger.warning("email_intel: Zoho fetch failed deal=%s: %s", deal_id, e)

    # 2. Outlook supplementary
    ms_token = _get_ms_token(_user_key(session))
    if ms_token:
        try:
            outlook_emails = await _fetch_outlook_emails(ms_token, zoho_token, deal_id, emails)
            emails.extend(outlook_emails)
            logger.info("email_intel: deal=%s after outlook merge=%d", deal_id, len(emails))
        except Exception as e:
            logger.warning("email_intel: Outlook merge failed deal=%s: %s", deal_id, e)

    # Sort flat list newest first
    emails.sort(key=lambda e: e.get("date") or e.get("sent_at") or "", reverse=True)

    # Group into threads
    threads = _group_into_threads(emails)

    # 3. AI analysis — run on the most active thread (most messages)
    extracted = await _get_db_extraction(deal_id, db)
    if not extracted and threads:
        biggest = max(threads, key=lambda t: t["message_count"])
        thread_text = _build_thread_text(biggest["messages"])
        if thread_text.strip():
            deal_name = biggest["subject"]
            extracted = await _analyse_thread(thread_text, deal_name)

    return {
        "deal_id":      deal_id,
        "thread_count": len(emails),
        "emails":       emails,
        "threads":      threads,
        "extracted":    extracted,
        "source":       "zoho" if emails else "empty",
    }


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
    emails: list[dict] = []

    if zoho_token:
        try:
            emails = await _fetch_zoho_emails(zoho_token, payload.deal_id)
        except Exception as e:
            logger.warning("sync: Zoho failed deal=%s: %s", payload.deal_id, e)

    ms_token = _get_ms_token(_user_key(session))
    if ms_token:
        try:
            outlook_emails = await _fetch_outlook_emails(ms_token, zoho_token, payload.deal_id, emails)
            emails.extend(outlook_emails)
        except Exception as e:
            logger.warning("sync: Outlook failed deal=%s: %s", payload.deal_id, e)

    emails.sort(key=lambda e: e.get("date") or "", reverse=True)

    return {
        "deal_id":       payload.deal_id,
        "threads_found": len(emails),
        "emails":        emails,
        "threads":       _group_into_threads(emails),
    }
