"""
Alerts Digest Service
======================
Scans the full pipeline and identifies deals that have crossed
danger thresholds — the kind of things a good sales manager notices
by reading every deal every day, but no one actually has time to do.

Alert types:
  - WENT_SILENT      : No activity in 14+ days
  - CLOSING_OVERDUE  : Closing date passed, deal still open
  - CLOSING_URGENT   : Closes in ≤7 days with critical/zombie health
  - ZOMBIE_IN_FORECAST: Zombie health deal inflating pipeline
  - HIGH_VALUE_RISK  : Deal worth >$50K with critical/zombie health
  - NO_NEXT_STEP     : Deal in Negotiation/Proposal with no next step defined
  - STAGE_STUCK      : Deal old with no health progression

Each alert has:
  - type, severity (critical/warning/info)
  - deal_id, deal_name, owner, amount
  - message: specific human-readable description
  - action: one concrete thing to do about it right now

Consolidation: one alert per deal (highest severity wins, all types listed).
Dead deal detection: 90+ days silent AND 30+ days overdue → "mark as lost" advice.
"""

from datetime import datetime, date, timezone
from typing import List, Dict, Any, Optional


def _days_since(dt_str: Optional[str]) -> Optional[int]:
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None


def _days_to_close(closing_date: Optional[str]) -> Optional[int]:
    if not closing_date:
        return None
    try:
        d = date.fromisoformat(closing_date)
        return (d - date.today()).days
    except Exception:
        return None


