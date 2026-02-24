"""
Alerts Digest Service
======================
Scans the full pipeline and identifies deals that have crossed
danger thresholds — the kind of things a good sales manager notices
by reading every deal every day, but no one actually has time to do.

Alert types:
  - WENT_SILENT      : No activity in 14+ days (was active last week)
  - CLOSING_OVERDUE  : Closing date passed, deal still open
  - CLOSING_URGENT   : Closes in ≤7 days with critical/zombie health
  - WENT_ZOMBIE      : Health dropped to zombie (health_score < 25)
  - STAGE_STUCK      : Deal hasn't progressed in 30+ days
  - NO_NEXT_STEP     : Deal in Negotiation/Proposal with no next step defined
  - HIGH_VALUE_RISK  : Deal worth >$50K with critical/zombie health

Each alert has:
  - type, severity (critical/warning/info)
  - deal_id, deal_name, owner, amount
  - message: specific human-readable description
  - action: one concrete thing to do about it right now
"""

from datetime import datetime, date, timezone, timedelta
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


def generate_digest(deals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Scan all deals and return a structured digest of alerts.
    'deals' should be the scored deal dicts (with health_score, health_label).
    """
    alerts = []
    summary_counts = {"critical": 0, "warning": 0, "info": 0}

    for deal in deals:
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

        def add_alert(alert_type, severity, message, action):
            alerts.append({
                "type": alert_type,
                "severity": severity,
                "deal_id": deal_id,
                "deal_name": name,
                "owner": owner,
                "amount": amount,
                "amount_fmt": _fmt(amount),
                "stage": stage,
                "health_label": health_label,
                "health_score": health_score,
                "message": message,
                "action": action,
                "silence_days": silence_days,
                "days_to_close": days_to_close,
            })
            summary_counts[severity] += 1

        # ── CLOSING OVERDUE ───────────────────────────────────────────────────
        if days_to_close is not None and -30 <= days_to_close < 0:
            overdue_days = abs(days_to_close)
            add_alert(
                "CLOSING_OVERDUE", "critical",
                f"{name} closing date passed {overdue_days} day{'s' if overdue_days != 1 else ''} ago — still open at {stage}",
                f"Update the closing date in CRM or kill the deal. Don't let it inflate the forecast."
            )


        # ── CLOSING URGENT with bad health ────────────────────────────────────
        elif days_to_close is not None and days_to_close <= 7 and health_label in ("critical", "zombie"):
            add_alert(
                "CLOSING_URGENT", "critical",
                f"{name} closes in {days_to_close} day{'s' if days_to_close != 1 else ''} but health is {health_label} (score: {health_score})",
                f"Call {owner} today. One focused re-engagement attempt before writing this off."
            )

        # ── WENT SILENT in active stage ───────────────────────────────────────
        if silence_days >= 21 and stage in ACTIVE_STAGES and health_label != "zombie":
            add_alert(
                "WENT_SILENT", "critical" if silence_days >= 30 else "warning",
                f"{name} has been silent for {silence_days} days — last activity was over 3 weeks ago",
                f"Send a short re-engagement email. Ask one specific question to get a response."
            )
        elif silence_days >= 14 and stage in ACTIVE_STAGES:
            add_alert(
                "WENT_SILENT", "warning",
                f"{name} quiet for {silence_days} days — buyer engagement dropping",
                f"Check in with {owner}. Has the buyer gone dark or is there a blocker?"
            )

        # ── ZOMBIE with money still showing ───────────────────────────────────
        if health_label == "zombie" and amount >= 10_000:
            add_alert(
                "ZOMBIE_IN_FORECAST", "critical",
                f"{name} ({_fmt(amount)}) is zombie health but still showing in forecast — inflating CRM numbers",
                f"Manager review: advance, re-qualify, or kill. Don't let zombie deals distort the pipeline."
            )

        # ── HIGH VALUE at risk ────────────────────────────────────────────────
        if amount >= 50_000 and health_label in ("critical", "zombie"):
            add_alert(
                "HIGH_VALUE_RISK", "critical",
                f"High-value deal {name} ({_fmt(amount)}) has {health_label} health — significant revenue at risk",
                f"Escalate to leadership. Assign an executive sponsor. This deal needs a recovery plan."
            )

        # ── NO NEXT STEP in late stage ────────────────────────────────────────
        if stage in NEXT_STEP_REQUIRED_STAGES and not next_step and health_label in ("at_risk", "critical"):
            add_alert(
                "NO_NEXT_STEP", "warning",
                f"{name} is in {stage} with no next step defined — deal is drifting",
                f"Have {owner} define a concrete next step with a date. 'Following up' is not a next step."
            )

        # ── DEAL AGE — stuck too long ─────────────────────────────────────────
        if deal_age_days >= 60 and health_label in ("at_risk", "critical", "zombie"):
            add_alert(
                "STAGE_STUCK", "warning",
                f"{name} is {deal_age_days} days old with {health_label} health — no progression",
                f"Force a decision: either get a concrete next step this week, or mark as lost."
            )

    # Sort: critical first, then by amount descending
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: (severity_order.get(a["severity"], 2), -a["amount"]))

    # Deduplicate — one deal shouldn't appear in the same severity bucket twice for similar types
    seen_deal_types = set()
    deduped = []
    for a in alerts:
        key = f"{a['deal_id']}:{a['type']}"
        if key not in seen_deal_types:
            seen_deal_types.add(key)
            deduped.append(a)

    critical_alerts = [a for a in deduped if a["severity"] == "critical"]
    warning_alerts  = [a for a in deduped if a["severity"] == "warning"]

    # Top 3 actions — the most important things to do right now
    top_actions = []
    for a in deduped[:5]:
        top_actions.append({
            "deal_name": a["deal_name"],
            "owner": a["owner"],
            "amount_fmt": a["amount_fmt"],
            "action": a["action"],
            "severity": a["severity"],
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_alerts": len(deduped),
        "critical_count": summary_counts["critical"],
        "warning_count": summary_counts["warning"],
        "critical_alerts": critical_alerts[:15],   # cap for UI
        "warning_alerts": warning_alerts[:15],
        "top_actions": top_actions,
        "deals_scanned": len(deals),
    }
