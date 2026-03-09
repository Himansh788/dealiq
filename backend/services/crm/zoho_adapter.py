"""
Zoho CRM adapter — thin wrapper around zoho_client.py.
All actual HTTP logic lives in zoho_client.py; this file only maps results
to the normalized CRM dataclasses.
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
import services.zoho_client as _zoho

logger = logging.getLogger(__name__)

ZOHO_ACCOUNTS_URL = os.getenv("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.in")
ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string to datetime; return None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _map_raw_to_crm_deal(raw: Dict[str, Any]) -> CRMDeal:
    owner = raw.get("Owner") or {}
    account = raw.get("Account_Name") or {}
    return CRMDeal(
        id=str(raw.get("id", "")),
        name=raw.get("Deal_Name") or "Unnamed Deal",
        company=account.get("name") if isinstance(account, dict) else (account or ""),
        stage=raw.get("Stage") or "Unknown",
        amount=float(raw.get("Amount") or 0),
        currency="USD",
        close_date=_parse_dt(raw.get("Closing_Date")),
        created_at=_parse_dt(raw.get("Created_Time")),
        owner_id=str(owner.get("id") or "") if isinstance(owner, dict) else "",
        owner_name=owner.get("name") if isinstance(owner, dict) else (owner or ""),
        probability=raw.get("Probability"),
        pipeline=None,
        description=raw.get("Description"),
        next_step=raw.get("Next_Step"),
        contacts=[],
        custom_fields={},
        raw=raw,
    )


def _map_raw_to_crm_activity(raw: Dict[str, Any], deal_id: str) -> CRMActivity:
    owner = raw.get("Owner") or {}
    return CRMActivity(
        id=str(raw.get("id", "")),
        deal_id=deal_id,
        type=raw.get("Activity_Type") or raw.get("$se_module") or "unknown",
        subject=raw.get("Subject") or raw.get("Activity_Name") or "",
        description=raw.get("Description"),
        date=_parse_dt(raw.get("Activity_Date") or raw.get("Created_Time")) or datetime.now(timezone.utc),
        owner_id=str(owner.get("id") or "") if isinstance(owner, dict) else "",
        owner_name=owner.get("name") if isinstance(owner, dict) else (owner or ""),
        direction=None,
        contacts=[],
        raw=raw,
    )


def _map_raw_to_crm_email(raw: Dict[str, Any], deal_id: Optional[str]) -> CRMEmail:
    return CRMEmail(
        id=str(raw.get("message_id") or raw.get("id") or ""),
        deal_id=deal_id,
        thread_id=raw.get("thread_id"),
        subject=raw.get("subject") or "",
        body=raw.get("content") or raw.get("body") or "",
        from_email=raw.get("from_email") or raw.get("from", {}).get("email", "") if isinstance(raw.get("from"), dict) else raw.get("from_email") or "",
        from_name=raw.get("from_name") or (raw.get("from", {}).get("user_name", "") if isinstance(raw.get("from"), dict) else ""),
        to_emails=[r.get("email", "") for r in raw.get("to", []) if isinstance(r, dict)],
        cc_emails=[r.get("email", "") for r in raw.get("cc", []) if isinstance(r, dict)],
        date=_parse_dt(raw.get("date") or raw.get("sent_time") or raw.get("Created_Time")) or datetime.now(timezone.utc),
        direction=raw.get("direction") or "inbound",
        has_attachments=bool(raw.get("has_attachment") or raw.get("attachments")),
        raw=raw,
    )


def _map_raw_to_crm_contact(raw: Dict[str, Any]) -> CRMContact:
    return CRMContact(
        id=str(raw.get("id", "")),
        name=raw.get("Full_Name") or raw.get("name") or "",
        email=raw.get("Email"),
        phone=raw.get("Phone") or raw.get("Mobile"),
        role=raw.get("Title") or raw.get("role"),
        company=raw.get("Account_Name") if isinstance(raw.get("Account_Name"), str) else (raw.get("Account_Name") or {}).get("name"),
        raw=raw,
    )


class ZohoAdapter(CRMAdapter):
    provider_name = "zoho"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        return _zoho.get_authorization_url(state=state)

    async def authenticate(self, auth_code: str, redirect_uri: str) -> CRMAuthTokens:
        tokens = await _zoho.exchange_code_for_tokens(auth_code)
        expires_in = int(tokens.get("expires_in") or 3600)
        return CRMAuthTokens(
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="zoho",
        )

    async def refresh_token(self, tokens: CRMAuthTokens) -> CRMAuthTokens:
        result = await _zoho.refresh_access_token(tokens.refresh_token)
        expires_in = int(result.get("expires_in") or 3600)
        return CRMAuthTokens(
            access_token=result["access_token"],
            refresh_token=tokens.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="zoho",
            extra=tokens.extra,
        )

    async def get_current_user(self, tokens: CRMAuthTokens) -> CRMUser:
        user = await _zoho.get_current_user(tokens.access_token)
        return CRMUser(
            id=str(user.get("id") or ""),
            name=user.get("display_name") or "",
            email=user.get("email") or "",
            role=None,
            avatar_url=None,
        )

    async def get_deals(self, tokens: CRMAuthTokens, modified_since: Optional[datetime] = None) -> List[CRMDeal]:
        raw_deals = await _zoho.fetch_deals(tokens.access_token)
        return [_map_raw_to_crm_deal(d) for d in raw_deals]

    async def get_deal(self, tokens: CRMAuthTokens, deal_id: str) -> CRMDeal:
        raw = await _zoho.fetch_single_deal(tokens.access_token, deal_id)
        if raw is None:
            raise ValueError(f"Deal {deal_id} not found in Zoho")
        return _map_raw_to_crm_deal(raw)

    async def get_activities(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMActivity]:
        raw_activities = await _zoho.fetch_deal_activities(tokens.access_token, deal_id)
        return [_map_raw_to_crm_activity(a, deal_id) for a in raw_activities]

    async def get_emails(self, tokens: CRMAuthTokens, deal_id: Optional[str] = None, entity_id: Optional[str] = None) -> List[CRMEmail]:
        target_id = deal_id or entity_id
        if not target_id:
            return []
        raw_emails = await _zoho.fetch_deal_emails(tokens.access_token, target_id)
        return [_map_raw_to_crm_email(e, deal_id) for e in raw_emails]

    async def get_contacts(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMContact]:
        raw_contacts = await _zoho.get_contacts_for_deal(tokens.access_token, deal_id)
        return [_map_raw_to_crm_contact(c) for c in raw_contacts]

    async def update_deal(self, tokens: CRMAuthTokens, deal_id: str, updates: Dict[str, Any]) -> bool:
        results = []
        for field, value in updates.items():
            ok = await _zoho.update_deal_field(deal_id, field, value, tokens.access_token)
            results.append(ok)
        return all(results)

    async def get_stages(self, tokens: CRMAuthTokens) -> List[Dict[str, Any]]:
        # Zoho doesn't have a dedicated stages endpoint; return common stages
        return [
            {"id": s, "name": s}
            for s in [
                "Qualification",
                "Needs Analysis",
                "Value Proposition",
                "Id. Decision Makers",
                "Perception Analysis",
                "Proposal/Price Quote",
                "Negotiations",
                "Contract Sent",
                "Closed Won",
                "Closed Lost",
            ]
        ]