def _fmt(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${round(val/1_000)}K"
    return f"${round(val)}"


# Stages where silence is more alarming
ACTIVE_STAGES = {
    "Proposal/Price Quote", "Negotiation/Review", "Negotiation",
    "Value Proposition", "Id. Decision Makers", "Proposal",
    "Contract Sent", "Demo Done", "Sales Approved Deal",
}

# Stages where a next step should always be defined
NEXT_STEP_REQUIRED_STAGES = {
    "Proposal/Price Quote", "Negotiation/Review", "Negotiation",
    "Contract Sent", "Proposal",
}

_SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _classify_deal_status(silence_days: int, days_to_close: Optional[int], health_score: int) -> str:
    """Classify deal into an honest status tier for action generation."""
    dtc = days_to_close if days_to_close is not None else 9999
    if silence_days >= 90 and dtc < -30:
        return "dead"
    if silence_days >= 150:
        return "dead"
    if silence_days >= 60 or (dtc < -30 and health_score < 50):
        return "zombie"
    if silence_days >= 21 or dtc < 0:
        return "at_risk"
    return "active"


def _build_action(
    alert_types: List[str],
    deal_status: str,
    name: str,
    owner: str,
    stage: str,
    amount: float,
    silence_days: int,
    days_to_close: Optional[int],
    amount_fmt: str,
) -> str:
    """Generate a single honest, context-aware action string."""
    dtc = days_to_close if days_to_close is not None else 9999

    if deal_status == "dead":
        overdue_str = f"{abs(dtc)} days past close date" if dtc < 0 else "close date unknown"
        return (
            f"Mark {name} as lost. Silent {silence_days} days and {overdue_str}. "
            f"Free up {owner}'s pipeline — move to a nurture list or close it out."
        )

    if deal_status == "zombie":
        if dtc < -30:
            return (
                f"{name} is {abs(dtc)} days past close with no activity. "
                f"Send ONE final 'break-up' email to {owner}'s contact: 'Should I close this out?' "
                f"If no response in 5 days, mark as lost."
            )
        return (
            f"Pipeline review needed for {name}. "
            f"Send ONE final 'break-up' message: 'Haven't heard back — should I close this out?' "
            f"No response in 5 days? Mark as lost."
        )

    # Contextual actions for active/at_risk deals
    if "HIGH_VALUE_RISK" in alert_types and amount >= 50_000:
        return (
            f"{name} ({amount_fmt}) is at risk. Get {owner}'s manager involved — "
            f"this deal needs an executive sponsor and a recovery plan this week."
        )

    if "CLOSING_OVERDUE" in alert_types or "CLOSING_URGENT" in alert_types:
        if dtc < -30:
            return (
                f"{name} is {abs(dtc)} days past close date. Either get a real new timeline "
                f"from the buyer this week, or mark as lost to clean the forecast."
            )
        if dtc < 0:
            return (
                f"{name} closing date passed {abs(dtc)} day{'s' if abs(dtc) != 1 else ''} ago — "
                f"still in {stage}. Update the close date in CRM or kill the deal."
            )
        return (
            f"Call the buyer at {name} today. Be direct: "
            f"'We had this closing by [date] — are we still on track?' Closes in {dtc} days."
        )

    if "WENT_SILENT" in alert_types:
        return (
            f"Re-engage {name} this week — silent {silence_days} days. "
            f"Don't send 'just checking in'. Reference the last conversation "
            f"and ask one specific question to get a response."
        )

    if "STAGE_STUCK" in alert_types:
        return (
            f"{name} has been in {stage} too long. "
            f"Ask for a specific next step with a date: "
            f"'Can we schedule [next milestone] for this week?' Force a decision."
        )

    if "NO_NEXT_STEP" in alert_types:
        return (
            f"Have {owner} define a concrete next step with a date for {name}. "
            f"'Following up' is not a next step."
        )

    if "ZOMBIE_IN_FORECAST" in alert_types:
        return (
            f"Manager review: {name} ({amount_fmt}) has zombie health but is inflating the forecast. "
            f"Advance, re-qualify, or kill this deal."
        )

    return f"Review {name} with {owner} and agree on a concrete next step this week."


def _collect_deal_alerts(deal: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return all raw alert dicts for a single deal (before consolidation)."""
    raw: List[Dict[str, Any]] = []

    deal_id = deal.get("id", "")
    name = deal.get("name") or deal.get("deal_name", "Unknown Deal")
    owner = deal.get("owner", "Unknown")
    amount = float(deal.get("amount") or 0)
    stage = deal.get("stage", "Unknown")
    health_score = deal.get("health_score", 50)
    health_label = deal.get("health_label", "at_risk")
    closing_date = deal.get("closing_date")
    last_activity = deal.get("last_activity_time")
    created_time = deal.get("created_time")
    next_step = deal.get("next_step", "")

    silence_days = _days_since(last_activity) or _days_since(created_time) or 0
    days_to_close = _days_to_close(closing_date)
    deal_age_days = _days_since(created_time) or 0
    amount_fmt = _fmt(amount)

    def _add(alert_type: str, severity: str, message: str) -> None:
        raw.append({
            "type": alert_type,
            "severity": severity,
            "deal_id": deal_id,
            "deal_name": name,
            "owner": owner,
            "amount": amount,
            "amount_fmt": amount_fmt,
            "stage": stage,
            "health_label": health_label,
            "health_score": health_score,
            "silence_days": silence_days,
            "days_to_close": days_to_close,
            "message": message,
        })

    # ── CLOSING OVERDUE ────────────────────────────────────────────────────────
    if days_to_close is not None and days_to_close < 0:
        overdue_days = abs(days_to_close)
        _add(
            "CLOSING_OVERDUE", "critical",
            f"{name} closing date passed {overdue_days} day{'s' if overdue_days != 1 else ''} ago — still open at {stage}",
        )

    # ── CLOSING URGENT with bad health ────────────────────────────────────────
    elif days_to_close is not None and days_to_close <= 7 and health_label in ("critical", "zombie"):
        _add(
            "CLOSING_URGENT", "critical",
            f"{name} closes in {days_to_close} day{'s' if days_to_close != 1 else ''} but health is {health_label} (score: {health_score})",
        )

    # ── WENT SILENT in active stage ───────────────────────────────────────────
    if silence_days >= 21 and stage in ACTIVE_STAGES:
        _add(
            "WENT_SILENT",
            "critical" if silence_days >= 30 else "warning",
            f"{name} has been silent for {silence_days} days",
        )
    elif silence_days >= 14 and stage in ACTIVE_STAGES:
        _add(
            "WENT_SILENT", "warning",
            f"{name} quiet for {silence_days} days — buyer engagement dropping",
        )

    # ── ZOMBIE in forecast ─────────────────────────────────────────────────────
    if health_label == "zombie" and amount >= 10_000:
        _add(
            "ZOMBIE_IN_FORECAST", "critical",
            f"{name} ({amount_fmt}) is zombie health but still showing in forecast",
        )

    # ── HIGH VALUE at risk ─────────────────────────────────────────────────────
    if amount >= 50_000 and health_label in ("critical", "zombie"):
        _add(
            "HIGH_VALUE_RISK", "critical",
            f"High-value deal {name} ({amount_fmt}) has {health_label} health — significant revenue at risk",
        )

    # ── NO NEXT STEP in late stage ────────────────────────────────────────────
    if stage in NEXT_STEP_REQUIRED_STAGES and not next_step and health_label in ("at_risk", "critical"):
        _add(
            "NO_NEXT_STEP", "warning",
            f"{name} is in {stage} with no next step defined — deal is drifting",
        )

    # ── DEAL AGE — stuck too long ──────────────────────────────────────────────
    if deal_age_days >= 60 and health_label in ("at_risk", "critical", "zombie"):
        _add(
            "STAGE_STUCK", "warning",
            f"{name} is {deal_age_days} days old with {health_label} health — no progression",
        )

    return raw


def _consolidate(raw_alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Collapse multiple alerts for the same deal into ONE consolidated alert.
    Picks the highest severity, merges all types, generates a single action.
    """
    by_deal: Dict[str, List[Dict[str, Any]]] = {}
    for a in raw_alerts:
        by_deal.setdefault(a["deal_id"], []).append(a)

    consolidated: List[Dict[str, Any]] = []
    for deal_id, deal_alerts in by_deal.items():
        # Sort: critical first, then highest amount
        deal_alerts.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 2), -a["amount"]))
        primary = deal_alerts[0]

        all_types = list(dict.fromkeys(a["type"] for a in deal_alerts))
        silence_days = primary["silence_days"]
        days_to_close = primary["days_to_close"]
        health_score = primary["health_score"]

        deal_status = _classify_deal_status(silence_days, days_to_close, health_score)

        action = _build_action(
            alert_types=all_types,
            deal_status=deal_status,
            name=primary["deal_name"],
            owner=primary["owner"],
            stage=primary["stage"],
            amount=primary["amount"],
            silence_days=silence_days,
            days_to_close=days_to_close,
            amount_fmt=primary["amount_fmt"],
        )

        # Build a combined summary message
        issues = []
        if silence_days >= 14:
            issues.append(f"silent {silence_days}d")
        if days_to_close is not None and days_to_close < 0:
            issues.append(f"overdue {abs(days_to_close)}d")
        elif days_to_close is not None and days_to_close <= 7:
            issues.append(f"closes in {days_to_close}d")
        if "HIGH_VALUE_RISK" in all_types:
            issues.append(f"high value ({primary['amount_fmt']})")
        if "STAGE_STUCK" in all_types:
            issues.append(f"stuck in {primary['stage']}")
        if "ZOMBIE_IN_FORECAST" in all_types:
            issues.append("zombie in forecast")

        combined_msg = primary["message"]
        if len(issues) > 1:
            combined_msg = f"{primary['deal_name']} — {', '.join(issues)}"

        consolidated.append({
            "type": all_types[0],          # primary type
            "alert_types": all_types,       # all types for UI display
            "severity": primary["severity"],
            "deal_id": deal_id,
            "deal_name": primary["deal_name"],
            "owner": primary["owner"],
            "amount": primary["amount"],
            "amount_fmt": primary["amount_fmt"],
            "stage": primary["stage"],
            "health_label": primary["health_label"],
            "health_score": primary["health_score"],
            "silence_days": silence_days,
            "days_to_close": days_to_close,
            "deal_status": deal_status,
            "message": combined_msg,
            "action": action,
        })

    # Sort: critical first, then by amount descending
    consolidated.sort(key=lambda a: (_SEVERITY_ORDER.get(a["severity"], 2), -a["amount"]))
    return consolidated


