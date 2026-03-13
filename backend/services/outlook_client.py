"""
Microsoft Outlook / Graph API integration.
Replaces gmail_client.py — same interface, Microsoft Graph endpoints.

Degrades gracefully (returns []) when MICROSOFT_CLIENT_ID is not set.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID")
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


async def sync_emails_for_deal(
    access_token: str,
    deal_id: str,
    contact_emails: list[str],
) -> list[dict[str, Any]]:
    """
    Fetch Outlook messages matching the given contact emails via Microsoft Graph.
    Returns [] if Microsoft OAuth is not configured or token is absent.
    """
    if not MICROSOFT_CLIENT_ID:
        logger.warning("outlook_client [deal=%s]: MICROSOFT_CLIENT_ID not set — Outlook fetch disabled", deal_id)
        return []
    if not access_token:
        logger.warning("outlook_client [deal=%s]: no access_token — skipping Graph call", deal_id)
        return []

    import httpx

    # Sanitise contact_emails — ensure every entry is a plain string
    safe_emails = []
    for e in contact_emails:
        if isinstance(e, dict):
            e = e.get("address") or e.get("email") or ""
        if isinstance(e, str) and e.strip():
            safe_emails.append(e.strip().lower())

    logger.info(
        "outlook_client [deal=%s]: input contact_emails=%s → safe_emails=%s",
        deal_id, contact_emails, safe_emails,
    )

    # Graph KQL: space between terms = AND, so "from:x to:x" means both must be true.
    # We want emails where the contact appears as sender OR recipient — use explicit OR.
    # Format: (from:a@b.com OR to:a@b.com) OR (from:c@d.com OR to:c@d.com)
    search_query = " OR ".join(
        f"(from:{e} OR to:{e})" for e in safe_emails
    ) if safe_emails else None

    # NOTE: Graph API rejects $search combined with $orderby — use one or the other.
    params: dict[str, Any] = {
        "$top": 25,
        "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead",
    }
    if search_query:
        params["$search"] = f'"{search_query}"'
        logger.info("outlook_client [deal=%s]: $search=%s", deal_id, params["$search"])
    else:
        params["$orderby"] = "receivedDateTime desc"
        logger.info("outlook_client [deal=%s]: no contact emails — fetching last 25 messages unfiltered", deal_id)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GRAPH_API_BASE}/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
                timeout=10,
            )
    except Exception as e:
        logger.warning("outlook_client [deal=%s]: Graph API request EXCEPTION: %s", deal_id, e)
        return []

    logger.info(
        "outlook_client [deal=%s]: Graph API status=%d body_preview=%s",
        deal_id, resp.status_code, resp.text[:600],
    )

    if resp.status_code == 401:
        logger.warning("outlook_client [deal=%s]: 401 UNAUTHORIZED — token expired or revoked", deal_id)
        return []
    if resp.status_code == 403:
        logger.warning("outlook_client [deal=%s]: 403 FORBIDDEN — token is missing Mail.Read scope, user must re-auth", deal_id)
        return []
    if resp.status_code == 400:
        logger.warning("outlook_client [deal=%s]: 400 BAD REQUEST — search query rejected. body=%s", deal_id, resp.text[:400])
        return []
    if resp.status_code != 200:
        logger.warning("outlook_client [deal=%s]: unexpected status=%d body=%s", deal_id, resp.status_code, resp.text[:400])
        return []

    messages = resp.json().get("value", [])
    logger.info("outlook_client [deal=%s]: Graph returned %d messages", deal_id, len(messages))
    return messages


async def get_messages_for_deal(
    access_token: str,
    contact_emails: list[str],
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Return normalised email dicts for a deal's contacts, suitable for the
    email timeline UI.  Shape matches what email_intel router expects.
    """
    if not access_token:
        return []

    raw_messages = await sync_emails_for_deal(access_token, "", contact_emails)

    results: list[dict[str, Any]] = []
    for msg in raw_messages[:max_results]:
        sender_addr = (msg.get("from") or {}).get("emailAddress", {}).get("address", "")
        sender_name = (msg.get("from") or {}).get("emailAddress", {}).get("name", sender_addr)
        user_email = os.getenv("OUTLOOK_USER_EMAIL", "").lower()

        direction = "received" if sender_addr.lower() != user_email else "sent"

        results.append({
            "subject": msg.get("subject", "(no subject)"),
            "from": f"{sender_name} <{sender_addr}>" if sender_name != sender_addr else sender_addr,
            "direction": direction,
            "sent_at": msg.get("receivedDateTime", ""),
            "body_preview": msg.get("bodyPreview", ""),
            "message_id": msg.get("id", ""),
            "is_read": msg.get("isRead", True),
        })

    return results


async def get_upcoming_meetings(access_token: str) -> list[dict[str, Any]]:
    """
    Return calendar events for the next 24 hours from Outlook Calendar.
    Returns [] if token is absent.
    """
    if not access_token:
        return []

    import httpx
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    time_end = now + timedelta(hours=24)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_API_BASE}/me/calendarView",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Prefer": 'outlook.timezone="UTC"',
            },
            params={
                "startDateTime": now.isoformat(),
                "endDateTime": time_end.isoformat(),
                "$select": "id,subject,start,end,attendees,bodyPreview,webLink",
                "$orderby": "start/dateTime",
                "$top": 10,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("value", [])


def match_attendees_to_deals(
    events: list[dict[str, Any]],
    zoho_contacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Cross-reference Outlook event attendee emails with Zoho contact emails.
    Returns events enriched with deal_id where a match is found.
    """
    contact_email_to_deal: dict[str, str] = {}
    for contact in zoho_contacts:
        email = contact.get("Email", "")
        deal_id = contact.get("deal_id", "")
        if email and deal_id:
            contact_email_to_deal[email.lower()] = deal_id

    enriched: list[dict[str, Any]] = []
    for event in events:
        attendees = event.get("attendees", [])
        matched_deal_id: str | None = None
        for attendee in attendees:
            email = (attendee.get("emailAddress") or {}).get("address", "").lower()
            if email in contact_email_to_deal:
                matched_deal_id = contact_email_to_deal[email]
                break
        enriched.append({**event, "deal_id": matched_deal_id})

    return enriched
