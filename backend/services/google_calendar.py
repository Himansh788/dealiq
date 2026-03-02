"""
Google Calendar integration — stubbed until GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are set.
All functions degrade gracefully (return empty / raise 501) when credentials are absent.
"""

import os
from typing import Any

from fastapi import HTTPException

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
]

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def _client_id() -> str | None:
    return os.getenv("GOOGLE_CLIENT_ID")

def _client_secret() -> str | None:
    return os.getenv("GOOGLE_CLIENT_SECRET")

def _redirect_uri() -> str:
    return os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")


def _require_credentials() -> None:
    if not _client_id() or not _client_secret():
        raise HTTPException(
            status_code=501,
            detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )


async def get_authorization_url(state: str) -> str:
    """Return the Google OAuth2 URL for calendar + gmail read scopes."""
    _require_credentials()
    import urllib.parse

    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an authorization code for access + refresh tokens."""
    _require_credentials()
    import httpx

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_upcoming_meetings(access_token: str) -> list[dict[str, Any]]:
    """Return calendar events for the next 24 hours with external attendees."""
    if not _client_id():
        return []

    import httpx
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    time_max = now + timedelta(hours=24)

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{GOOGLE_CALENDAR_API}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": now.isoformat(),
                "timeMax": time_max.isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("items", [])


async def match_attendees_to_deals(
    events: list[dict[str, Any]],
    zoho_contacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Cross-reference event attendee emails with Zoho contact emails.
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
            email = attendee.get("email", "").lower()
            if email in contact_email_to_deal:
                matched_deal_id = contact_email_to_deal[email]
                break
        enriched.append({**event, "deal_id": matched_deal_id})

    return enriched
