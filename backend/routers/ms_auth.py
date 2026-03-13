"""
Microsoft OAuth2 router — Connect / Callback / Status / Disconnect.
Uses the Microsoft identity platform (login.microsoftonline.com).

Required env vars:
  MICROSOFT_CLIENT_ID      — Azure App Registration client ID
  MICROSOFT_CLIENT_SECRET  — Azure App Registration client secret
  MICROSOFT_TENANT_ID      — Tenant ID or "common" for multi-tenant
  MICROSOFT_REDIRECT_URI   — e.g. http://localhost:8000/ms-auth/callback

Tokens are persisted in the `microsoft_tokens` DB table (survives restarts).
An in-memory dict acts as a fast L1 cache in front of the DB.
Auto-refresh: access tokens are refreshed automatically when < 5 min remain.
"""

import os
import secrets
import base64
import json
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# ── state → user_key map (short-lived, only during OAuth flow) ─────────────
_pending_states: dict[str, str] = {}

# ── L1 in-memory cache (user_key → token dict) ────────────────────────────
# Populated on first DB read; evicted on disconnect or explicit refresh.
_token_cache: dict[str, dict] = {}

MS_SCOPES = [
    "offline_access",
    "Mail.Read",
    "Calendars.Read",
    "User.Read",
]

_TOKEN_REFRESH_BUFFER_SECONDS = 300  # refresh if < 5 min left


# ── env helpers ────────────────────────────────────────────────────────────

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


# ── session decode ─────────────────────────────────────────────────────────

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


# ── token expiry helpers ───────────────────────────────────────────────────

def _expires_at_from_response(token_resp: dict) -> datetime:
    """Compute expiry datetime from MS token response."""
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
    return datetime.now(timezone.utc) >= (expires_at - timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS))


# ── DB persistence ─────────────────────────────────────────────────────────

async def _save_token_to_db(user_key: str, tokens: dict) -> None:
    """Upsert MS token into microsoft_tokens table. No-op if DB unavailable."""
    try:
        from database.connection import get_db
        from database.models import MicrosoftToken
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

            row = (await db.execute(
                select(MicrosoftToken).where(MicrosoftToken.user_key == user_key)
            )).scalars().first()

            if row:
                row.access_token = tokens.get("access_token", "")
                row.refresh_token = tokens.get("refresh_token") or row.refresh_token
                row.ms_email = tokens.get("ms_email") or row.ms_email
                row.expires_at = expires_at
                row.scopes = " ".join(MS_SCOPES)
            else:
                db.add(MicrosoftToken(
                    user_key=user_key,
                    access_token=tokens.get("access_token", ""),
                    refresh_token=tokens.get("refresh_token"),
                    ms_email=tokens.get("ms_email"),
                    expires_at=expires_at,
                    scopes=" ".join(MS_SCOPES),
                ))
            await db.commit()
    except Exception as e:
        logger.warning("ms_auth: DB save failed for user_key=%s: %s", user_key, e)


async def _load_token_from_db(user_key: str) -> dict | None:
    """Load MS token from DB. Returns None if DB unavailable or not found."""
    try:
        from database.connection import get_db
        from database.models import MicrosoftToken
        from sqlalchemy import select

        async for db in get_db():
            if db is None:
                return None
            row = (await db.execute(
                select(MicrosoftToken).where(MicrosoftToken.user_key == user_key)
            )).scalars().first()
            if not row:
                return None
            expires_at_str = row.expires_at.isoformat() if row.expires_at else None
            return {
                "access_token": row.access_token,
                "refresh_token": row.refresh_token,
                "ms_email": row.ms_email,
                "expires_at": expires_at_str,
                "scope": row.scopes or "",
            }
    except Exception as e:
        logger.warning("ms_auth: DB load failed for user_key=%s: %s", user_key, e)
    return None


async def _delete_token_from_db(user_key: str) -> None:
    try:
        from database.connection import get_db
        from database.models import MicrosoftToken
        from sqlalchemy import select

        async for db in get_db():
            if db is None:
                return
            row = (await db.execute(
                select(MicrosoftToken).where(MicrosoftToken.user_key == user_key)
            )).scalars().first()
            if row:
                await db.delete(row)
                await db.commit()
    except Exception as e:
        logger.warning("ms_auth: DB delete failed for user_key=%s: %s", user_key, e)


# ── token refresh ──────────────────────────────────────────────────────────

