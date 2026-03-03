"""
Microsoft OAuth2 router — Connect / Callback / Status / Disconnect.
Uses the Microsoft identity platform (login.microsoftonline.com).

Required env vars:
  MICROSOFT_CLIENT_ID      — Azure App Registration client ID
  MICROSOFT_CLIENT_SECRET  — Azure App Registration client secret
  MICROSOFT_TENANT_ID      — Tenant ID or "common" for multi-tenant
  MICROSOFT_REDIRECT_URI   — e.g. http://localhost:8000/ms-auth/callback

Tokens stored in-memory keyed by user email from the Zoho session.
"""

import os
import secrets
import base64
import json
import urllib.parse

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter()

# state_token → user_key (set at /connect, consumed at /callback)
_pending_states: dict[str, str] = {}

# user_key → microsoft tokens
_user_tokens: dict[str, dict] = {}

MS_SCOPES = [
    "offline_access",
    "Mail.Read",
    "Calendars.Read",
    "User.Read",
]


def _client_id() -> str | None:
    return os.getenv("MICROSOFT_CLIENT_ID")


def _client_secret() -> str | None:
    return os.getenv("MICROSOFT_CLIENT_SECRET")


def _tenant_id() -> str:
    return os.getenv("MICROSOFT_TENANT_ID", "common")


def _redirect_uri() -> str:
    return os.getenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/ms-auth/callback")


def _auth_base() -> str:
    return f"https://login.microsoftonline.com/{_tenant_id()}/oauth2/v2.0"


def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    if len(token) > 10:
        return {"access_token": token, "email": "user@local"}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _user_key(session: dict) -> str:
    return session.get("email") or session.get("user_id") or "default"


def get_user_token(user_key: str) -> dict | None:
    """Called by other services to retrieve the stored MS token for a user."""
    return _user_tokens.get(user_key)


@router.post("/connect")
async def connect_outlook(authorization: str = Header(...)):
    """Start Microsoft OAuth2 flow. Returns the authorization URL."""
    if not _client_id():
        raise HTTPException(
            status_code=501,
            detail="Microsoft OAuth not configured. Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID.",
        )
    session = _decode_session(authorization)
    state = secrets.token_urlsafe(16)
    _pending_states[state] = _user_key(session)

    params = {
        "client_id": _client_id(),
        "response_type": "code",
        "redirect_uri": _redirect_uri(),
        "scope": " ".join(MS_SCOPES),
        "state": state,
        "response_mode": "query",
    }
    auth_url = f"{_auth_base()}/authorize?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
async def ms_callback(code: str, state: str):
    """Handle Microsoft OAuth2 callback — exchanges code for tokens."""
    if not _client_id():
        raise HTTPException(status_code=501, detail="Microsoft OAuth not configured.")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_auth_base()}/token",
            data={
                "client_id": _client_id(),
                "client_secret": _client_secret(),
                "code": code,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
                "scope": " ".join(MS_SCOPES),
            },
        )
        resp.raise_for_status()
        tokens = resp.json()

    user_key = _pending_states.pop(state, "default")

    # Fetch the user's email from Graph to store alongside tokens
    try:
        me_resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if me_resp.status_code == 200:
            tokens["ms_email"] = me_resp.json().get("mail") or me_resp.json().get("userPrincipalName")
    except Exception:
        pass

    _user_tokens[user_key] = tokens

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
    return RedirectResponse(url=f"{frontend_url}/settings?outlook=connected")


@router.get("/status")
async def outlook_status(authorization: str = Header(...)):
    """Check if an Outlook account is connected for this session."""
    session = _decode_session(authorization)
    if not _client_id():
        return {"connected": False, "message": "Microsoft OAuth not configured"}
    user_key = _user_key(session)
    tokens = _user_tokens.get(user_key)
    if tokens:
        email = tokens.get("ms_email", "")
        return {
            "connected": True,
            "message": "Outlook connected",
            "email": email,
        }
    return {"connected": False, "message": "No Outlook account connected yet"}


@router.delete("/disconnect")
async def disconnect_outlook(authorization: str = Header(...)):
    """Remove stored Microsoft tokens."""
    session = _decode_session(authorization)
    user_key = _user_key(session)
    _user_tokens.pop(user_key, None)
    return {"disconnected": True}
