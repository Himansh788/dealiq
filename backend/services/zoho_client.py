import httpx
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/auth/callback")
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.in"   # Change to .com for non-India accounts
ZOHO_API_BASE = "https://www.zohoapis.in/crm/v2"  # Change to .com for non-India


def get_authorization_url(state: str = "") -> str:
    """Build the Zoho OAuth2 authorization URL."""
    params = {
        "scope": "ZohoCRM.modules.deals.READ,ZohoCRM.modules.contacts.READ,"
                 "ZohoCRM.modules.activities.READ,ZohoCRM.modules.notes.READ,"
                 "ZohoCRM.modules.calls.READ,ZohoCRM.users.READ",
        "client_id": ZOHO_CLIENT_ID,
        "response_type": "code",
        "access_type": "offline",
        "redirect_uri": ZOHO_REDIRECT_URI,
        "state": state,
        "prompt": "consent",
    }
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{ZOHO_ACCOUNTS_URL}/oauth/v2/auth?{query}"


async def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": ZOHO_CLIENT_ID,
                "client_secret": ZOHO_CLIENT_SECRET,
                "redirect_uri": ZOHO_REDIRECT_URI,
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> Dict[str, Any]:
    """Use refresh token to get a new access token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_ACCOUNTS_URL}/oauth/v2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": ZOHO_CLIENT_ID,
                "client_secret": ZOHO_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_current_user(access_token: str) -> Dict[str, Any]:
    """Fetch the authenticated Zoho user's profile."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/users?type=CurrentUser",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        resp.raise_for_status()
        data = resp.json()
        user = data.get("users", [{}])[0]
        return {
            "id": user.get("id"),
            "display_name": user.get("full_name", "Unknown"),
            "email": user.get("email", ""),
        }


async def fetch_deals(access_token: str, page: int = 1, per_page: int = 50) -> List[Dict[str, Any]]:
    """Fetch deals from Zoho CRM."""
    fields = (
        "Deal_Name,Stage,Amount,Closing_Date,Account_Name,"
        "Owner,Last_Activity_Time,Created_Time,Modified_Time,Probability,Description"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={
                "fields": fields,
                "page": page,
                "per_page": per_page,
                "sort_by": "Last_Activity_Time",
                "sort_order": "desc",
            },
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])


async def fetch_deal_notes(access_token: str, deal_id: str) -> List[Dict[str, Any]]:
    """Fetch notes attached to a specific deal."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}/Notes",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])


async def fetch_deal_activities(access_token: str, deal_id: str) -> List[Dict[str, Any]]:
    """Fetch activities (calls, tasks) linked to a deal."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}/Activities",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if resp.status_code == 204:
            return []
        resp.raise_for_status()
        return resp.json().get("data", [])


def map_zoho_deal(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a raw Zoho deal record into our schema format."""
    return {
        "id": raw.get("id", ""),
        "name": raw.get("Deal_Name", "Unnamed Deal"),
        "stage": raw.get("Stage", "Unknown"),
        "amount": raw.get("Amount"),
        "closing_date": raw.get("Closing_Date"),
        "account_name": (raw.get("Account_Name") or {}).get("name") if isinstance(raw.get("Account_Name"), dict) else raw.get("Account_Name"),
        "owner": (raw.get("Owner") or {}).get("name") if isinstance(raw.get("Owner"), dict) else raw.get("Owner"),
        "last_activity_time": raw.get("Last_Activity_Time"),
        "created_time": raw.get("Created_Time"),
        "probability": raw.get("Probability"),
        "modified_time": raw.get("Modified_Time"),
    }


async def fetch_deal_emails(access_token: str, deal_id: str) -> list:
    """Fetch emails linked to a deal from Zoho CRM."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}/Emails",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if resp.status_code == 204:
            return []
        if not resp.is_success:
            return []
        return resp.json().get("Emails", resp.json().get("data", []))