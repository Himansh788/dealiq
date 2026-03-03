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

try:
    from dateutil import parser as dateutil_parser
    _HAS_DATEUTIL = True
except ImportError:
    _HAS_DATEUTIL = False

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

# Workflow automation sources — their emails must NOT count toward rep
# Communication Balance outbound score.
_AUTOMATION_SOURCES = frozenset({"workflow", "mass_update", "automation", "blueprint"})


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 / Zoho timestamp into a timezone-aware UTC datetime.

    Uses dateutil.parser when available for robustness against non-standard
    Zoho timestamp variants (e.g. missing 'T', space separator, various tz
    offsets).  Falls back to stdlib fromisoformat if dateutil is not installed.
    Always converts to UTC so all date-math is apples-to-apples.
    """
    if not s:
        return None
    try:
        if _HAS_DATEUTIL:
            dt = dateutil_parser.parse(str(s))
        else:
            dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        # Normalise to UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
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
    for plv in pick_list_values or []:
        if plv.get("display_value") == stage_name or plv.get("actual_value") == stage_name:
            seq = plv.get("sequence_number")
            if seq is not None:
                try:
                    return int(seq)
                except (TypeError, ValueError):
                    pass
    return _STAGE_SEQUENCE.get(stage_name, 50)


def _extract_value_dict(fh: Dict[str, Any]) -> Dict[str, Any]:
    """Defensively extract the old/new value dict from a field_history entry.

    Zoho sometimes uses '_value' (internal name) and sometimes 'value'.
    Returns an empty dict if neither key is present.
    """
    return fh.get("_value") or fh.get("value") or {}


def _parse_revenue_floats(fh: Dict[str, Any]) -> Optional[tuple]:
    """Return (old_v, new_v) floats from a revenue field_history entry.

    Priority: _value > actual_value (actual_value can carry unrelated numbers
    like probability percentages that produce wrong deltas).
    Returns None if parsing fails.
    """
    val = _extract_value_dict(fh)
    # _value carries the display-accurate numbers; prefer it.
    # actual_value is a fallback only when _value has no old/new keys.
    actual = fh.get("actual_value") or {}
    try:
        raw_old = val.get("old") or actual.get("old") or 0
        raw_new = val.get("new") or actual.get("new") or 0
        return float(raw_old), float(raw_new)
    except (TypeError, ValueError):
        return None


def compute_delta(old_v: float, new_v: float) -> float:
    """Return the signed revenue change (new − old).

    $400 → $1000 == +600.  Used in tests and in label generation.
    """
    return new_v - old_v


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
        "outbound_email_count": int,   # rep-sent only (excludes workflow)
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
    outbound_email_count: int = 0  # rep-sent emails only

    task_count = 0
    human_entries = 0
    automation_entries = 0
    last_human_activity_dt: Optional[datetime] = None  # most recent rep-driven event

    logger.info("analyze_timeline: received %d entries", len(timeline_entries or []))
    if timeline_entries:
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
        # Null-guard record — direct deal-update events have record: null
        record = entry.get("record") or {}
        module = (record.get("module") or {}).get("api_name", "")
        record_name = record.get("name", "")

        is_automation = source in _AUTOMATION_SOURCES
        if is_automation:
            automation_entries += 1
        else:
            human_entries += 1
            # Track most recent human-driven event for Activity Momentum scoring
            _human_actions = {"sent", "added", "updated", "completed"}
            if action in _human_actions and audited_time:
                ev_dt = _parse_dt(audited_time)
                if ev_dt and (last_human_activity_dt is None or ev_dt > last_human_activity_dt):
                    last_human_activity_dt = ev_dt

        # Null-guard field_history — non-update events return null not []
        field_history = entry.get("field_history") or []

        # ── Stage changes ──────────────────────────────────────────────────
        for fh in field_history:
            api_name = fh.get("api_name") or fh.get("field_label", "")
            if api_name not in ("Stage", "stage"):
                continue
            val = _extract_value_dict(fh)
            old_stage = val.get("old") or ""
            new_stage = val.get("new") or ""
            if not old_stage or not new_stage or old_stage == new_stage:
                continue

            pick_list_values = fh.get("pick_list_values") or []
            old_pos = _stage_position(old_stage, pick_list_values)
            new_pos = _stage_position(new_stage, pick_list_values)
            direction = "forward" if new_pos > old_pos else "backward"

            old_colour = next(
                (p.get("colour_code", "") for p in pick_list_values
                 if p.get("display_value") == old_stage or p.get("actual_value") == old_stage),
                ""
            )
            new_colour = next(
                (p.get("colour_code", "") for p in pick_list_values
                 if p.get("display_value") == new_stage or p.get("actual_value") == new_stage),
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
            parsed = _parse_revenue_floats(fh)
            if parsed is None:
                continue
            old_v, new_v = parsed
            delta = compute_delta(old_v, new_v)
            revenue_changes.append({
                "field": api_name,
                "old_value": old_v,
                "new_value": new_v,
                "delta": delta,
                "direction": "up" if delta > 0 else "down",
                "changed_by": done_by_name,
                "changed_at": audited_time,
                "days_ago": _days_ago(_parse_dt(audited_time)),
            })

        # ── Email sent events ──────────────────────────────────────────────
        # action: "sent"                      → rep manually sent an email
        # action: "email_notification_sent"   → workflow / automation email
        # action: "added" + module: "Emails"  → email logged against deal
        #
        # Only "sent" (rep emails) count toward outbound_email_count used in
        # Communication Balance scoring.  Workflow emails are automation noise.
        is_rep_email = (action == "sent") or (action == "added" and module == "Emails")
        is_workflow_email = action == "email_notification_sent"

        if is_rep_email or is_workflow_email:
            if last_email_sent is None or audited_time > last_email_sent:
                last_email_sent = audited_time
                last_email_subject = record_name or None
                last_email_sent_by = done_by_name
            if is_rep_email and not is_automation:
                outbound_email_count += 1

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

    stage_moving_forward = False
    if stage_progression:
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
        "days_since_last_human_activity": _days_ago(last_human_activity_dt),
        "outbound_email_count": outbound_email_count,
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
    _event_counter = 0  # used for synthetic IDs on null-id records

    for entry in raw_entries or []:
        action = entry.get("action", "")
        audited_time = entry.get("audited_time", "")
        source = entry.get("source", "crm_ui")
        done_by = entry.get("done_by") or {}
        actor = done_by.get("name", "CRM")
        # Null-guard record — direct deal-update events have record: null
        record = entry.get("record") or {}
        module = (record.get("module") or {}).get("api_name", "")
        record_name = record.get("name", "")
        # Null-guard record.id — Zoho Email records have id: null
        record_id = record.get("id")
        if record_id is None:
            _event_counter += 1
            record_id = f"synthetic_{_event_counter}"

        # Null-guard field_history — non-update events return null not []
        field_history = entry.get("field_history") or []
        is_automation = source in _AUTOMATION_SOURCES
        dt = _parse_dt(audited_time)

        # Stage change events
        for fh in field_history:
            api_name = fh.get("api_name") or fh.get("field_label", "")
            if api_name not in ("Stage", "stage"):
                continue
            val = _extract_value_dict(fh)
            old_stage = val.get("old", "")
            new_stage = val.get("new", "")
            if not old_stage or not new_stage or old_stage == new_stage:
                continue

            pick_list_values = fh.get("pick_list_values") or []
            old_colour = next(
                (p.get("colour_code", "") for p in pick_list_values
                 if p.get("display_value") == old_stage or p.get("actual_value") == old_stage),
                ""
            )
            new_colour = next(
                (p.get("colour_code", "") for p in pick_list_values
                 if p.get("display_value") == new_stage or p.get("actual_value") == new_stage),
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
            parsed = _parse_revenue_floats(fh)
            if parsed is None:
                continue
            old_v, new_v = parsed
            delta = compute_delta(old_v, new_v)
            direction = "up" if delta > 0 else "down"
            delta_abs = abs(delta)
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
                "delta": delta,
                "delta_abs": delta_abs,
            })

        # Email events
        # action: "sent"                    → rep email (human or via CRM send)
        # action: "email_notification_sent" → workflow automation email
        # action: "added" + Emails module   → email logged against deal
        is_rep_email = (action == "sent") or (action == "added" and module == "Emails")
        is_workflow_email = action == "email_notification_sent"

        if is_rep_email or is_workflow_email:
            label = f"Email: {record_name}" if record_name else "Email sent"
            # Only mark as "Automated" for workflow source — not just because it
            # has is_automation set (a human could trigger a CRM-sent email).
            is_automated_email = is_automation and is_workflow_email
            new_events.append({
                "type": "email",
                "label": label,
                "detail": f"{'Automated' if is_automated_email else 'Sent'} by {actor}",
                "datetime": audited_time,
                "days_ago": _days_ago(dt),
                "icon": "mail",
                "is_automation": is_automated_email,
                "is_rep_email": is_rep_email and not is_automation,
                "email_subject": record_name,
                "record_id": record_id,
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
        # Skip if an existing event is within 60 seconds (dedup by time proximity)
        duplicate = any(
            abs((ev_dt - ex_dt).total_seconds()) < 60
            for ex_dt in existing_datetimes
        )
        if not duplicate:
            merged.append(ev)
            existing_datetimes.add(ev_dt)

    # Sort chronologically (UTC-normalised datetimes, nulls sort to beginning)
    def _sort_key(e: dict):
        dt = _parse_dt(e.get("datetime"))
        return dt or datetime.min.replace(tzinfo=timezone.utc)

    merged.sort(key=_sort_key)
    return merged
