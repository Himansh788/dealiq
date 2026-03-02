"""
Gmail integration — stubbed until GOOGLE_CLIENT_ID is set.
Returns empty results gracefully when credentials are absent.
"""

import os
from typing import Any

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


async def sync_emails_for_deal(
    access_token: str,
    deal_id: str,
    contact_emails: list[str],
) -> list[dict[str, Any]]:
    """
    Fetch Gmail threads matching the given contact emails.
    Returns [] if Google is not configured.
    """
    if not GOOGLE_CLIENT_ID:
        return []

    import httpx

    query = " OR ".join(f"from:{e} OR to:{e}" for e in contact_emails)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/users/me/threads",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"q": query, "maxResults": 20},
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("threads", [])


async def get_thread_summary(
    access_token: str,
    thread_id: str,
) -> dict[str, Any]:
    """
    Return a summary dict for a Gmail thread.
    Returns empty dict if Google is not configured.
    """
    if not GOOGLE_CLIENT_ID:
        return {}

    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GMAIL_API_BASE}/users/me/threads/{thread_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        messages = data.get("messages", [])
        if not messages:
            return {}

        def _header(msg: dict, name: str) -> str:
            for h in msg.get("payload", {}).get("headers", []):
                if h.get("name", "").lower() == name.lower():
                    return h.get("value", "")
            return ""

        last_msg = messages[-1]
        return {
            "thread_id": thread_id,
            "total_count": len(messages),
            "last_sender": _header(last_msg, "From"),
            "last_date": _header(last_msg, "Date"),
            "subject": _header(messages[0], "Subject"),
            "messages": [
                {
                    "id": m.get("id"),
                    "from": _header(m, "From"),
                    "date": _header(m, "Date"),
                }
                for m in messages
            ],
        }
