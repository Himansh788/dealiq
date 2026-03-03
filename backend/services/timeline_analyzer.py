"""
Timeline Analyzer
=================
Parses raw Zoho CRM v9 Timelines API entries into structured deal signals.

The v9 Timelines API provides richer data than notes/activities:
- Field-level change history (Stage, Expected Revenue, Probability)
- Action source (crm_ui = human, workflow = automation)
- Email send events with subject
- Per-field old→new values with pick list colours

All functions are pure / synchronous — no I/O, easy to test.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Stage sequence numbers used to detect forward vs backward movement.
# Lower index = earlier in pipeline. Stages not in this list use sequence_number
# from pick_list_values when available, falling back to index-based comparison.
_STAGE_SEQUENCE: Dict[str, int] = {
    "Qualification": 1,
    "Demo Scheduled": 2,
    "Demo Done": 3,
    "Needs Analysis": 4,
    "Value Proposition": 5,
    "Evaluation": 6,
    "Id. Decision Makers": 7,
    "Proposal/Price Quote": 8,
    "Sales Approved Deal": 9,
    "Negotiation/Review": 10,
    "Contract Sent": 11,
    "Closed Won": 99,
    "Closed - Won": 99,
    "Closed Lost": 100,
    "Closed - Lost": 100,
}


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _days_ago(dt: Optional[datetime]) -> Optional[int]:
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def _stage_position(stage_name: str, pick_list_values: List[dict]) -> int:
    """
    Return a sortable integer representing a stage's position in the pipeline.
    Prefers sequence_number from pick_list_values (Zoho-configured order),
    falls back to _STAGE_SEQUENCE, then 50 (middle of pipeline).
    """
    # Check pick_list_values for sequence_number matching this stage
    for plv in pick_list_values or []:
        if plv.get("display_value") == stage_name or plv.get("actual_value") == stage_name:
            seq = plv.get("sequence_number")
            if seq is not None:
                try:
                    return int(seq)
                except (TypeError, ValueError):
                    pass
    return _STAGE_SEQUENCE.get(stage_name, 50)


def analyze_timeline(timeline_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse raw Zoho v9 Timelines entries into structured deal intelligence signals.

    Returns:
    {
        "stage_progression": [...],    # list of stage changes with direction
        "last_email_sent": str | None, # ISO timestamp
        "last_email_subject": str | None,
        "last_email_sent_by": str | None,
        "days_since_last_email": int | None,
        "task_count": int,
        "revenue_changes": [...],
        "automation_events": [...],
        "deal_health_signals": {
            "has_recent_email": bool,
            "stage_moving_forward": bool,
            "has_pending_tasks": bool,
            "revenue_growing": bool,
            "human_activity_ratio": float,
        },
        "total_entries": int,
        "human_entries": int,
        "automation_entries": int,
    }
    """
    stage_progression: List[Dict[str, Any]] = []
    revenue_changes: List[Dict[str, Any]] = []
    automation_events: List[Dict[str, Any]] = []

    last_email_sent: Optional[str] = None
    last_email_subject: Optional[str] = None
    last_email_sent_by: Optional[str] = None

    task_count = 0
    human_entries = 0
    automation_entries = 0

    logger.info("analyze_timeline: received %d entries", len(timeline_entries or []))
    if timeline_entries:
        # Log first entry keys to confirm structure
        sample = timeline_entries[0]
        logger.info(
            "analyze_timeline: sample entry keys=%s action=%s source=%s",
            list(sample.keys()),
            sample.get("action"),
            sample.get("source"),
        )

    for entry in timeline_entries or []:
        action = entry.get("action", "")
        audited_time = entry.get("audited_time", "")
        source = entry.get("source", "crm_ui")
        done_by = entry.get("done_by") or {}
        done_by_name = done_by.get("name", "Unknown")
        record = entry.get("record") or {}
        module = (record.get("module") or {}).get("api_name", "")
        record_name = record.get("name", "")

        is_automation = source in ("workflow", "mass_update", "automation", "blueprint")
        if is_automation:
            automation_entries += 1
        else:
            human_entries += 1

        field_history = entry.get("field_history") or []

        # ── Stage changes ──────────────────────────────────────────────────
        for fh in field_history:
            api_name = fh.get("api_name") or fh.get("field_label", "")
            if api_name not in ("Stage", "stage"):
                continue
            val = fh.get("_value") or {}
            old_stage = val.get("old") or ""
            new_stage = val.get("new") or ""
            if not old_stage or not new_stage or old_stage == new_stage:
                continue

            pick_list_values = fh.get("pick_list_values") or []
            old_pos = _stage_position(old_stage, pick_list_values)
            new_pos = _stage_position(new_stage, pick_list_values)
            direction = "forward" if new_pos > old_pos else "backward"

            # Colour codes from pick_list_values
            old_colour = next(
                (p.get("colour_code", "") for p in pick_list_values if p.get("display_value") == old_stage or p.get("actual_value") == old_stage),
                ""
            )
            new_colour = next(
                (p.get("colour_code", "") for p in pick_list_values if p.get("display_value") == new_stage or p.get("actual_value") == new_stage),
                ""
            )

            stage_progression.append({
                "old_stage": old_stage,
                "new_stage": new_stage,
                "old_colour": old_colour,
                "new_colour": new_colour,
                "direction": direction,
                "changed_by": done_by_name,
                "changed_at": audited_time,
                "days_ago": _days_ago(_parse_dt(audited_time)),
                "source": source,
            })

        # ── Revenue changes ────────────────────────────────────────────────
        for fh in field_history:
            api_name = fh.get("api_name") or ""
            if api_name not in ("Expected_Revenue", "Amount", "Revenue"):
                continue
            val = fh.get("_value") or {}
            actual = fh.get("actual_value") or {}
            try:
                old_v = float(actual.get("old") or val.get("old") or 0)
                new_v = float(actual.get("new") or val.get("new") or 0)
            except (TypeError, ValueError):
                continue
            revenue_changes.append({
                "field": api_name,
                "old_value": old_v,
                "new_value": new_v,
                "direction": "up" if new_v > old_v else "down",
                "changed_by": done_by_name,
                "changed_at": audited_time,
                "days_ago": _days_ago(_parse_dt(audited_time)),
            })

        # ── Email sent events ──────────────────────────────────────────────
        if action in ("sent", "email_notification_sent") or (action == "added" and module == "Emails"):
            if last_email_sent is None or audited_time > last_email_sent:
                last_email_sent = audited_time
                last_email_subject = record_name or None
                last_email_sent_by = done_by_name

        # ── Task events ────────────────────────────────────────────────────
        if module == "Tasks":
            task_count += 1

        # ── Automation events ──────────────────────────────────────────────
        if is_automation:
            automation_events.append({
                "action": action,
                "record_name": record_name,
                "module": module,
                "timestamp": audited_time,
                "days_ago": _days_ago(_parse_dt(audited_time)),
            })

    # ── Compute summary signals ────────────────────────────────────────────

    days_since_last_email: Optional[int] = None
    if last_email_sent:
        days_since_last_email = _days_ago(_parse_dt(last_email_sent))

    has_recent_email = (
        days_since_last_email is not None and days_since_last_email <= 14
    )

    # Forward = at least one forward stage change with no subsequent backward change
    stage_moving_forward = False
    if stage_progression:
        # Look at the most recent stage change
        latest = max(stage_progression, key=lambda s: s.get("changed_at", ""))
        stage_moving_forward = latest["direction"] == "forward"

    revenue_growing = any(r["direction"] == "up" for r in revenue_changes)

    total = human_entries + automation_entries
    human_activity_ratio = human_entries / total if total > 0 else 0.0

    return {
        "stage_progression": stage_progression,
        "last_email_sent": last_email_sent,
        "last_email_subject": last_email_subject,
        "last_email_sent_by": last_email_sent_by,
        "days_since_last_email": days_since_last_email,
        "task_count": task_count,
        "revenue_changes": revenue_changes,
        "automation_events": automation_events,
        "deal_health_signals": {
            "has_recent_email": has_recent_email,
            "stage_moving_forward": stage_moving_forward,
            "has_pending_tasks": task_count > 0,
            "revenue_growing": revenue_growing,
            "human_activity_ratio": round(human_activity_ratio, 2),
        },
        "total_entries": total,
        "human_entries": human_entries,
        "automation_entries": automation_entries,
    }


