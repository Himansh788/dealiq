import asyncio
import httpx
import logging
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

logger = logging.getLogger(__name__)

ZOHO_CLIENT_ID = os.getenv("ZOHO_CLIENT_ID")
ZOHO_CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET")
ZOHO_REDIRECT_URI = os.getenv("ZOHO_REDIRECT_URI", "http://localhost:8000/auth/callback")
ZOHO_ACCOUNTS_URL = "https://accounts.zoho.in"   # Change to .com for non-India accounts
ZOHO_API_BASE = "https://www.zohoapis.in/crm/v2"  # Change to .com for non-India
ZOHO_API_V8   = "https://www.zohoapis.in/crm/v8"  # v8 required for Emails endpoint with content


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


async def _fetch_email_body_v8(
    module: str,
    record_id: str,
    message_id: str,
    access_token: str,
) -> tuple[str, str]:
    """
    Fetch full email body via Zoho CRM v8.
    GET /crm/v8/{module}/{record_id}/Emails/{message_id}
    Returns (html_content, plain_text).
    """
    encoded_id = quote(str(message_id), safe="")
    url = f"{ZOHO_API_V8}/{module}/{record_id}/Emails/{encoded_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, headers={"Authorization": f"Zoho-oauthtoken {access_token}"})

    if resp.status_code in (204, 404) or not resp.is_success:
        logger.debug("v8 email body: %s %s → %s", module, message_id[:20], resp.status_code)
        return "", ""

    data = resp.json()
    # v8 wraps in {"data": [{...}]} or returns the object directly
    if isinstance(data.get("data"), list) and data["data"]:
        obj = data["data"][0]
    elif isinstance(data.get("data"), dict):
        obj = data["data"]
    else:
        obj = data

    html = (
        obj.get("content")
        or obj.get("html_body")
        or obj.get("body")
        or obj.get("mail_body")
        or ""
    )
    plain = _strip_html(html) if html else (obj.get("text_body") or obj.get("summary") or "")
    return html, plain


async def _fetch_emails_for_record(module: str, record_id: str, access_token: str) -> list:
    """
    Fetch ALL emails for a Zoho CRM record using v8 API with full pagination and bodies.

    Step 1 — paginate GET /crm/v8/{module}/{record_id}/Emails until no more records
    Step 2 — fetch full body for every email in parallel via /Emails/{message_id}
    """
    all_emails: list[dict] = []

    # Step 1: paginate email list
    async with httpx.AsyncClient(timeout=15) as client:
        index: int | None = None
        while True:
            params: dict = {}
            if index is not None:
                params["index"] = index

            resp = await client.get(
                f"{ZOHO_API_V8}/{module}/{record_id}/Emails",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params=params,
            )

            if resp.status_code == 204:
                break  # no emails
            if not resp.is_success:
                logger.warning(
                    "Zoho v8 email list: %s/%s → status=%s body=%s",
                    module, record_id, resp.status_code, resp.text[:300],
                )
                # Fall back to v2 if v8 fails (scope issue etc.)
                break

            body = resp.json()
            page_emails = body.get("data", body.get("Emails", body.get("email_related_list", [])))
            if page_emails:
                all_emails.extend(page_emails)
                logger.debug("v8 email list: %s/%s page count=%d", module, record_id, len(page_emails))

            info = body.get("info", {})
            if info.get("more_records"):
                index = info.get("next_index")
                if index is None:
                    break
            else:
                break

    if not all_emails:
        # v2 fallback — older token or scope issue
        logger.info("v8 email list empty for %s/%s — falling back to v2", module, record_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{ZOHO_API_BASE}/{module}/{record_id}/Emails",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params={"sort_by": "sent_time", "sort_order": "desc", "per_page": 200},
            )
            if resp.is_success and resp.status_code != 204:
                b = resp.json()
                all_emails = b.get("data", b.get("Emails", b.get("email_related_list", [])))

    if not all_emails:
        return []

    logger.info("Zoho email list: %s/%s total=%d — fetching bodies", module, record_id, len(all_emails))

    # Step 2: fetch full body for every email in parallel
    async def _enrich(email: dict) -> dict:
        message_id = email.get("message_id") or email.get("id")
        if not message_id:
            return email
        html, plain = await _fetch_email_body_v8(module, record_id, message_id, access_token)
        if html or plain:
            return {**email, "html_content": html, "content": plain or _strip_html(html)}
        # v2 fallback for body
        plain_v2 = await _fetch_email_body(module, record_id, message_id, access_token)
        if plain_v2:
            return {**email, "content": plain_v2}
        return email

    enriched = await asyncio.gather(*[_enrich(e) for e in all_emails])
    result = list(enriched)

    bodies_found = sum(1 for e in result if e.get("content"))
    logger.info("Zoho email list: %s/%s enriched=%d/%d with body", module, record_id, bodies_found, len(result))
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


