import asyncio
import httpx
import logging
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)

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
                 "ZohoCRM.modules.calls.READ,ZohoCRM.users.READ,"
                 "ZohoCRM.modules.emails.READ",
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
        "Owner,Last_Activity_Time,Created_Time,Modified_Time,Probability,Description,Next_Step"
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
    def _name(field: str) -> Optional[str]:
        v = raw.get(field)
        return v.get("name") if isinstance(v, dict) else v

    return {
        # ── Core fields (already mapped) ────────────────────────────────────
        "id": raw.get("id", ""),
        "name": raw.get("Deal_Name", "Unnamed Deal"),
        "stage": raw.get("Stage", "Unknown"),
        "amount": raw.get("Amount"),
        "closing_date": raw.get("Closing_Date"),
        "account_name": _name("Account_Name"),
        "owner": _name("Owner"),
        "last_activity_time": raw.get("Last_Activity_Time"),
        "created_time": raw.get("Created_Time"),
        "probability": raw.get("Probability"),
        "modified_time": raw.get("Modified_Time"),
        "next_step": raw.get("Next_Step"),

        # ── Deal Information panel fields (new) ──────────────────────────────
        "description": raw.get("Description"),
        "deal_type": raw.get("Type"),
        "geo_region": raw.get("GeoRegion__c") or raw.get("Geo_Region") or raw.get("GeoRegion"),
        "country": raw.get("Country_Picklist__c") or raw.get("Country_Picklist"),
        "city": raw.get("City"),
        "contact_name": _name("Contact_Name"),
        "expected_revenue": raw.get("Expected_Revenue"),
        "upgrade_amount": raw.get("Upgrade_Amount"),
        "lost_reason": raw.get("Lost_Reason"),
        "blacklist": raw.get("Blacklist"),
        "dropped_on": raw.get("Dropped_On"),
        "referred_by": raw.get("Referred_By"),
        "referred_by_provider": raw.get("Referred_By_Provider"),
        "campaign_source": raw.get("Campaign_Source"),
        "cs_account_id": raw.get("CS_AccountId__c") or raw.get("CS_AccountId"),
        "no_of_booking_per_month": raw.get("No_of_Booking_Per_Month__c") or raw.get("No_of_Booking_Per_Month"),
        "is_owner": _name("IS_Owner"),
        "inside_sales_rep": raw.get("Inside_Sales_Rep"),
        "account_management_rep": raw.get("Account_Management_Rep"),
        "customer_success_rep": raw.get("Customer_Success_Rep"),
        "supplier_partnership_rep": raw.get("Supplier_Partnership_Rep"),
        "legal_name": raw.get("Legal_Name"),
    }


