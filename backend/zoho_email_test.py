"""
Zoho Email Debug Script
=======================
Run this to find out WHERE your emails actually live in Zoho CRM.

Usage:
  1. Paste your dealiq_session cookie value into SESSION
  2. Paste any deal ID from the dashboard into DEAL_ID
  3. Run:  python zoho_email_test.py

The script tries three approaches and tells you which one finds the emails.
"""

import asyncio
import httpx
import json
import base64
import os
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────────
# Paste your dealiq_session cookie value here
SESSION = "eyJ1c2VyX2lkIjoidmlqZW5kcmFAdmVydm90ZWNoLmNvbSIsImRpc3BsYXlfbmFtZSI6IlZpamVuZHJhIFNpbmdoIiwiZW1haWwiOiJ2aWplbmRyYUB2ZXJ2b3RlY2guY29tIiwiYWNjZXNzX3Rva2VuIjoiMTAwMC44ZGNhZjZiZTRlZTlkYzUzMDA4ZDEyYzA1M2IzZmJkNy5mNDY1YjdlYzA2ZGM4YTk2YzQzODJhYjlmZGExNDdjNyIsInJlZnJlc2hfdG9rZW4iOiIifQ=="

# Paste any deal ID here (copy from the deal row in the dashboard URL or CRM)
DEAL_ID = "202252000053985413"

BASE = os.getenv("ZOHO_API_BASE", "https://www.zohoapis.in/crm/v2")

# ── Decode session ─────────────────────────────────────────────────────────────
decoded = json.loads(base64.b64decode(SESSION).decode())
access_token = decoded["access_token"]
headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}


def sep(title: str):
    print(f"\n{'━' * 60}")
    print(f"  {title}")
    print('━' * 60)


async def get(client: httpx.AsyncClient, url: str, params: dict = None):
    r = await client.get(url, headers=headers, params=params or {})
    body = {}
    if r.status_code != 204:
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:500]}
    return r.status_code, body


def show_email_sample(e: dict):
    print(f"  subject:   {e.get('subject', '—')}")
    print(f"  direction: {e.get('direction', '—')}")
    print(f"  source:    {e.get('source', '—')}")
    print(f"  sent_time: {e.get('sent_time') or e.get('date', '—')}")
    print(f"  all fields: {list(e.keys())}")
    content = (e.get("content") or e.get("html_body") or e.get("body")
               or e.get("description") or e.get("summary") or e.get("snippet") or "")
    print(f"  content preview: {content[:200]!r}")
    # Print raw so we can spot any unexpected field that holds the body
    print(f"  full object: {json.dumps(e, indent=2, default=str)[:800]}")


async def test():
    async with httpx.AsyncClient(timeout=15) as client:

        # ── Step 1: Direct deal emails ─────────────────────────────────────────
        sep("STEP 1 — GET /Deals/{deal_id}/Emails  (direct deal-level emails)")
        status, body = await get(
            client, f"{BASE}/Deals/{DEAL_ID}/Emails",
            params={"sort_by": "sent_time", "sort_order": "desc", "per_page": 10},
        )
        print(f"HTTP status: {status}")
        emails = body.get("data", body.get("Emails", body.get("email_related_list", [])))
        print(f"Emails found: {len(emails)}")
        print(f"Response keys: {list(body.keys())}")
        if emails:
            print("\nFirst email (metadata):")
            show_email_sample(emails[0])

            # ── Step 1b: fetch full body for the first email ──────────────────
            message_id = emails[0].get("message_id")
            if message_id:
                sep(f"STEP 1b — GET /Deals/{{deal_id}}/Emails/{message_id}  (full body)")
                status2, body2 = await get(
                    client, f"{BASE}/Deals/{DEAL_ID}/Emails/{message_id}",
                )
                print(f"HTTP status: {status2}")
                print(f"Response keys: {list(body2.keys())}")
                email_obj = body2
                if isinstance(body2.get("data"), list) and body2["data"]:
                    email_obj = body2["data"][0]
                elif isinstance(body2.get("data"), dict):
                    email_obj = body2["data"]
                content = (
                    email_obj.get("content") or email_obj.get("html_body")
                    or email_obj.get("body") or email_obj.get("description")
                    or email_obj.get("message") or ""
                )
                print(f"Content field found: {bool(content)}")
                print(f"Content preview: {content[:300]!r}")
                print(f"All fields in body response: {list(email_obj.keys())}")
            else:
                print("No message_id on first email — cannot fetch body")
        else:
            print("Full response (first 600 chars):", str(body)[:600])

        # ── Step 2: Contacts linked to the deal ───────────────────────────────
        sep("STEP 2 — GET /Deals/{deal_id}/Contacts  (find linked contacts)")
        status, body = await get(
            client, f"{BASE}/Deals/{DEAL_ID}/Contacts",
            params={"per_page": 5, "fields": "id,Full_Name,Email"},
        )
        print(f"HTTP status: {status}")
        contacts = body.get("data", [])
        print(f"Contacts found: {len(contacts)}")
        for c in contacts:
            print(f"  id={c.get('id')}  name={c.get('Full_Name')}  email={c.get('Email')}")

        if not contacts:
            print("\n⚠  No contacts linked to this deal in Zoho.")
            print("   BCC Dropbox emails require a linked Contact to be associated with.")
            return

        # ── Step 3: Emails on each contact ────────────────────────────────────
        found_via_contact = False
        for contact in contacts[:3]:
            cid = contact.get("id")
            cname = contact.get("Full_Name", "?")
            sep(f"STEP 3 — GET /Contacts/{cid}/Emails  ({cname})")
            status, body = await get(
                client, f"{BASE}/Contacts/{cid}/Emails",
                params={"sort_by": "sent_time", "sort_order": "desc", "per_page": 10},
            )
            print(f"HTTP status: {status}")
            c_emails = body.get("data", body.get("Emails", []))
            print(f"Emails found: {len(c_emails)}")
            if c_emails:
                found_via_contact = True
                print("\nFirst email:")
                show_email_sample(c_emails[0])
            else:
                print("Response keys:", list(body.keys()))

        # ── Summary ───────────────────────────────────────────────────────────
        sep("SUMMARY")
        if emails:
            print("✅  Emails found via STEP 1 (deal-direct).")
            print("   fetch_deal_emails will return them on the first call.")
        elif found_via_contact:
            print("✅  Emails found via STEP 3 (contact-level — BCC Dropbox path).")
            print("   fetch_deal_emails will fall back correctly and return them.")
        else:
            print("❌  No emails found via any approach.")
            print("   Possible causes:")
            print("   1. The OAuth token is missing ZohoCRM.modules.emails.READ scope")
            print("      → Log out of DealIQ and log back in to get a fresh token.")
            print("   2. The deal ID is wrong — double-check you are using the Zoho record ID.")
            print("   3. The emails in the UI are from a different Zoho module (SalesInbox?)")
            print(f"   4. API base URL mismatch — currently using: {BASE}")


asyncio.run(test())
