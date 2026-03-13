"""
Post-meeting pipeline orchestrator.
1. Gathers deal context + recent emails from DB.
2. Sends to AI for summary, action items, field updates, follow-up email draft.
3. Writes HIGH confidence updates to Zoho; queues MEDIUM/LOW to PendingCrmUpdate.
4. Creates Zoho note + tasks.
5. Returns full result summary.
"""

import os
import json
from datetime import datetime, timezone
from typing import Any

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import MeetingLog, PendingCrmUpdate, EmailExtraction


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_AI_MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a CRM intelligence engine. Given a meeting summary and deal context, produce a structured JSON response.

Return ONLY valid JSON with this exact shape:
{
  "ai_summary": "2-3 sentence meeting summary",
  "action_items": ["action 1", "action 2"],
  "field_updates": [
    {"field_name": "Next_Step", "new_value": "...", "confidence": "high"},
    {"field_name": "Stage", "new_value": "...", "confidence": "medium"}
  ],
  "follow_up_email": {
    "subject": "...",
    "body": "..."
  },
  "note_content": "Full meeting note for CRM"
}

confidence must be: high (clearly stated), medium (inferred), or low (uncertain).
field_name must be valid Zoho CRM Deals field names."""


async def _call_ai(prompt: str) -> dict[str, Any]:
    client = AsyncGroq(api_key=ANTHROPIC_API_KEY)
    resp = await client.chat.completions.create(
        model=_AI_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    raw = resp.choices[0].message.content or "{}"
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def process_post_meeting(
    meeting_log: MeetingLog,
    deal: dict[str, Any],
    access_token: str | None,
    db: AsyncSession,
) -> dict[str, Any]:
    """
    Full post-meeting pipeline. Returns summary of all actions taken.
    access_token=None → skips Zoho writes (demo mode).
    """
    # 1. Gather recent email context from DB
    email_rows = await db.execute(
        select(EmailExtraction)
        .where(EmailExtraction.deal_zoho_id == meeting_log.deal_id)
        .order_by(EmailExtraction.created_at.desc())
        .limit(5)
    )
    recent_emails = email_rows.scalars().all()
    email_context = "\n".join(
        f"- Next step: {e.next_step or 'none'} | Commitments: {', '.join(e.commitments or [])}"
        for e in recent_emails
    ) or "No recent email data."

    # 2. Build prompt
    topics = ", ".join(meeting_log.topics_confirmed or [])
    prompt = f"""Deal: {deal.get('name', 'Unknown')} | Stage: {deal.get('stage', '?')} | Amount: ${deal.get('amount', 0):,}
Meeting sentiment: {meeting_log.sentiment or 'ok'}
Topics confirmed: {topics or 'not specified'}
Notes: {meeting_log.quick_notes or 'none'}
Duration: {meeting_log.duration_minutes or '?'} minutes

Recent email context:
{email_context}

Generate the post-meeting CRM update."""

    # 3. AI analysis
    try:
        ai_result = await _call_ai(prompt)
    except Exception:
        ai_result = {
            "ai_summary": f"Meeting with {deal.get('name', 'client')} completed.",
            "action_items": [],
            "field_updates": [],
            "follow_up_email": {"subject": f"Following up — {deal.get('name', '')}", "body": ""},
            "note_content": meeting_log.quick_notes or "Meeting completed.",
        }

    # 4. Update meeting_log with AI results
    meeting_log.ai_summary = ai_result.get("ai_summary")
    meeting_log.action_items = ai_result.get("action_items", [])
    meeting_log.follow_up_email_draft = ai_result.get("follow_up_email")

    crm_updates_made: list[dict[str, Any]] = []
    pending_queued: list[dict[str, Any]] = []

    # 5. Handle field updates
    from services.zoho_writer import update_deal_fields, create_meeting_note, create_task

    for update in ai_result.get("field_updates", []):
        confidence = update.get("confidence", "low")
        field_name = update.get("field_name", "")
        new_value = update.get("new_value", "")

        if confidence == "high" and access_token:
            try:
                await update_deal_fields(access_token, meeting_log.deal_id, {field_name: new_value}, "high")
                crm_updates_made.append({"field": field_name, "value": new_value})
            except Exception:
                pass  # Don't fail the whole pipeline on a single field write
        else:
            # Queue for rep approval
            pending = PendingCrmUpdate(
                deal_id=meeting_log.deal_id,
                field_name=field_name,
                old_value=None,
                new_value=new_value,
                confidence=confidence,
                source="meeting",
                status="pending",
            )
            db.add(pending)
            pending_queued.append({"field": field_name, "value": new_value, "confidence": confidence})

    meeting_log.crm_updates_applied = {"direct": crm_updates_made, "pending": pending_queued}

    # 6. Create Zoho note
    note_created = False
    if access_token and ai_result.get("note_content"):
        try:
            await create_meeting_note(
                access_token,
                meeting_log.deal_id,
                {"title": "Meeting Summary", "content": ai_result["note_content"]},
            )
            note_created = True
        except Exception:
            pass

    # 7. Create Zoho tasks from action items
    tasks_created = 0
    if access_token:
        from datetime import timedelta
        due = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
        for item in ai_result.get("action_items", [])[:3]:  # cap at 3 tasks
            try:
                await create_task(
                    access_token,
                    meeting_log.deal_id,
                    {"subject": item, "due_date": due, "description": item},
                )
                tasks_created += 1
            except Exception:
                pass

    db.add(meeting_log)
    await db.commit()

    return {
        "meeting_log_id": str(meeting_log.id),
        "ai_summary": meeting_log.ai_summary,
        "action_items": meeting_log.action_items,
        "crm_updates_made": crm_updates_made,
        "pending_updates_queued": len(pending_queued),
        "note_created": note_created,
        "tasks_created": tasks_created,
        "follow_up_email_draft": meeting_log.follow_up_email_draft,
    }
