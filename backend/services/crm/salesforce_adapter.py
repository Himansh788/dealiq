"""
Salesforce CRM adapter.
Uses REST API v59.0 + SOQL for all data access.
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

SF_AUTH_URL = "https://login.salesforce.com/services/oauth2/authorize"
SF_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
SF_API_VERSION = "v59.0"

SALESFORCE_CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID", "")
SALESFORCE_CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET", "")
SALESFORCE_REDIRECT_URI = os.getenv("SALESFORCE_REDIRECT_URI", "http://localhost:8000/auth/salesforce/callback")


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _instance_url(tokens: CRMAuthTokens) -> str:
    return tokens.extra.get("instance_url", "https://login.salesforce.com")


def _api_base(tokens: CRMAuthTokens) -> str:
    return f"{_instance_url(tokens)}/services/data/{SF_API_VERSION}"


def _auth_headers(tokens: CRMAuthTokens) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tokens.access_token}", "Content-Type": "application/json"}


async def _soql_query(client: httpx.AsyncClient, tokens: CRMAuthTokens, soql: str) -> List[Dict[str, Any]]:
    """Execute a SOQL query and follow nextRecordsUrl pagination."""
    base = _api_base(tokens)
    headers = _auth_headers(tokens)
    records: List[Dict[str, Any]] = []
    url = f"{base}/query"
    params: Dict[str, Any] = {"q": soql}
    next_url: Optional[str] = None

    while True:
        if next_url:
            resp = await client.get(f"{_instance_url(tokens)}{next_url}", headers=headers)
        else:
            resp = await client.get(url, headers=headers, params=params)

        if resp.status_code == 204:
            break
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        next_url = data.get("nextRecordsUrl")
        if not next_url or data.get("done", True):
            break

    return records


def _map_opportunity_to_crm_deal(raw: Dict[str, Any]) -> CRMDeal:
    owner = raw.get("Owner") or {}
    return CRMDeal(
        id=str(raw.get("Id", "")),
        name=raw.get("Name") or "Unnamed Deal",
        company=raw.get("Account", {}).get("Name", "") if isinstance(raw.get("Account"), dict) else "",
        stage=raw.get("StageName") or "Unknown",
        amount=float(raw.get("Amount") or 0),
        currency=raw.get("CurrencyIsoCode") or "USD",
        close_date=_parse_dt(raw.get("CloseDate")),
        created_at=_parse_dt(raw.get("CreatedDate")),
        owner_id=str(owner.get("Id") or "") if isinstance(owner, dict) else "",
        owner_name=owner.get("Name") if isinstance(owner, dict) else "",
        probability=raw.get("Probability"),
        pipeline=raw.get("ForecastCategoryName"),
        description=raw.get("Description"),
        next_step=raw.get("NextStep"),
        contacts=[],
        custom_fields={},
        raw=raw,
    )


def _map_task_to_crm_activity(raw: Dict[str, Any], deal_id: str) -> CRMActivity:
    owner = raw.get("Owner") or {}
    return CRMActivity(
        id=str(raw.get("Id", "")),
        deal_id=deal_id,
        type=raw.get("TaskSubtype") or raw.get("Type") or "Task",
        subject=raw.get("Subject") or "",
        description=raw.get("Description"),
        date=_parse_dt(raw.get("ActivityDate") or raw.get("CreatedDate")) or datetime.now(timezone.utc),
        owner_id=str(owner.get("Id") or "") if isinstance(owner, dict) else "",
        owner_name=owner.get("Name") if isinstance(owner, dict) else "",
        direction=None,
        contacts=[],
        raw=raw,
    )


def _map_email_message_to_crm_email(raw: Dict[str, Any], deal_id: Optional[str]) -> CRMEmail:
    return CRMEmail(
        id=str(raw.get("Id", "")),
        deal_id=deal_id,
        thread_id=raw.get("ThreadIdentifier"),
        subject=raw.get("Subject") or "",
        body=raw.get("TextBody") or raw.get("HtmlBody") or "",
        from_email=raw.get("FromAddress") or "",
        from_name=raw.get("FromName") or "",
        to_emails=[a.strip() for a in (raw.get("ToAddress") or "").split(";") if a.strip()],
        cc_emails=[a.strip() for a in (raw.get("CcAddress") or "").split(";") if a.strip()],
        date=_parse_dt(raw.get("MessageDate") or raw.get("CreatedDate")) or datetime.now(timezone.utc),
        direction="inbound" if raw.get("Incoming") else "outbound",
        has_attachments=bool(raw.get("HasAttachment")),
        raw=raw,
    )


def _map_contact_role_to_crm_contact(raw: Dict[str, Any]) -> CRMContact:
    contact = raw.get("Contact") or {}
    return CRMContact(
        id=str(contact.get("Id") or raw.get("ContactId") or ""),
        name=contact.get("Name") or "",
        email=contact.get("Email"),
        phone=contact.get("Phone"),
        role=raw.get("Role"),
        company=None,
        raw=raw,
    )


class SalesforceAdapter(CRMAdapter):
    provider_name = "salesforce"

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        params = (
            f"response_type=code"
            f"&client_id={SALESFORCE_CLIENT_ID}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state}"
            f"&prompt=consent"
        )
        return f"{SF_AUTH_URL}?{params}"

    async def authenticate(self, auth_code: str, redirect_uri: str) -> CRMAuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SF_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": SALESFORCE_CLIENT_ID,
                    "client_secret": SALESFORCE_CLIENT_SECRET,
                    "redirect_uri": redirect_uri,
                    "code": auth_code,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_in = int(data.get("expires_in") or 7200)
        return CRMAuthTokens(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="salesforce",
            extra={"instance_url": data.get("instance_url", "")},
        )

    async def refresh_token(self, tokens: CRMAuthTokens) -> CRMAuthTokens:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                SF_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": SALESFORCE_CLIENT_ID,
                    "client_secret": SALESFORCE_CLIENT_SECRET,
                    "refresh_token": tokens.refresh_token,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        expires_in = int(data.get("expires_in") or 7200)
        extra = dict(tokens.extra)
        if "instance_url" in data:
            extra["instance_url"] = data["instance_url"]
        return CRMAuthTokens(
            access_token=data["access_token"],
            refresh_token=tokens.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            provider="salesforce",
            extra=extra,
        )

    async def get_current_user(self, tokens: CRMAuthTokens) -> CRMUser:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_api_base(tokens)}/chatter/users/me",
                headers=_auth_headers(tokens),
            )
            resp.raise_for_status()
            data = resp.json()

        return CRMUser(
            id=str(data.get("id") or ""),
            name=data.get("displayName") or data.get("name") or "",
            email=data.get("email") or "",
            role=data.get("userType"),
            avatar_url=data.get("photo", {}).get("largePhotoUrl") if isinstance(data.get("photo"), dict) else None,
        )

    async def get_deals(self, tokens: CRMAuthTokens, modified_since: Optional[datetime] = None) -> List[CRMDeal]:
        soql = (
            "SELECT Id, Name, StageName, Amount, CloseDate, CurrencyIsoCode, "
            "CreatedDate, LastModifiedDate, Probability, Description, NextStep, "
            "ForecastCategoryName, Owner.Id, Owner.Name, "
            "Account.Name "
            "FROM Opportunity"
        )
        if modified_since:
            soql += f" WHERE LastModifiedDate > {modified_since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        soql += " ORDER BY LastModifiedDate DESC"

        async with httpx.AsyncClient(timeout=30) as client:
            records = await _soql_query(client, tokens, soql)

        return [_map_opportunity_to_crm_deal(r) for r in records]

    async def get_deal(self, tokens: CRMAuthTokens, deal_id: str) -> CRMDeal:
        soql = (
            f"SELECT Id, Name, StageName, Amount, CloseDate, CurrencyIsoCode, "
            f"CreatedDate, LastModifiedDate, Probability, Description, NextStep, "
            f"ForecastCategoryName, Owner.Id, Owner.Name, Account.Name "
            f"FROM Opportunity WHERE Id = '{deal_id}' LIMIT 1"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            records = await _soql_query(client, tokens, soql)

        if not records:
            raise ValueError(f"Deal {deal_id} not found in Salesforce")
        return _map_opportunity_to_crm_deal(records[0])

    async def get_activities(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMActivity]:
        task_soql = (
            f"SELECT Id, Subject, Description, ActivityDate, CreatedDate, Type, TaskSubtype, "
            f"Owner.Id, Owner.Name "
            f"FROM Task WHERE WhatId = '{deal_id}' ORDER BY ActivityDate DESC"
        )
        event_soql = (
            f"SELECT Id, Subject, Description, ActivityDate, CreatedDate, Type, "
            f"Owner.Id, Owner.Name "
            f"FROM Event WHERE WhatId = '{deal_id}' ORDER BY ActivityDate DESC"
        )
        async with httpx.AsyncClient(timeout=20) as client:
            tasks = await _soql_query(client, tokens, task_soql)
            events = await _soql_query(client, tokens, event_soql)

        activities = [_map_task_to_crm_activity(r, deal_id) for r in tasks]
        activities += [_map_task_to_crm_activity({**r, "TaskSubtype": "Event"}, deal_id) for r in events]
        return activities

    async def get_emails(self, tokens: CRMAuthTokens, deal_id: Optional[str] = None, entity_id: Optional[str] = None) -> List[CRMEmail]:
        target_id = deal_id or entity_id
        if not target_id:
            return []
        soql = (
            f"SELECT Id, Subject, TextBody, HtmlBody, FromAddress, FromName, "
            f"ToAddress, CcAddress, MessageDate, CreatedDate, Incoming, HasAttachment, ThreadIdentifier "
            f"FROM EmailMessage WHERE RelatedToId = '{target_id}' ORDER BY MessageDate DESC"
        )
        async with httpx.AsyncClient(timeout=20) as client:
            records = await _soql_query(client, tokens, soql)

        return [_map_email_message_to_crm_email(r, deal_id) for r in records]

    async def get_contacts(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMContact]:
        soql = (
            f"SELECT Id, Role, ContactId, Contact.Id, Contact.Name, Contact.Email, Contact.Phone "
            f"FROM OpportunityContactRole WHERE OpportunityId = '{deal_id}'"
        )
        async with httpx.AsyncClient(timeout=15) as client:
            records = await _soql_query(client, tokens, soql)

        return [_map_contact_role_to_crm_contact(r) for r in records]

    async def update_deal(self, tokens: CRMAuthTokens, deal_id: str, updates: Dict[str, Any]) -> bool:
        url = f"{_api_base(tokens)}/sobjects/Opportunity/{deal_id}"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.patch(url, headers=_auth_headers(tokens), json=updates)

        if resp.status_code == 204:
            return True
        logger.warning("Salesforce update_deal failed: %s %s", resp.status_code, resp.text[:200])
        return False

    async def get_stages(self, tokens: CRMAuthTokens) -> List[Dict[str, Any]]:
        soql = "SELECT MasterLabel, SortOrder, IsActive, IsClosed, IsWon FROM OpportunityStage WHERE IsActive = true ORDER BY SortOrder"
        async with httpx.AsyncClient(timeout=15) as client:
            records = await _soql_query(client, tokens, soql)

        return [{"id": r.get("MasterLabel"), "name": r.get("MasterLabel"), "sort_order": r.get("SortOrder"), "is_closed": r.get("IsClosed"), "is_won": r.get("IsWon")} for r in records]
