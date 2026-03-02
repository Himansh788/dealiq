"""
Zoho CRM write operations — separate from zoho_client.py (read-only) to avoid regression.
Uses Zoho CRM v8 REST API.
"""

import os
from typing import Any

import httpx

ZOHO_API_BASE = os.getenv("ZOHO_API_BASE", "https://www.zohoapis.in/crm/v8")


async def update_deal_fields(
    access_token: str,
    deal_id: str,
    fields: dict[str, Any],
    confidence: str,
) -> dict[str, Any]:
    """
    Update deal fields in Zoho CRM.
    confidence='high' → write directly and return result.
    confidence='medium'/'low' → caller is responsible for saving to PendingCrmUpdate.
    """
    if confidence not in ("high",):
        # Caller should save to PendingCrmUpdate; we don't write medium/low directly.
        return {"skipped": True, "reason": f"confidence={confidence}; queued for approval"}

    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{ZOHO_API_BASE}/Deals/{deal_id}",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            },
            json={"data": [{"id": deal_id, **fields}]},
        )
        resp.raise_for_status()
        return resp.json()


async def create_meeting_note(
    access_token: str,
    deal_id: str,
    note: dict[str, Any],
) -> dict[str, Any]:
    """Create a note on the deal in Zoho CRM."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_API_BASE}/Notes",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "data": [
                    {
                        "Note_Title": note.get("title", "Meeting Summary"),
                        "Note_Content": note.get("content", ""),
                        "Parent_Id": deal_id,
                        "$se_module": "Deals",
                    }
                ]
            },
        )
        resp.raise_for_status()
        return resp.json()


async def create_task(
    access_token: str,
    deal_id: str,
    task: dict[str, Any],
) -> dict[str, Any]:
    """Create a follow-up task on the deal in Zoho CRM."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_API_BASE}/Tasks",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "data": [
                    {
                        "Subject": task.get("subject", "Follow-up"),
                        "Due_Date": task.get("due_date"),
                        "Description": task.get("description", ""),
                        "What_Id": deal_id,
                        "$se_module": "Deals",
                        "Status": "Not Started",
                    }
                ]
            },
        )
        resp.raise_for_status()
        return resp.json()


async def log_call_activity(
    access_token: str,
    deal_id: str,
    activity: dict[str, Any],
) -> dict[str, Any]:
    """Log a completed call/meeting activity against the deal in Zoho CRM."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ZOHO_API_BASE}/Calls",
            headers={
                "Authorization": f"Zoho-oauthtoken {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "data": [
                    {
                        "Subject": activity.get("subject", "Call"),
                        "Call_Duration": str(activity.get("duration_minutes", 30)),
                        "Call_Duration_Seconds": str(activity.get("duration_minutes", 30) * 60),
                        "Call_Start_Time": activity.get("start_time"),
                        "Description": activity.get("description", ""),
                        "Call_Type": "Outbound",
                        "Call_Result": activity.get("result", "Interested"),
                        "What_Id": deal_id,
                        "$se_module": "Deals",
                    }
                ]
            },
        )
        resp.raise_for_status()
        return resp.json()


async def apply_pending_update(
    access_token: str,
    update: Any,  # PendingCrmUpdate ORM instance
) -> dict[str, Any]:
    """Apply a rep-approved PendingCrmUpdate row to Zoho."""
    return await update_deal_fields(
        access_token=access_token,
        deal_id=update.deal_id,
        fields={update.field_name: update.new_value},
        confidence="high",
    )