def generate_digest(deals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Scan all deals and return a structured digest of alerts.
    'deals' should be the scored deal dicts (with health_score, health_label).
    """
    raw_alerts: List[Dict[str, Any]] = []
    for deal in deals:
        raw_alerts.extend(_collect_deal_alerts(deal))

    # Consolidate: one alert per deal
    consolidated = _consolidate(raw_alerts)

    # Count by severity after consolidation
    critical_count = sum(1 for a in consolidated if a["severity"] == "critical")
    warning_count = sum(1 for a in consolidated if a["severity"] == "warning")

    critical_alerts = [a for a in consolidated if a["severity"] == "critical"]
    warning_alerts = [a for a in consolidated if a["severity"] == "warning"]

    # Top 5 actions — one per deal, highest priority first, deduplicated by deal_id
    top_actions = []
    for a in consolidated[:5]:
        top_actions.append({
            "deal_id": a["deal_id"],
            "deal_name": a["deal_name"],
            "owner": a["owner"],
            "amount_fmt": a["amount_fmt"],
            "action": a["action"],
            "severity": a["severity"],
            "alert_types": a["alert_types"],
            "deal_status": a["deal_status"],
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_alerts": len(consolidated),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "critical_alerts": critical_alerts[:15],
        "warning_alerts": warning_alerts[:15],
        "top_actions": top_actions,
        "deals_scanned": len(deals),
    }
