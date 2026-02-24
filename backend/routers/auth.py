from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
import os
import secrets
import json
import base64
from services.zoho_client import (
    get_authorization_url,
    exchange_code_for_tokens,
    get_current_user,
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
async def refresh_token_endpoint(refresh_token: str):
    """Get a new access token using the refresh token."""
    from services.zoho_client import refresh_access_token
    try:
        result = await refresh_access_token(refresh_token)
        return {"access_token": result.get("access_token"), "expires_in": result.get("expires_in")}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


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
