"""
Outlook primary-login router.

Unlike /ms-auth/connect (which requires an existing session to attach Outlook
as a *secondary* integration), /outlook-auth/login starts the OAuth flow with
no session and returns a primary session via the shared /ms-auth/callback.

The Azure-registered redirect URI (/ms-auth/callback) is reused. The two flows
are distinguished by which state set the OAuth `state` token lives in.
"""

import urllib.parse
import secrets

from fastapi import APIRouter, HTTPException

from routers.ms_auth import (
    _client_id, _auth_base, _redirect_uri, MS_SCOPES, _primary_states,
)

router = APIRouter()


@router.get("/login")
def outlook_primary_login():
    if not _client_id():
        raise HTTPException(
            status_code=501,
            detail="Microsoft OAuth not configured. Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID.",
        )
    state = secrets.token_urlsafe(16)
    _primary_states.add(state)

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