def enrich_timeline_events(
    existing_events: List[Dict[str, Any]],
    analysis: Dict[str, Any],
    raw_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Convert raw v9 timeline entries into the event format used by build_timeline()
    and merge them with existing events, deduplicating by (type, datetime) proximity.

    Existing events come from deal_timeline.build_timeline() (notes + activities).
    New events come from v9 stage changes, revenue changes, automation entries, emails.
    """
    new_events: List[Dict[str, Any]] = []

    for entry in raw_entries or []:
        action = entry.get("action", "")
        audited_time = entry.get("audited_time", "")
        source = entry.get("source", "crm_ui")
        done_by = entry.get("done_by") or {}
        actor = done_by.get("name", "CRM")
        record = entry.get("record") or {}
        module = (record.get("module") or {}).get("api_name", "")
        record_name = record.get("name", "")
        field_history = entry.get("field_history") or []
        is_automation = source in ("workflow", "mass_update", "automation", "blueprint")
        dt = _parse_dt(audited_time)

        # Stage change events
        for fh in field_history:
            api_name = fh.get("api_name") or fh.get("field_label", "")
            if api_name not in ("Stage", "stage"):
                continue
            val = fh.get("_value") or {}
            old_stage = val.get("old", "")
            new_stage = val.get("new", "")
            if not old_stage or not new_stage or old_stage == new_stage:
                continue

            pick_list_values = fh.get("pick_list_values") or []
            old_colour = next(
                (p.get("colour_code", "") for p in pick_list_values if p.get("display_value") == old_stage or p.get("actual_value") == old_stage),
                ""
            )
            new_colour = next(
                (p.get("colour_code", "") for p in pick_list_values if p.get("display_value") == new_stage or p.get("actual_value") == new_stage),
                ""
            )
            old_pos = _stage_position(old_stage, pick_list_values)
            new_pos = _stage_position(new_stage, pick_list_values)
            direction = "forward" if new_pos > old_pos else "backward"

            new_events.append({
                "type": "stage_change",
                "label": f"Stage: {old_stage} → {new_stage}",
                "detail": f"{'↑' if direction == 'forward' else '↓'} {direction} · by {actor}{'  · via automation' if is_automation else ''}",
                "datetime": audited_time,
                "days_ago": _days_ago(dt),
                "icon": "git-merge",
                "is_automation": is_automation,
                "stage_from": old_stage,
                "stage_to": new_stage,
                "stage_from_colour": old_colour,
                "stage_to_colour": new_colour,
                "direction": direction,
            })

        # Revenue change events
        for fh in field_history:
            api_name = fh.get("api_name") or ""
            if api_name not in ("Expected_Revenue", "Amount"):
                continue
            val = fh.get("_value") or {}
            actual = fh.get("actual_value") or {}
            try:
                old_v = float(actual.get("old") or val.get("old") or 0)
                new_v = float(actual.get("new") or val.get("new") or 0)
            except (TypeError, ValueError):
                continue
            direction = "up" if new_v > old_v else "down"
            new_events.append({
                "type": "revenue_change",
                "label": f"Revenue updated: ${old_v:,.0f} → ${new_v:,.0f} {'▲' if direction == 'up' else '▼'}",
                "detail": f"by {actor}",
                "datetime": audited_time,
                "days_ago": _days_ago(dt),
                "icon": "trending-up" if direction == "up" else "trending-down",
                "is_automation": is_automation,
                "revenue_direction": direction,
                "old_value": old_v,
                "new_value": new_v,
            })

        # Email sent events
        if action in ("sent", "email_notification_sent") or (action == "added" and module == "Emails"):
            label = f"Email: {record_name}" if record_name else "Email sent"
            new_events.append({
                "type": "email",
                "label": label,
                "detail": f"{'Automated' if is_automation else 'Sent'} by {actor}",
                "datetime": audited_time,
                "days_ago": _days_ago(dt),
                "icon": "mail",
                "is_automation": is_automation,
                "email_subject": record_name,
            })

        # Task events (skip if already in existing events by proximity)
        elif module == "Tasks" and action == "added":
            new_events.append({
                "type": "task",
                "label": f"Task: {record_name or 'added'}",
                "detail": f"by {actor}",
                "datetime": audited_time,
                "days_ago": _days_ago(dt),
                "icon": "check-square",
                "is_automation": is_automation,
            })

    # Merge: use existing events as base; add new v9 events that don't duplicate
    existing_datetimes = {
        _parse_dt(e.get("datetime"))
        for e in existing_events
        if _parse_dt(e.get("datetime"))
    }

    merged = list(existing_events)
    for ev in new_events:
        ev_dt = _parse_dt(ev.get("datetime"))
        if ev_dt is None:
            merged.append(ev)
            continue
        # Skip if an existing event is within 60 seconds of same type
        duplicate = any(
            abs((ev_dt - ex_dt).total_seconds()) < 60
            for ex_dt in existing_datetimes
        )
        if not duplicate:
            merged.append(ev)
            existing_datetimes.add(ev_dt)

    # Sort chronologically
    def _sort_key(e: dict):
        dt = _parse_dt(e.get("datetime"))
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    merged.sort(key=_sort_key)
    return merged
