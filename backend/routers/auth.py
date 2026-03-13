from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import RedirectResponse, JSONResponse
import os
import secrets
import json
import base64
from services.zoho_client import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_current_user,
    refresh_access_token,
)

router = APIRouter()

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


@router.get("/login")
def login():
    """Redirect user to Zoho OAuth2 consent screen."""
    state = secrets.token_urlsafe(16)
    url = get_authorization_url(state=state)
    return {"auth_url": url, "state": state}


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(default="")):
    """
    Handle Zoho OAuth2 callback.
    Exchanges code for tokens, fetches user info, then redirects to frontend
    with a base64-encoded session payload in the URL fragment.
    """
    try:
        tokens = await exchange_code_for_tokens(code)
        if "error" in tokens:
            raise HTTPException(status_code=400, detail=tokens.get("error_description", "OAuth error"))

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")

        user = await get_current_user(access_token)

        # Build a lightweight session payload for the frontend
        # In production, use proper JWT or server-side sessions
        session = {
            "user_id": user.get("id"),
            "display_name": user.get("display_name"),
            "email": user.get("email"),
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        encoded = base64.b64encode(json.dumps(session).encode()).decode()
        return RedirectResponse(url=f"{FRONTEND_URL}/?session={encoded}")

    except HTTPException:
        raise
    except Exception as e:
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=auth_failed&detail={str(e)}")


@router.post("/refresh")
async def refresh_token_endpoint(authorization: str = Header(default="")):
    """
    Refresh the Zoho access token using the refresh_token embedded in the
    current session. Returns a new fully-encoded session that the frontend
    should store in localStorage to replace the stale one.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    raw = authorization.replace("Bearer ", "").strip()
    try:
        session = json.loads(base64.b64decode(raw).decode())
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session token")

    rt = session.get("refresh_token", "")
    if not rt or rt == "DEMO_MODE":
        raise HTTPException(status_code=400, detail="No refresh token available")

    try:
        result = await refresh_access_token(rt)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Zoho token refresh failed: {e}")

    new_access_token = result.get("access_token")
    if not new_access_token:
        raise HTTPException(status_code=401, detail="Zoho did not return a new access token")

    # Build updated session preserving all user fields, just swapping access_token
    new_session = {**session, "access_token": new_access_token}
    encoded = base64.b64encode(json.dumps(new_session).encode()).decode()
    return {"session": encoded}


@router.get("/demo-session")
def demo_session():
    """
    Return a demo session for judges/testers without Zoho account.
    This bypasses OAuth and uses simulated data.
    """
    session = {
        "user_id": "demo_user",
        "display_name": "Demo User",
        "email": "demo@dealiq.ai",
        "access_token": "DEMO_MODE",
        "refresh_token": "DEMO_MODE",
    }
    encoded = base64.b64encode(json.dumps(session).encode()).decode()
    return {"session": encoded, "message": "Demo session created. Use simulated deal data."}