async def fetch_single_deal(access_token: str, deal_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch one deal by record ID — much faster than fetching all deals then filtering.
    GET /Deals/{deal_id} returns all configured fields with no ?fields= param needed.
    Returns None if the deal is not found or the request fails.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
    if resp.status_code != 200:
        logger.warning("fetch_single_deal: deal=%s status=%s", deal_id, resp.status_code)
        return None
    data = resp.json().get("data", [])
    return map_zoho_deal(data[0]) if data else None


def _strip_html(html: str) -> str:
    """Strip HTML tags and collapse whitespace so AI gets plain text."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _fetch_email_body(
    module: str,
    record_id: str,
    message_id: str,
    access_token: str,
) -> str:
    """
    Fetch the full body of a single email.

    The email_related_list endpoint returns metadata only — snippet is often None.
    The full content requires a second call:
      GET /crm/v2/{module}/{record_id}/Emails/{message_id}

    message_id may be an RFC 2822 Message-ID like <abc@mail.zoho.in> — must be
    URL-encoded before using as a path segment.
    """
    # RFC Message-IDs contain <, >, @ and other special chars — encode them.
    encoded_id = quote(str(message_id), safe="")
    url = f"{ZOHO_API_BASE}/{module}/{record_id}/Emails/{encoded_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
        )
        if resp.status_code == 204 or not resp.is_success:
            logger.warning(
                "Zoho email body: %s/%s/Emails/%s → status=%s",
                module, record_id, message_id, resp.status_code,
            )
            return ""
        data = resp.json()
        # Response may be a single object or wrapped in {"data": [...]}
        if isinstance(data.get("data"), list) and data["data"]:
            email_obj = data["data"][0]
        elif isinstance(data.get("data"), dict):
            email_obj = data["data"]
        else:
            email_obj = data

        logger.debug(
            "Zoho email body fields: %s/%s/Emails/%s → keys=%s",
            module, record_id, message_id, list(email_obj.keys()),
        )

        raw = (
            email_obj.get("content")
            or email_obj.get("html_body")
            or email_obj.get("body")
            or email_obj.get("text_body")
            or email_obj.get("mail_body")
            or email_obj.get("description")
            or email_obj.get("message")
            or email_obj.get("summary")
            or ""
        )
        # Strip HTML tags so the AI receives readable plain text
        if raw and "<" in raw:
            raw = _strip_html(raw)
        return raw


async def _fetch_emails_for_record(module: str, record_id: str, access_token: str) -> list:
    """
    Fetch the Emails related list for a Zoho CRM record (Deal or Contact).

    Two-step because Zoho's email_related_list only returns metadata:
      Step 1 — GET /{module}/{record_id}/Emails          → list: subject, message_id, snippet=None
      Step 2 — GET /{module}/{record_id}/Emails/{msg_id} → full body per email (parallel, capped at 5)
    """
    # Step 1: email list (metadata only)
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/{module}/{record_id}/Emails",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"sort_by": "sent_time", "sort_order": "desc", "per_page": 200},
        )
        if resp.status_code == 204:
            return []
        if not resp.is_success:
            logger.warning(
                "Zoho email list: %s/%s → status=%s body=%s",
                module, record_id, resp.status_code, resp.text[:300],
            )
            return []
        body = resp.json()

    # Zoho v2 uses different response keys depending on the endpoint:
    # "data" → standard, "Emails" → older endpoints, "email_related_list" → this endpoint
    emails = body.get("data", body.get("Emails", body.get("email_related_list", [])))

    if not emails:
        return []

    logger.info("Zoho email list: %s/%s count=%d — fetching full bodies", module, record_id, len(emails))
    if emails:
        logger.debug(
            "Zoho email list sample fields: %s/%s → %s",
            module, record_id, list(emails[0].keys()),
        )

    # Step 2: fetch full body per email in parallel (cap at 5 to stay within rate limits)
    async def _enrich(email: dict) -> dict:
        # email_related_list uses "message_id"; standard list uses "id" — try both
        message_id = email.get("message_id") or email.get("id")
        if not message_id:
            logger.debug(
                "Zoho email body: %s/%s — no message_id/id field, skipping body fetch. keys=%s",
                module, record_id, list(email.keys()),
            )
            return email
        body_text = await _fetch_email_body(module, record_id, message_id, access_token)
        if body_text:
            return {**email, "content": body_text}
        return email

    enriched = await asyncio.gather(*[_enrich(e) for e in emails[:5]])
    result = list(enriched) + emails[5:]

    logger.info(
        "Zoho email list: %s/%s enriched=%d total=%d",
        module, record_id, len(enriched), len(result),
    )
    return result


async def fetch_deal_activities_closed(access_token: str, deal_id: str) -> dict:
    """
    Fetch closed tasks and meetings for a deal from Zoho CRM.
    Returns: { "tasks": [...], "meetings": [...] }
    """
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    async with httpx.AsyncClient(timeout=10) as client:
        tasks_r, meetings_r = await asyncio.gather(
            client.get(
                f"{ZOHO_API_BASE}/Tasks",
                headers=headers,
                params={
                    "criteria": f"(What_Id:equals:{deal_id})",
                    "fields": "Subject,Status,Due_Date,Closed_Time,Description",
                    "per_page": 20,
                },
            ),
            client.get(
                f"{ZOHO_API_BASE}/Events",
                headers=headers,
                params={
                    "criteria": f"(What_Id:equals:{deal_id})",
                    "fields": "Subject,Status,Start_DateTime,End_DateTime,Description",
                    "per_page": 10,
                },
            ),
        )

    tasks = tasks_r.json().get("data", []) if tasks_r.status_code == 200 else []
    meetings = meetings_r.json().get("data", []) if meetings_r.status_code == 200 else []

    closed_tasks = [t for t in tasks if t.get("Status") in ("Completed", "Closed", "Done")]
    closed_meetings = [m for m in meetings if m.get("Status") in ("Completed", "Closed", "Done")]

    logger.info(
        "Zoho activities: deal=%s tasks=%d/%d closed meetings=%d/%d closed",
        deal_id, len(closed_tasks), len(tasks), len(closed_meetings), len(meetings),
    )
    return {"tasks": closed_tasks, "meetings": closed_meetings}


async def fetch_deal_contact_roles(access_token: str, deal_id: str) -> list:
    """
    Fetch contact roles for a deal from Zoho CRM.
    Returns list of { name, role, email }.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}/Contact_Roles",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"fields": "Full_Name,Email,Contact_Role", "per_page": 20},
        )

    if resp.status_code != 200:
        logger.info("Zoho contact roles: deal=%s status=%s", deal_id, resp.status_code)
        return []

    contacts = resp.json().get("data", [])
    result = [
        {
            "name": c.get("Full_Name", ""),
            "email": c.get("Email", ""),
            "role": (
                c.get("Contact_Role", {}).get("name", "")
                if isinstance(c.get("Contact_Role"), dict)
                else c.get("Contact_Role", "")
            ),
        }
        for c in contacts
    ]
    logger.info("Zoho contact roles: deal=%s count=%d", deal_id, len(result))
    return result


