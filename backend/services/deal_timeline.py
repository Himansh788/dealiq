"""
Deal Timeline Service
=====================
Builds a chronological timeline of every significant event on a deal:
- Deal created
- Notes added (from Zoho Notes)
- Activities logged (calls, tasks, emails from Zoho Activities)
- Last known activity
- Closing date (future or past)
- Health signals (computed)

Then passes this to Groq to generate a narrative summary:
"This deal has been silent for 23 days. The last interaction was a demo
in November. Closing date passed 5 days ago. This is the pattern of a
zombie deal — recommend killing it or doing one final re-engagement."
"""

import anthropic
import os
import re
import json
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


def _days_ago(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).days


def _days_from_now(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        d = date.fromisoformat(s)
        return (d - date.today()).days
    except Exception:
        return None


def build_timeline(
    deal: Dict[str, Any],
    notes: List[Dict[str, Any]],
    activities: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a structured timeline from deal metadata + notes + activities.
    Returns a list of events sorted chronologically, plus computed signals.
    """
    events = []

    # ── Deal created ──────────────────────────────────────────────────────────
    created_dt = _parse_dt(deal.get("created_time"))
    if created_dt:
        events.append({
            "type": "created",
            "label": "Deal created",
            "detail": f"Added to CRM at stage: {deal.get('stage', 'Unknown')}",
            "datetime": created_dt.isoformat(),
            "days_ago": _days_ago(created_dt),
            "icon": "plus",
        })

    # ── Notes ─────────────────────────────────────────────────────────────────
    for note in notes[:10]:  # cap at 10 most recent
        note_dt = _parse_dt(note.get("Created_Time") or note.get("created_time"))
        content = note.get("Note_Content") or note.get("note_content") or ""
        title = note.get("Note_Title") or note.get("note_title") or "Note added"
        if note_dt:
            events.append({
                "type": "note",
                "label": title[:60],
                "detail": content[:120] + ("..." if len(content) > 120 else ""),
                "datetime": note_dt.isoformat(),
                "days_ago": _days_ago(note_dt),
                "icon": "file-text",
            })

    # ── Activities (calls, tasks, emails) ─────────────────────────────────────
    for act in activities[:10]:
        act_dt = _parse_dt(
            act.get("Created_Time") or act.get("created_time") or
            act.get("Due_Date") or act.get("due_date")
        )
        act_type = act.get("$se_module") or act.get("type") or "Activity"
        subject = act.get("Subject") or act.get("subject") or "Activity logged"
        status = act.get("Status") or act.get("status") or ""

        icon = "phone" if "call" in act_type.lower() else \
               "mail" if "email" in act_type.lower() else "check-square"

        if act_dt:
            events.append({
                "type": "activity",
                "label": f"{act_type}: {subject[:50]}",
                "detail": status,
                "datetime": act_dt.isoformat(),
                "days_ago": _days_ago(act_dt),
                "icon": icon,
            })

    # ── Last activity (from deal record itself) ───────────────────────────────
    last_act_dt = _parse_dt(deal.get("last_activity_time"))
    last_act_days = _days_ago(last_act_dt)

    # Only add if no notes/activities close to this date already
    if last_act_dt and (not events or all(
        abs((_parse_dt(e["datetime"]) - last_act_dt).total_seconds()) > 86400
        for e in events if _parse_dt(e.get("datetime"))
    )):
        events.append({
            "type": "last_activity",
            "label": "Last recorded activity",
            "detail": f"{last_act_days} days ago" if last_act_days is not None else "",
            "datetime": last_act_dt.isoformat(),
            "days_ago": last_act_days,
            "icon": "activity",
        })

    # ── Closing date ──────────────────────────────────────────────────────────
    closing_date = deal.get("closing_date")
    days_to_close = _days_from_now(closing_date)
    if closing_date:
        if days_to_close is not None and days_to_close < 0:
            events.append({
                "type": "closing_overdue",
                "label": "Closing date PASSED",
                "detail": f"Was due {abs(days_to_close)} days ago — still open",
                "datetime": f"{closing_date}T00:00:00+00:00",
                "days_ago": abs(days_to_close),
                "icon": "alert-triangle",
                "is_future": False,
                "is_warning": True,
            })
        else:
            events.append({
                "type": "closing_date",
                "label": "Expected close date",
                "detail": f"In {days_to_close} days" if days_to_close is not None else closing_date,
                "datetime": f"{closing_date}T00:00:00+00:00",
                "days_ago": -(days_to_close or 0),
                "icon": "flag",
                "is_future": True,
            })

    # Sort chronologically
    def sort_key(e):
        try:
            return datetime.fromisoformat(e["datetime"].replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    events.sort(key=sort_key)

    # ── Computed signals ──────────────────────────────────────────────────────
    silence_days = last_act_days if last_act_days is not None else _days_ago(created_dt)
    stage_age_days = _days_ago(created_dt)  # approximation

    signals = []
    if silence_days is not None:
        if silence_days >= 30:
            signals.append({"severity": "critical", "text": f"Silent for {silence_days} days — buyer has gone dark"})
        elif silence_days >= 14:
            signals.append({"severity": "warning", "text": f"No activity in {silence_days} days — engagement dropping"})
        else:
            signals.append({"severity": "good", "text": f"Active {silence_days} days ago — engagement recent"})

    if days_to_close is not None:
        if days_to_close < 0:
            signals.append({"severity": "critical", "text": f"Closing date passed {abs(days_to_close)} days ago"})
        elif days_to_close <= 7:
            signals.append({"severity": "critical", "text": f"Closes in {days_to_close} days — urgent"})
        elif days_to_close <= 30:
            signals.append({"severity": "warning", "text": f"Closes in {days_to_close} days"})

    if stage_age_days and stage_age_days > 45:
        signals.append({"severity": "warning", "text": f"Deal is {stage_age_days} days old — benchmark is 30 days"})

    return {
        "events": events,
        "signals": signals,
        "silence_days": silence_days,
        "days_to_close": days_to_close,
        "stage_age_days": stage_age_days,
        "total_events": len(events),
    }


async def generate_timeline_narrative(
    deal_name: str,
    stage: str,
    amount: float,
    health_label: str,
    timeline: Dict[str, Any],
) -> str:
    """
    Reads the timeline and writes a 2-3 sentence narrative that explains
    what the pattern of activity means for this deal's future.
    """
    events_text = "\n".join([
        f"  {i+1}. [{e.get('days_ago', '?')} days ago] {e['label']}: {e.get('detail', '')}"
        for i, e in enumerate(timeline["events"][-8:])  # last 8 events
    ]) or "  No recorded events"

    silence = timeline.get("silence_days")
    closing = timeline.get("days_to_close")

    prompt = f"""You are a sales manager reviewing a deal's activity timeline.

DEAL: {deal_name}
STAGE: {stage}
AMOUNT: ${amount:,.0f}
HEALTH: {health_label}
Silent for: {silence} days
Days to close: {closing if closing is not None else 'unknown'}

TIMELINE (most recent events):
{events_text}

Write a 2-3 sentence narrative interpreting this timeline. What does the pattern of activity tell you about this deal? Is the silence normal for this stage? What should happen next?

Be specific and direct. Use the actual data. Do not use bullet points. Output only the narrative text, no JSON, no headers."""

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        return f"Timeline analysis unavailable: {str(e)[:60]}"
