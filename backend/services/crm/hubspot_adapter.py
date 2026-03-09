"""
HubSpot CRM adapter.
Uses HubSpot CRM v3 API with cursor-based pagination.
"""
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import httpx

from services.crm.base import (
    CRMAdapter,
    CRMAuthTokens,
    CRMContact,
    CRMDeal,
    CRMActivity,
    CRMEmail,
    CRMUser,
)

logger = logging.getLogger(__name__)

HS_AUTH_URL = "https://app.hubspot.com/oauth/authorize"
HS_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HS_API_BASE = "https://api.hubapi.com"

HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID", "")
HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET", "")
HUBSPOT_REDIRECT_URI = os.getenv("HUBSPOT_REDIRECT_URI", "http://localhost:8000/auth/hubspot/callback")

_HS_SCOPES = "crm.objects.deals.read crm.objects.contacts.read crm.objects.companies.read oauth"


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        # HubSpot timestamps are epoch milliseconds as strings
        if value.isdigit() or (value.replace("-", "").isdigit() and len(value) > 10):
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError, OSError):
        return None


def _auth_headers(tokens: CRMAuthTokens) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tokens.access_token}", "Content-Type": "application/json"}


async def _paginate(client: httpx.AsyncClient, url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Cursor-based pagination for HubSpot list endpoints."""
    results: List[Dict[str, Any]] = []
    after: Optional[str] = None
    base_params = dict(params or {})

    while True:
        req_params = dict(base_params)
        if after:
            req_params["after"] = after

        resp = await client.get(url, headers=headers, params=req_params)
        if resp.status_code == 204:
            break
        resp.raise_for_status()
        data = resp.json()

        results.extend(data.get("results", []))
        paging = data.get("paging", {})
        after = paging.get("next", {}).get("after") if isinstance(paging.get("next"), dict) else None
        if not after:
            break

    return results


def _map_hs_deal_to_crm_deal(raw: Dict[str, Any]) -> CRMDeal:
    props = raw.get("properties") or {}
    return CRMDeal(
        id=str(raw.get("id", "")),
        name=props.get("dealname") or "Unnamed Deal",
        company=props.get("company") or "",
        stage=props.get("dealstage") or "Unknown",
        amount=float(props.get("amount") or 0),
        currency="USD",
        close_date=_parse_dt(props.get("closedate")),
        created_at=_parse_dt(props.get("createdate") or raw.get("createdAt")),
        owner_id=str(props.get("hubspot_owner_id") or ""),
        owner_name=props.get("hubspot_owner_name") or "",
        probability=float(props.get("hs_deal_stage_probability") or 0) if props.get("hs_deal_stage_probability") else None,
        pipeline=props.get("pipeline"),
        description=props.get("description"),
        next_step=props.get("hs_next_step"),
        contacts=[],
        custom_fields={},
        raw=raw,
    )


def _map_hs_engagement_to_crm_activity(raw: Dict[str, Any], deal_id: str) -> CRMActivity:
    engagement = raw.get("engagement") or {}
    metadata = raw.get("metadata") or {}
    return CRMActivity(
        id=str(engagement.get("id") or raw.get("id") or ""),
        deal_id=deal_id,
        type=engagement.get("type") or raw.get("properties", {}).get("hs_task_type") or "unknown",
        subject=metadata.get("subject") or metadata.get("title") or raw.get("properties", {}).get("hs_task_subject") or "",
        description=metadata.get("body") or raw.get("properties", {}).get("hs_note_body"),
        date=_parse_dt(str(engagement.get("createdAt") or engagement.get("timestamp") or raw.get("properties", {}).get("hs_timestamp"))) or datetime.now(timezone.utc),
        owner_id=str(engagement.get("ownerId") or raw.get("properties", {}).get("hubspot_owner_id") or ""),
        owner_name="",
        direction=metadata.get("direction"),
        contacts=[str(c) for c in raw.get("associations", {}).get("contactIds", [])],
        raw=raw,
    )


def _map_hs_email_to_crm_email(raw: Dict[str, Any], deal_id: Optional[str]) -> CRMEmail:
    props = raw.get("properties") or {}
    engagement = raw.get("engagement") or {}
    metadata = raw.get("metadata") or {}

    from_obj = metadata.get("from") or {}
    to_list = metadata.get("to") or []
    cc_list = metadata.get("cc") or []

    return CRMEmail(
        id=str(engagement.get("id") or raw.get("id") or ""),
        deal_id=deal_id,
        thread_id=metadata.get("threadId") or props.get("hs_email_thread_id"),
        subject=metadata.get("subject") or props.get("hs_email_subject") or "",
        body=metadata.get("text") or metadata.get("html") or props.get("hs_email_text") or "",
        from_email=from_obj.get("email", "") if isinstance(from_obj, dict) else "",
        from_name=from_obj.get("firstName", "") if isinstance(from_obj, dict) else "",
        to_emails=[r.get("email", "") for r in to_list if isinstance(r, dict)],
        cc_emails=[r.get("email", "") for r in cc_list if isinstance(r, dict)],
        date=_parse_dt(str(engagement.get("createdAt") or props.get("hs_email_send_time"))) or datetime.now(timezone.utc),
        direction=metadata.get("direction") or ("inbound" if metadata.get("status") == "RECEIVED" else "outbound"),
        has_attachments=bool(metadata.get("attachments")),
        raw=raw,
    )


def _map_hs_contact_to_crm_contact(raw: Dict[str, Any]) -> CRMContact:
    props = raw.get("properties") or {}
    return CRMContact(
        id=str(raw.get("id", "")),
        name=f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or props.get("email") or "",
        email=props.get("email"),
        phone=props.get("phone"),
        role=props.get("jobtitle"),
        company=props.get("company"),
        raw=raw,
    )


class HubSpotAdapter(CRMAdapter):
    provider_name = "hubspot"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = (
            f"client_id={HUBSPOT_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={_HS_SCOPES.replace(' ', '%20')}"
            f"&state={state}"
        )
        return f"{HS_AUTH_URL}?{params}"

    async def authenticate(self, auth_code: str, redirect_uri: str) -> CRMAuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                HS_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": HUBSPOT_CLIENT_ID,
                    "client_secret": HUBSPOT_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": auth_code,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        expires_in = int(data.get("expires_in") or 1800)
        return CRMAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="hubspot",
        )

    async def refresh_token(self, tokens: CRMAuthTokens) -> CRMAuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                HS_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": HUBSPOT_CLIENT_ID,
                    "client_secret": HUBSPOT_CLIENT_SECRET,
                    "refresh_token": tokens.refresh_token,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()

        expires_in = int(data.get("expires_in") or 1800)
        return CRMAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token") or tokens.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="hubspot",
            extra=tokens.extra,
        )

    async def get_current_user(self, tokens: CRMAuthTokens) -> CRMUser:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{HS_API_BASE}/oauth/v1/access-tokens/{tokens.access_token}",
            )
            resp.raise_for_status()
            data = resp.json()

        return CRMUser(
            id=str(data.get("user_id") or data.get("hub_id") or ""),
            name=data.get("user") or "",
            email=data.get("user") or "",
            role=data.get("token_type"),
            avatar_url=None,
        )

    async def get_deals(self, tokens: CRMAuthTokens, modified_since: Optional[datetime] = None) -> List[CRMDeal]:
        props = "dealname,dealstage,amount,closedate,createdate,pipeline,description,hs_next_step,hubspot_owner_id,hs_deal_stage_probability"
        async with httpx.AsyncClient(timeout=30) as client:
            records = await _paginate(
                client,
                f"{HS_API_BASE}/crm/v3/objects/deals",
                _auth_headers(tokens),
                params={"properties": props, "limit": 100},
            )

        return [_map_hs_deal_to_crm_deal(r) for r in records]

    async def get_deal(self, tokens: CRMAuthTokens, deal_id: str) -> CRMDeal:
        props = "dealname,dealstage,amount,closedate,createdate,pipeline,description,hs_next_step,hubspot_owner_id,hs_deal_stage_probability"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{HS_API_BASE}/crm/v3/objects/deals/{deal_id}",
                headers=_auth_headers(tokens),
                params={"properties": props},
            )
            resp.raise_for_status()
            return _map_hs_deal_to_crm_deal(resp.json())

    async def get_activities(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMActivity]:
        """Fetch engagements (tasks + meetings) associated with a deal."""
        headers = _auth_headers(tokens)
        async with httpx.AsyncClient(timeout=20) as client:
            # v4 associations API
            assoc_resp = await client.get(
                f"{HS_API_BASE}/crm/v4/objects/deals/{deal_id}/associations/engagements",
                headers=headers,
            )
            if assoc_resp.status_code != 200:
                return []

            engagement_ids = [
                str(r.get("toObjectId") or r.get("id"))
                for r in assoc_resp.json().get("results", [])
                if r.get("toObjectId") or r.get("id")
            ]

            if not engagement_ids:
                return []

            activities: List[CRMActivity] = []
            for eid in engagement_ids[:50]:  # cap at 50
                eng_resp = await client.get(
                    f"{HS_API_BASE}/engagements/v1/engagements/{eid}",
                    headers=headers,
                )
                if eng_resp.status_code == 200:
                    activities.append(_map_hs_engagement_to_crm_activity(eng_resp.json(), deal_id))

        return activities

    async def get_emails(self, tokens: CRMAuthTokens, deal_id: Optional[str] = None, entity_id: Optional[str] = None) -> List[CRMEmail]:
        target_id = deal_id or entity_id
        if not target_id:
            return []

        headers = _auth_headers(tokens)
        async with httpx.AsyncClient(timeout=20) as client:
            # Use v4 associations to get email engagement IDs
            assoc_resp = await client.get(
                f"{HS_API_BASE}/crm/v4/objects/deals/{target_id}/associations/emails",
                headers=headers,
            )
            if assoc_resp.status_code != 200:
                return []

            email_ids = [
                str(r.get("toObjectId") or r.get("id"))
                for r in assoc_resp.json().get("results", [])
                if r.get("toObjectId") or r.get("id")
            ]

            if not email_ids:
                return []

            emails: List[CRMEmail] = []
            for eid in email_ids[:50]:
                eng_resp = await client.get(
                    f"{HS_API_BASE}/engagements/v1/engagements/{eid}",
                    headers=headers,
                )
                if eng_resp.status_code == 200:
                    emails.append(_map_hs_email_to_crm_email(eng_resp.json(), deal_id))

        return emails

    async def get_contacts(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMContact]:
        headers = _auth_headers(tokens)
        async with httpx.AsyncClient(timeout=15) as client:
            assoc_resp = await client.get(
                f"{HS_API_BASE}/crm/v4/objects/deals/{deal_id}/associations/contacts",
                headers=headers,
            )
            if assoc_resp.status_code != 200:
                return []

            contact_ids = [
                str(r.get("toObjectId") or r.get("id"))
                for r in assoc_resp.json().get("results", [])
                if r.get("toObjectId") or r.get("id")
            ]

            if not contact_ids:
                return []

            contacts: List[CRMContact] = []
            for cid in contact_ids[:50]:
                c_resp = await client.get(
                    f"{HS_API_BASE}/crm/v3/objects/contacts/{cid}",
                    headers=headers,
                    params={"properties": "firstname,lastname,email,phone,jobtitle,company"},
                )
                if c_resp.status_code == 200:
                    contacts.append(_map_hs_contact_to_crm_contact(c_resp.json()))

        return contacts

    async def update_deal(self, tokens: CRMAuthTokens, deal_id: str, updates: Dict[str, Any]) -> bool:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(
                f"{HS_API_BASE}/crm/v3/objects/deals/{deal_id}",
                headers=_auth_headers(tokens),
                json={"properties": updates},
            )

        if resp.is_success:
            return True
        logger.warning("HubSpot update_deal failed: %s %s", resp.status_code, resp.text[:200])
        return False

    async def get_stages(self, tokens: CRMAuthTokens) -> List[Dict[str, Any]]:
        """Fetch deal stages for the default pipeline."""
        async with httpx.AsyncClient(timeout=15) as client:
            # First get available pipelines
            pipelines_resp = await client.get(
                f"{HS_API_BASE}/crm/v3/pipelines/deals",
                headers=_auth_headers(tokens),
            )
            if not pipelines_resp.is_success:
                return []

            pipelines = pipelines_resp.json().get("results", [])
            if not pipelines:
                return []

            # Use the first (default) pipeline
            pipeline_id = pipelines[0].get("id")
            stages_resp = await client.get(
                f"{HS_API_BASE}/crm/v3/pipelines/deals/{pipeline_id}/stages",
                headers=_auth_headers(tokens),
            )
            if not stages_resp.is_success:
                return []

            return [
                {
                    "id": s.get("id"),
                    "name": s.get("label"),
                    "pipeline_id": pipeline_id,
                    "display_order": s.get("displayOrder"),
                    "metadata": s.get("metadata", {}),
                }
                for s in stages_resp.json().get("results", [])
            ]