async def _fetch_deal_contacts(access_token: str, deal_id: str) -> list:
    """Fetch contacts linked to a deal — needed for BCC Dropbox email fallback."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{ZOHO_API_BASE}/Deals/{deal_id}/Contacts",
            headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
            params={"per_page": 5, "fields": "id,Full_Name,Email"},
        )
        if resp.status_code == 204 or not resp.is_success:
            return []
        return resp.json().get("data", [])


async def fetch_deal_emails(access_token: str, deal_id: str) -> list:
    """
    Fetch emails for a deal from Zoho CRM.

    Two-step strategy to handle how Zoho actually stores BCC Dropbox emails:

    Step 1 — GET /Deals/{deal_id}/Emails
      Returns emails that were sent/received directly on the Deal record.
      For most deals this is empty because BCC Dropbox does NOT store emails here.

    Step 2 — GET /Deals/{deal_id}/Contacts → GET /Contacts/{id}/Emails (for each)
      BCC Dropbox emails are matched to a Contact by email address and stored on
      the Contact record. Zoho's UI aggregates Contact emails into the Deal's
      "Emails" tab, but the API does not — so we replicate that aggregation here.
    """
    # Step 1: direct deal-level emails
    emails = await _fetch_emails_for_record("Deals", deal_id, access_token)
    logger.info("Zoho email fetch (deal-direct): deal=%s count=%d", deal_id, len(emails))

    if emails:
        return emails

    # Step 2: BCC Dropbox emails live on the linked Contacts, not the Deal record
    logger.info(
        "Zoho email fetch: deal=%s no direct emails — fetching via linked contacts (BCC Dropbox path)",
        deal_id,
    )
    contacts = await _fetch_deal_contacts(access_token, deal_id)
    logger.info("Zoho email fetch: deal=%s linked contacts=%d", deal_id, len(contacts))

    contact_emails: list = []
    for contact in contacts[:3]:  # cap at 3 contacts to avoid rate limit issues
        contact_id = contact.get("id")
        if not contact_id:
            continue
        c_emails = await _fetch_emails_for_record("Contacts", contact_id, access_token)
        logger.info(
            "Zoho email fetch: contact=%s (%s) emails=%d",
            contact_id, contact.get("Full_Name", "?"), len(c_emails),
        )
        contact_emails.extend(c_emails)

    # Sort merged results newest-first so callers get the most recent emails
    try:
        contact_emails.sort(key=lambda e: e.get("sent_time", ""), reverse=True)
    except Exception:
        pass

    logger.info(
        "Zoho email fetch: deal=%s total via contacts=%d directions=%s",
        deal_id,
        len(contact_emails),
        list({e.get("direction", "?") for e in contact_emails}),
    )
    return contact_emails