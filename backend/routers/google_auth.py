"""
Google OAuth2 router — Connect / Callback / Status / Disconnect.
Tokens stored in-memory keyed by user email from the Zoho session.
State → session_token map bridges the stateless OAuth callback back to the user.
"""

import os
import secrets
import base64
import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

from services.google_calendar import get_authorization_url, exchange_code

router = APIRouter()

# state_token → raw session token (set at /connect, consumed at /callback)
_pending_states: dict[str, str] = {}

# user_email → google tokens (persistent within process lifetime)
_user_tokens: dict[str, dict] = {}


def _google_client_id() -> str | None:
    return os.getenv("GOOGLE_CLIENT_ID")


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
    """Stable key to identify a user across requests."""
    return session.get("email") or session.get("user_id") or "default"


@router.post("/connect")
async def connect_google(authorization: str = Header(...)):
    """Start Google OAuth2 flow. Returns the authorization URL."""
    session = _decode_session(authorization)
    if not _google_client_id():
        raise HTTPException(status_code=501, detail="Google OAuth not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
    state = secrets.token_urlsafe(16)
    # Remember which user initiated this flow
    _pending_states[state] = _user_key(session)
    auth_url = await get_authorization_url(state=state)
    return {"auth_url": auth_url, "state": state}


@router.get("/callback")
async def google_callback(code: str, state: str):
    """Handle Google OAuth2 callback — exchanges code for tokens."""
    if not _google_client_id():
        raise HTTPException(status_code=501, detail="Google OAuth not configured.")
    tokens = await exchange_code(code)
    # Link tokens back to the user who started the flow
    user_key = _pending_states.pop(state, "default")
    _user_tokens[user_key] = tokens
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
    return RedirectResponse(url=f"{frontend_url}/settings?google=connected")


@router.get("/status")
async def google_status(authorization: str = Header(...)):
    """Check if a Google account is connected for this session."""
    session = _decode_session(authorization)
    if not _google_client_id():
        return {"connected": False, "message": "Google not configured"}
    user_key = _user_key(session)
    tokens = _user_tokens.get(user_key)
    if tokens:
        return {"connected": True, "message": "Google account connected"}
    return {"connected": False, "message": "No Google account connected yet"}


@router.delete("/disconnect")
async def disconnect_google(authorization: str = Header(...)):
    """Remove stored Google tokens."""
    session = _decode_session(authorization)
    user_key = _user_key(session)
    _user_tokens.pop(user_key, None)
    return {"disconnected": True}