async def get_contacts_for_deal(access_token: str, deal_id: str) -> list:
    """
    Fetch contact roles for a deal, including the Contact record id.
    More reliable than fetch_deal_contact_roles for getting Contact IDs used in email lookup.
    Returns list of { id, email, name, role, title }.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ZOHO_API_BASE}/Deals/{deal_id}/Contact_Roles",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params={
                    "fields": "Email,First_Name,Last_Name,Title,Contact_Role",
                    "per_page": 20,
                },
            )
        if resp.status_code != 200:
            logger.info("get_contacts_for_deal: deal=%s status=%s", deal_id, resp.status_code)
            return []
        contacts = resp.json().get("data", [])
        result = []
        for c in contacts:
            role = c.get("Contact_Role", "")
            if isinstance(role, dict):
                role = role.get("name", "")
            result.append({
                "id": c.get("id", ""),
                "email": c.get("Email", ""),
                "name": f'{c.get("First_Name", "")} {c.get("Last_Name", "")}'.strip(),
                "role": role,
                "title": c.get("Title", ""),
            })
        logger.info("get_contacts_for_deal: deal=%s count=%d", deal_id, len(result))
        return result
    except Exception as e:
        logger.warning("get_contacts_for_deal: deal=%s error: %s", deal_id, e)
        return []


async def fetch_deal_calls(access_token: str, deal_id: str) -> list:
    """
    Fetch calls linked to a deal from Zoho CRM.
    Returns list of call dicts with injected type='call' and normalized direction.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ZOHO_API_BASE}/Calls",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params={
                    "criteria": f"(What_Id:equals:{deal_id})",
                    "fields": "Subject,Direction,Duration_in_seconds,Call_Start_Time,Created_Time,Description",
                    "per_page": 20,
                },
            )
        if resp.status_code == 204:
            return []
        if not resp.is_success:
            logger.info("fetch_deal_calls: deal=%s status=%s", deal_id, resp.status_code)
            return []
        calls = resp.json().get("data", [])
        result = []
        for raw in calls:
            raw["type"] = "call"
            raw["direction"] = "outbound" if raw.get("Direction") == "Outbound" else "inbound"
            result.append(raw)
        logger.info("fetch_deal_calls: deal=%s count=%d", deal_id, len(result))
        return result
    except Exception as e:
        logger.warning("fetch_deal_calls: deal=%s error: %s", deal_id, e)
        return []


async def get_all_activity_for_deal(access_token: str, deal_id: str) -> dict:
    """
    Unified activity bundle: emails (deal+contacts), activities, notes, calls, summary stats.
    Each external call is fault-tolerant — failures degrade gracefully to empty lists.
    """
    now = datetime.now(timezone.utc)

    # Step 1: parallel fetch
    results = await asyncio.gather(
        get_contacts_for_deal(access_token, deal_id),
        fetch_deal_emails(access_token, deal_id),
        fetch_deal_activities_closed(access_token, deal_id),
        fetch_deal_notes(access_token, deal_id),
        fetch_deal_calls(access_token, deal_id),
        return_exceptions=True,
    )

    contacts = results[0] if not isinstance(results[0], Exception) else []
    deal_emails = results[1] if not isinstance(results[1], Exception) else []
    activities_dict = results[2] if not isinstance(results[2], Exception) else {}
    notes = results[3] if not isinstance(results[3], Exception) else []
    calls = results[4] if not isinstance(results[4], Exception) else []

    # Step 2: per-contact emails (Contact_Roles IDs are more reliable than /Contacts fallback)
    contact_emails: list = []
    for c in contacts[:3]:  # cap 3 to stay within rate limits
        cid = c.get("id")
        if not cid:
            continue
        try:
            c_mails = await _fetch_emails_for_record("Contacts", cid, access_token)
            contact_emails.extend(c_mails)
        except Exception as e:
            logger.warning("get_all_activity_for_deal: contact email fetch id=%s: %s", cid, e)

    # Step 3: merge + deduplicate emails by message_id
    seen_emails: dict = {}
    for e in deal_emails + contact_emails:
        mid = e.get("message_id") or e.get("id", "")
        if mid and mid not in seen_emails:
            seen_emails[mid] = e
    merged_emails = sorted(seen_emails.values(), key=lambda e: e.get("sent_time", ""), reverse=True)

    # Step 4: combine activities (tasks + meetings + calls)
    tasks = activities_dict.get("tasks", []) if isinstance(activities_dict, dict) else []
    meetings = activities_dict.get("meetings", []) if isinstance(activities_dict, dict) else []
    all_activities = tasks + meetings + calls

    # Step 5: summary stats
    def _email_is_inbound(e: dict) -> bool:
        d = (e.get("direction") or e.get("type") or "").lower()
        if d in ("incoming", "received", "inbound"):
            return True
        if d in ("outgoing", "sent", "outbound"):
            return False
        # Zoho: sent=True means WE sent it
        return not e.get("sent", True)

    def _days_since_str(date_str) -> int:
        if not date_str:
            return 999
        try:
            dt = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).days
        except Exception:
            return 999

    inbound = [e for e in merged_emails if _email_is_inbound(e)]
    last_email = merged_emails[0].get("sent_time") if merged_emails else None
    last_inbound = inbound[0].get("sent_time") if inbound else None
    act_dates = [
        a.get("Call_Start_Time") or a.get("Created_Time", "")
        for a in all_activities
        if a.get("Call_Start_Time") or a.get("Created_Time")
    ]
    last_activity = max(act_dates) if act_dates else None

    return {
        "deal_id": deal_id,
        "contacts": contacts,
        "emails": merged_emails,
        "activities": all_activities,
        "notes": notes,
        "summary": {
            "total_emails": len(merged_emails),
            "total_activities": len(all_activities),
            "total_contacts": len(contacts),
            "emails_inbound": len(inbound),
            "emails_outbound": len(merged_emails) - len(inbound),
            "last_email_date": last_email,
            "last_inbound_email_date": last_inbound,
            "last_activity_date": last_activity,
            "days_since_last_inbound": _days_since_str(last_inbound),
            "days_since_any_activity": _days_since_str(last_email or last_activity),
        },
    }