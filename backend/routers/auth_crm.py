"""
Multi-CRM OAuth router.

Handles /auth/{provider}/login and /auth/{provider}/callback for
salesforce, hubspot, and zoho (via the adapter layer).

The existing /auth/login, /auth/callback, /auth/demo-session routes in
auth.py remain untouched and continue to work for Zoho.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
import os
import secrets
import json
import base64

from services.crm import get_crm_adapter

router = APIRouter(prefix="/auth", tags=["Multi-CRM Auth"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


@router.get("/{provider}/login")
async def crm_login(provider: str):
    """
    Generate the OAuth authorization URL for any supported CRM.
    Supported providers: zoho, salesforce, hubspot
    """
    if provider == "demo":
        # Demo session — mirror existing /auth/demo-session logic
        session = {
            "user_id": "demo_user",
            "display_name": "Demo User",
            "email": "demo@dealiq.ai",
            "access_token": "DEMO_MODE",
            "refresh_token": "DEMO_MODE",
            "crm_provider": "demo",
        }
        encoded = base64.b64encode(json.dumps(session).encode()).decode()
        return {"session": encoded, "message": "Demo session created."}

    try:
        adapter = get_crm_adapter(provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    redirect_uri = f"{BACKEND_URL}/auth/{provider}/callback"
    state = secrets.token_urlsafe(16)
    auth_url = adapter.get_auth_url(redirect_uri, state)
    return {"auth_url": auth_url, "provider": provider, "state": state}


@router.get("/{provider}/callback")
async def crm_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(default=""),
):
    """
    Handle OAuth callback for any supported CRM.
    Exchanges the auth code for tokens, fetches the CRM user, then
    redirects to the frontend with a base64-encoded session payload.
    """
    try:
        adapter = get_crm_adapter(provider)
    except ValueError as e:
        return RedirectResponse(url=f"{FRONTEND_URL}/?error=unknown_provider&detail={provider}")

    redirect_uri = f"{BACKEND_URL}/auth/{provider}/callback"

    try:
        tokens = await adapter.authenticate(code, redirect_uri)
        crm_user = await adapter.get_current_user(tokens)

        session = {
            "user_id": crm_user.id,
            "display_name": crm_user.name,
            "email": crm_user.email,
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "crm_provider": provider,
            # Salesforce needs instance_url to make API calls
            "instance_url": tokens.extra.get("instance_url"),
        }
        encoded = base64.b64encode(json.dumps(session).encode()).decode()
        return RedirectResponse(url=f"{FRONTEND_URL}/?session={encoded}")

    except Exception as e:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/?error=auth_failed&provider={provider}&detail={str(e)}"
        )