async def _refresh_access_token(user_key: str, tokens: dict) -> dict | None:
    """
    Use the refresh_token to get a new access_token from Microsoft.
    Updates both the in-memory cache and DB on success.
    Returns the updated token dict or None on failure.
    """
    refresh_token = tokens.get("refresh_token")
    if not refresh_token or not _client_id():
        return None

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{_auth_base()}/token",
                data={
                    "client_id": _client_id(),
                    "client_secret": _client_secret(),
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                    "scope": " ".join(MS_SCOPES),
                },
            )
            if resp.status_code != 200:
                logger.warning("ms_auth: token refresh failed status=%d user=%s", resp.status_code, user_key)
                return None

            new_tokens = resp.json()
            updated = {
                **tokens,
                "access_token": new_tokens["access_token"],
                "expires_at": _expires_at_from_response(new_tokens).isoformat(),
            }
            # MS may issue a new refresh_token in the response
            if new_tokens.get("refresh_token"):
                updated["refresh_token"] = new_tokens["refresh_token"]

            _token_cache[user_key] = updated
            await _save_token_to_db(user_key, updated)
            logger.info("ms_auth: token refreshed for user_key=%s", user_key)
            return updated

    except Exception as e:
        logger.warning("ms_auth: token refresh exception user=%s: %s", user_key, e)
        return None


# ── public API ─────────────────────────────────────────────────────────────

async def get_user_token(user_key: str) -> dict | None:
    """
    Retrieve a valid MS token for this user.
    Priority: L1 cache → DB → None.
    Auto-refreshes if the access_token is expiring.
    Called by other services (email_intel, outlook_client, etc.)
    """
    # L1 cache hit
    tokens = _token_cache.get(user_key)
    if tokens:
        logger.info("ms_auth.get_user_token: L1 cache hit user_key=%s", user_key)
    else:
        logger.info("ms_auth.get_user_token: L1 cache miss user_key=%s — checking DB", user_key)

    # L1 miss → try DB
    if not tokens:
        tokens = await _load_token_from_db(user_key)
        if tokens:
            logger.info("ms_auth.get_user_token: DB hit user_key=%s ms_email=%s", user_key, tokens.get("ms_email"))
            _token_cache[user_key] = tokens
        else:
            logger.warning("ms_auth.get_user_token: NO TOKEN FOUND user_key=%s — user has not connected Outlook", user_key)

    if not tokens:
        return None

    expires_at = tokens.get("expires_at", "unknown")
    has_access = bool(tokens.get("access_token"))
    has_refresh = bool(tokens.get("refresh_token"))
    logger.info(
        "ms_auth.get_user_token: token found user_key=%s has_access_token=%s has_refresh_token=%s expires_at=%s",
        user_key, has_access, has_refresh, expires_at,
    )

    # Auto-refresh if expiring
    if _is_expired(tokens):
        logger.warning("ms_auth.get_user_token: token EXPIRED for user_key=%s expires_at=%s — attempting refresh", user_key, expires_at)
        refreshed = await _refresh_access_token(user_key, tokens)
        if refreshed:
            logger.info("ms_auth.get_user_token: token refreshed successfully user_key=%s", user_key)
            return refreshed
        else:
            logger.warning("ms_auth.get_user_token: token refresh FAILED user_key=%s — returning stale token", user_key)
            return tokens

    return tokens


# ── routes ─────────────────────────────────────────────────────────────────

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
        token_data = resp.json()

        # Fetch the MS user email for display + to use as an additional identity signal
        try:
            me_resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {token_data['access_token']}"},
            )
            if me_resp.status_code == 200:
                me = me_resp.json()
                token_data["ms_email"] = me.get("mail") or me.get("userPrincipalName")
        except Exception:
            pass

    user_key = _pending_states.pop(state, "default")
    tokens = {
        **token_data,
        "expires_at": _expires_at_from_response(token_data).isoformat(),
    }

    # Persist to L1 cache and DB
    _token_cache[user_key] = tokens
    await _save_token_to_db(user_key, tokens)
    logger.info("ms_auth: token stored for user_key=%s ms_email=%s", user_key, tokens.get("ms_email"))

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
    return RedirectResponse(url=f"{frontend_url}/settings?outlook=connected")


@router.get("/status")
async def outlook_status(authorization: str = Header(...)):
    """Check if an Outlook account is connected for this session."""
    session = _decode_session(authorization)
    if not _client_id():
        return {"connected": False, "message": "Microsoft OAuth not configured"}

    user_key = _user_key(session)
    tokens = await get_user_token(user_key)

    if tokens:
        return {
            "connected": True,
            "message": "Outlook connected",
            "email": tokens.get("ms_email", ""),
        }
    return {"connected": False, "message": "No Outlook account connected yet"}


@router.delete("/disconnect")
async def disconnect_outlook(authorization: str = Header(...)):
    """Remove stored Microsoft tokens (L1 cache + DB)."""
    session = _decode_session(authorization)
    user_key = _user_key(session)
    _token_cache.pop(user_key, None)
    await _delete_token_from_db(user_key)
    return {"disconnected": True}
