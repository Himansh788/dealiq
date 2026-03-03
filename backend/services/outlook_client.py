"""
Microsoft Outlook / Graph API integration.
Replaces gmail_client.py — same interface, Microsoft Graph endpoints.

Degrades gracefully (returns []) when MICROSOFT_CLIENT_ID is not set.
"""

import os
from typing import Any

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
    if not MICROSOFT_CLIENT_ID or not access_token:
        return []

    import httpx

    # Use $search with email addresses — more reliable than OData filter for recipients
    # Graph search syntax: "from:email OR to:email"
    search_query = " OR ".join(
        f"from:{e} to:{e}" for e in contact_emails
    ) if contact_emails else None

    params: dict[str, Any] = {
        "$top": 25,
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,isRead",
    }
    if search_query:
        params["$search"] = f'"{search_query}"'

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GRAPH_API_BASE}/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=10,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("value", [])


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
