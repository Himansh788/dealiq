"""
Deal Timeline Service
=====================
Builds a chronological timeline of every significant event on a deal
and passes it to Groq to generate a narrative summary.
"""

from groq import AsyncGroq
import os
import re
import json
from datetime import datetime, timezone, date
from typing import List, Dict, Any, Optional

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


MODEL = "llama-3.1-8b-instant"  # Speed-optimised for timeline narrative


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
    events = []

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

    for note in notes[:10]:
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

    last_act_dt = _parse_dt(deal.get("last_activity_time"))
    last_act_days = _days_ago(last_act_dt)

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

    def sort_key(e):
        try:
            return datetime.fromisoformat(e["datetime"].replace("Z", "+00:00"))
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    events.sort(key=sort_key)

    silence_days = last_act_days if last_act_days is not None else _days_ago(created_dt)
    stage_age_days = _days_ago(created_dt)

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
    # Only past events — exclude future closing date so AI doesn't misread recency
    past_events = [e for e in timeline["events"] if not e.get("is_future")]
    # Most-recent first so the AI prioritises the latest activity
    recent_events = list(reversed(past_events))[:8]
    events_text = "\n".join([
        f"  {i+1}. [{e.get('days_ago', '?')} days ago] {e['label']}: {e.get('detail', '')}"
        for i, e in enumerate(recent_events)
    ]) or "  No recorded events"

    silence = timeline.get("silence_days")
    closing = timeline.get("days_to_close")
    most_recent_label = recent_events[0]["label"] if recent_events else "none"
    most_recent_days = recent_events[0].get("days_ago", "?") if recent_events else "?"

    prompt = f"""You are a sales manager reading a deal's activity timeline.

DEAL: {deal_name} | STAGE: {stage} | AMOUNT: ${amount:,.0f} | HEALTH: {health_label}
Most recent activity: {most_recent_label} ({most_recent_days} days ago)
Days since any activity: {silence} | Days to close: {closing if closing is not None else 'unknown'}

RECENT TIMELINE (most recent first):
{events_text}

Write a 2-3 sentence narrative. Tell me:
1. What the PATTERN of activity reveals about this deal's momentum
2. Whether the current silence is normal for this stage or a warning sign
3. What must happen next and by when

Be direct and specific. Reference the most recent activity accurately. No bullet points. Output only the narrative text."""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=250,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Timeline analysis unavailable: {str(e)[:60]}"
