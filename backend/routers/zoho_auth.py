"""
Zoho mid-session connect router.

Mirrors `ms_auth.py`. Adds a secondary OAuth flow so a user who signed in via
Outlook (or any non-Zoho primary) can connect Zoho CRM from
Settings → Integrations and keep their existing session.

Endpoints (all mounted at /zoho-auth):
  POST   /connect      — start OAuth, return Zoho consent URL
  GET    /status       — { connected, zoho_email }
  DELETE /disconnect   — drop stored tokens for this user

Callback is shared with `auth.py:callback` — that handler checks the state
token against `_secondary_states` here to route the response correctly.

Tokens are persisted in the `zoho_tokens` table (DB-backed) with an in-memory
L1 cache. Auto-refresh kicks in when < 5 min remain on the access token.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException

from services.zoho_client import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_current_user as zoho_get_current_user,
    refresh_access_token as zoho_refresh_access_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── state → user_key map (short-lived; only during OAuth flow) ─────────────
# Read by routers/auth.py:callback() to detect mid-session connect flows.
_secondary_states: dict[str, str] = {}

# ── L1 in-memory cache (user_key → token dict) ────────────────────────────
_token_cache: dict[str, dict] = {}

# Refresh access tokens when < 5 min remain
_TOKEN_REFRESH_BUFFER_SECONDS = 300

# Refresh attempts run under a lock per user_key to avoid duplicate refreshes
_refresh_locks: dict[str, asyncio.Lock] = {}


# ── session decode (matches the pattern in deals.py / ms_auth.py) ─────────

def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        return json.loads(base64.b64decode(token).decode())
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Invalid session token")


def _user_key(session: dict) -> str:
    return session.get("email") or session.get("user_id") or "default"


# ── token expiry helpers ──────────────────────────────────────────────────

def _expires_at_from_response(token_resp: dict) -> datetime:
    """Zoho returns expires_in in seconds (typically 3600)."""
    expires_in = int(token_resp.get("expires_in", 3600))
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in)


def _is_expired(tokens: dict) -> bool:
    expires_at = tokens.get("expires_at")
    if not expires_at:
        return False
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except Exception:
            return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) >= (
        expires_at - timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS)
    )


# ── DB persistence ────────────────────────────────────────────────────────

async def _save_token_to_db(user_key: str, tokens: dict) -> None:
    """Upsert into zoho_tokens. No-op when DB is unavailable."""
    try:
        from database.connection import get_db
        from database.models import ZohoToken
        from sqlalchemy import select

        async for db in get_db():
            if db is None:
                return
            expires_at = tokens.get("expires_at")
            if isinstance(expires_at, str):
                try:
                    expires_at = datetime.fromisoformat(expires_at)
                except Exception:
                    expires_at = None

            row = (
                await db.execute(select(ZohoToken).where(ZohoToken.user_key == user_key))
            ).scalars().first()

            if row:
                row.access_token = tokens.get("access_token", "")
                # Zoho may not return a refresh_token on every refresh — keep old.
                row.refresh_token = tokens.get("refresh_token") or row.refresh_token
                row.zoho_email = tokens.get("zoho_email") or row.zoho_email
                row.zoho_user_id = tokens.get("zoho_user_id") or row.zoho_user_id
                row.expires_at = expires_at
                row.scopes = tokens.get("scope") or row.scopes
            else:
                db.add(ZohoToken(
                    user_key=user_key,
                    access_token=tokens.get("access_token", ""),
                    refresh_token=tokens.get("refresh_token"),
                    zoho_email=tokens.get("zoho_email"),
                    zoho_user_id=tokens.get("zoho_user_id"),
                    expires_at=expires_at,
                    scopes=tokens.get("scope"),
                ))
            await db.commit()
    except Exception as e:
        logger.warning("zoho_auth: DB save failed user_key=%s: %s", user_key, e)


async def _load_token_from_db(user_key: str) -> dict | None:
    try:
        from database.connection import get_db
        from database.models import ZohoToken
        from sqlalchemy import select

        async for db in get_db():
            if db is None:
                return None
            row = (
                await db.execute(select(ZohoToken).where(ZohoToken.user_key == user_key))
            ).scalars().first()
            if not row:
                return None
            expires_at_str = row.expires_at.isoformat() if row.expires_at else None
            return {
                "access_token": row.access_token,
                "refresh_token": row.refresh_token,
                "zoho_email": row.zoho_email,
                "zoho_user_id": row.zoho_user_id,
                "expires_at": expires_at_str,
                "scope": row.scopes or "",
            }
    except Exception as e:
        logger.warning("zoho_auth: DB load failed user_key=%s: %s", user_key, e)
    return None


async def _delete_token_from_db(user_key: str) -> None:
    try:
        from database.connection import get_db
        from database.models import ZohoToken
        from sqlalchemy import select

        async for db in get_db():
            if db is None:
                return
            row = (
                await db.execute(select(ZohoToken).where(ZohoToken.user_key == user_key))
            ).scalars().first()
            if row:
                await db.delete(row)
                await db.commit()
    except Exception as e:
        logger.warning("zoho_auth: DB delete failed user_key=%s: %s", user_key, e)


# ── token refresh ─────────────────────────────────────────────────────────

async def _refresh(user_key: str, tokens: dict) -> dict | None:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return None
    lock = _refresh_locks.setdefault(user_key, asyncio.Lock())
    async with lock:
        # Double-check after acquiring the lock — another coroutine may have
        # refreshed in the meantime.
        cached = _token_cache.get(user_key)
        if cached and not _is_expired(cached):
            return cached
        try:
            result = await zoho_refresh_access_token(refresh_token)
        except Exception as e:
            logger.warning("zoho_auth: refresh failed user_key=%s: %s", user_key, e)
            return None
        new_access = result.get("access_token")
        if not new_access:
            logger.warning("zoho_auth: refresh returned no access_token user_key=%s", user_key)
            return None
        updated = {
            **tokens,
            "access_token": new_access,
            "expires_at": _expires_at_from_response(result).isoformat(),
        }
        # Zoho only sends a new refresh_token on first OAuth — keep the old one.
        if result.get("refresh_token"):
            updated["refresh_token"] = result["refresh_token"]
        _token_cache[user_key] = updated
        await _save_token_to_db(user_key, updated)
        logger.info("zoho_auth: refreshed token user_key=%s", user_key)
        return updated


# ── public helper (called by deals.py and other routers) ──────────────────

async def get_user_zoho_token(user_key: str) -> dict | None:
    """
    Return a valid Zoho token dict for this user, or None if not connected.
    Walks L1 cache → DB; auto-refreshes if the access_token is expiring.
    """
    tokens = _token_cache.get(user_key)
    if not tokens:
        tokens = await _load_token_from_db(user_key)
        if tokens:
            _token_cache[user_key] = tokens
    if not tokens:
        return None
    if _is_expired(tokens):
        refreshed = await _refresh(user_key, tokens)
        return refreshed or tokens  # fall back to stale token; caller can retry
    return tokens


async def resolve_zoho_access_token(session: dict) -> str | None:
    """
    Best-effort accessor used by deals.py: return whichever Zoho access_token
    is appropriate for this session.

    Priority:
      1. If the session is Zoho-primary, use the token embedded in the session.
      2. Otherwise look up a stored Zoho token keyed by the session user.
      3. Return None when no Zoho integration is connected.
    """
    if session.get("crm_provider") == "zoho":
        tok = session.get("access_token")
        if tok and tok != "DEMO_MODE":
            return tok
    stored = await get_user_zoho_token(_user_key(session))
    if stored:
        return stored.get("access_token")
    return None


# ── routes ─────────────────────────────────────────────────────────────────

@router.post("/connect")
async def connect_zoho(authorization: str = Header(...)):
    """Start Zoho OAuth and return the consent URL.

    The callback that ultimately receives `?code=...` is `routers/auth.py`'s
    existing `/auth/callback`. That handler peeks at our `_secondary_states`
    map to tell a mid-session connect apart from the primary-login flow.
    """
    from services.zoho_client import ZOHO_CLIENT_ID

    if not ZOHO_CLIENT_ID:
        raise HTTPException(
            status_code=501,
            detail="Zoho OAuth not configured. Set ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in your backend .env.",
        )

    session = _decode_session(authorization)
    state = secrets.token_urlsafe(16)
    _secondary_states[state] = _user_key(session)

    auth_url = get_authorization_url(state=state)
    return {"auth_url": auth_url, "state": state}


@router.get("/status")
async def zoho_status(authorization: str = Header(...)):
    """Return whether Zoho is connected for this user (primary or secondary)."""
    session = _decode_session(authorization)

    # Primary-Zoho login is implicitly connected.
    if session.get("crm_provider") == "zoho" and session.get("access_token") and session.get("access_token") != "DEMO_MODE":
        return {
            "connected": True,
            "primary": True,
            "zoho_email": session.get("email", ""),
            "message": "Zoho is your primary CRM login",
        }

    tokens = await get_user_zoho_token(_user_key(session))
    if tokens:
        return {
            "connected": True,
            "primary": False,
            "zoho_email": tokens.get("zoho_email", ""),
            "message": "Zoho connected as a secondary integration",
        }
    return {"connected": False, "message": "Zoho not connected yet"}


@router.delete("/disconnect")
async def disconnect_zoho(authorization: str = Header(...)):
    """Remove stored Zoho tokens for this user (L1 + DB)."""
    session = _decode_session(authorization)
    user_key = _user_key(session)
    _token_cache.pop(user_key, None)
    await _delete_token_from_db(user_key)
    return {"disconnected": True}


# ── shared callback hook (called from routers/auth.py:callback) ───────────

async def consume_secondary_state(
    state: str,
    code: str,
    frontend_url: str,
) -> tuple[str, str] | None:
    """
    If `state` was issued by /zoho-auth/connect, exchange the code for tokens,
    persist them under the originating user_key, and return a (redirect_url,
    user_key) tuple.

    Returns None when `state` is unknown (i.e. this is a primary-login flow
    and the caller should handle it normally).
    """
    user_key = _secondary_states.pop(state, None)
    if not user_key:
        return None

    try:
        tokens = await exchange_code_for_tokens(code)
        if "error" in tokens:
            redirect = f"{frontend_url}/settings?zoho_error={tokens.get('error_description', 'auth_failed')}"
            return redirect, user_key

        # Best-effort user lookup so we can show the connected email in Settings.
        zoho_email = ""
        zoho_user_id = ""
        try:
            user = await zoho_get_current_user(tokens.get("access_token", ""))
            zoho_email = user.get("email", "")
            zoho_user_id = str(user.get("id", "") or "")
        except Exception as e:
            logger.warning("zoho_auth: get_current_user after connect failed: %s", e)

        stored = {
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "zoho_email": zoho_email,
            "zoho_user_id": zoho_user_id,
            "expires_at": _expires_at_from_response(tokens).isoformat(),
            "scope": tokens.get("scope", ""),
        }
        _token_cache[user_key] = stored
        await _save_token_to_db(user_key, stored)
        logger.info("zoho_auth: secondary token stored user_key=%s zoho_email=%s", user_key, zoho_email)

        return f"{frontend_url}/settings?zoho=connected", user_key

    except Exception as e:
        logger.exception("zoho_auth: secondary connect failed: %s", e)
        return f"{frontend_url}/settings?zoho_error={str(e)}", user_key
