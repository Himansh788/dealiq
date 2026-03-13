"""
Daily Digest Service
====================
Generates a prioritised list of today's tasks for a sales rep based on
their active deals. Task generation is stage-aware and enriched with:
  - Health score + label (from health_scorer)
  - Buyer response recency (days since last inbound email via Zoho / Outlook)
  - Last outbound email date (did we already follow up?)
  - Real contact names (from Zoho Contact_Name field)
  - Ghost stakeholder alerts (from activity_intelligence)

Reusable across the Digest page, banner, and email surfaces.
"""

from datetime import datetime, date, timezone
from typing import Optional
import uuid


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

CLOSED_STAGES = {
    "Closed Won", "Closed Lost", "Lost", "Won", "Dead",
}

TASK_TYPE_LABELS = {
    "email":      "Send an email",
    "call":       "Make a phone call",
    "whatsapp":   "Send a WhatsApp / text",
    "case_study": "Prepare a case study",
    "meeting":    "Schedule a meeting",
    "contract":   "Follow up on a contract",
    "re_engage":  "Re-engage a stakeholder",
}

# Health label → urgency multiplier
HEALTH_URGENCY: dict[str, float] = {
    "zombie":   2.0,
    "critical": 1.5,
    "at_risk":  1.1,
    "healthy":  0.7,
}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

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


def _days_since_activity(deal: dict) -> Optional[int]:
    """Best estimate of days since last rep-side or buyer activity."""
    return _days_since(deal.get("last_activity_time")) or _days_since(deal.get("modified_time"))


def _fmt_amount(val) -> str:
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        if v >= 1_000:
            return f"${round(v/1_000)}K"
        return f"${round(v)}"
    except Exception:
        return ""


def _prospect(deal: dict) -> str:
    return deal.get("account_name") or deal.get("company") or deal.get("name", "this prospect")


def _contact(deal: dict) -> str:
    """Best contact name from enrichment or deal fields."""
    # contact_name comes from Zoho map_zoho_deal → Contact_Name field
    cn = deal.get("contact_name")
    if cn and isinstance(cn, str) and cn.strip():
        return cn.strip()
    # contacts list (from activity bundle or enrichment)
    contacts = deal.get("contacts") or []
    if contacts and isinstance(contacts, list) and contacts[0]:
        c = contacts[0]
        if isinstance(c, dict):
            return c.get("name") or c.get("email") or _prospect(deal)
        return str(c)
    return _prospect(deal)


def _days_since_outbound(deal: dict) -> Optional[int]:
    """Days since we last sent an outbound email to this deal."""
    # Set by enrichment: comes from Outlook/Zoho email data
    return deal.get("days_since_last_outbound")


def _days_since_inbound(deal: dict) -> Optional[int]:
    """Days since buyer last replied. Set by enrichment."""
    v = deal.get("days_since_last_inbound")
    if isinstance(v, int) and v < 999:
        return v
    return None


def _health_multiplier(deal: dict) -> float:
    label = deal.get("health_label") or "at_risk"
    return HEALTH_URGENCY.get(label, 1.0)


def _was_followed_up_recently(deal: dict, within_days: int = 2) -> bool:
    """True if we already sent an email to this deal within `within_days`."""
    d = _days_since_outbound(deal)
    return d is not None and d <= within_days


def _buyer_replied_recently(deal: dict, within_days: int = 7) -> bool:
    """True if the buyer replied recently — follow-up may not be needed."""
    d = _days_since_inbound(deal)
    return d is not None and d <= within_days


# --------------------------------------------------------------------------- #
# Stage-based task rules (each returns None if rule doesn't apply)
# --------------------------------------------------------------------------- #

def _rule_sales_approved(deal: dict) -> Optional[dict]:
    if (deal.get("stage") or "").strip() != "Sales Approved Deal":
        return None
    days = _days_since_activity(deal)
    if days is None or days < 14:
        return None
    return {
        "task_type": "meeting",
        "task_text": (
            f"Schedule demo with {_prospect(deal)}. "
            f"No demo booked since meeting {days} days ago."
        ),
        "reason": f"No demo scheduled. Last activity {days} days ago.",
        "urgency": days,
    }


def _rule_demo_done(deal: dict) -> Optional[dict]:
    if (deal.get("stage") or "").strip() != "Demo Done":
        return None
    days = _days_since_activity(deal)
    if days is None or days < 2:
        return None

    # If we already sent a follow-up email recently, skip or soften the task
    if _was_followed_up_recently(deal, within_days=1):
        return None
    if _was_followed_up_recently(deal, within_days=3):
        # Follow-up sent 2-3 days ago — ask them to follow up on response
        d_out = _days_since_outbound(deal)
        return {
            "task_type": "call",
            "task_text": (
                f"Follow up on demo email sent to {_contact(deal)} at {_prospect(deal)} "
                f"{d_out} day(s) ago. No reply yet."
            ),
            "reason": f"Demo follow-up email sent {d_out}d ago — no reply.",
            "urgency": days * 4,
        }

    # If buyer already replied, lower urgency task
    if _buyer_replied_recently(deal, within_days=7):
        d_in = _days_since_inbound(deal)
        return {
            "task_type": "meeting",
            "task_text": (
                f"Schedule next step with {_contact(deal)} at {_prospect(deal)}. "
                f"They replied {d_in} day(s) ago — capitalise on momentum."
            ),
            "reason": f"Buyer replied {d_in}d ago. Lock in next step.",
            "urgency": days * 2,
        }

    return {
        "task_type": "email",
        "task_text": (
            f"Send demo follow-up to {_contact(deal)} at {_prospect(deal)}. "
            f"Demo was {days} days ago with no follow-up sent."
        ),
        "reason": f"Demo done {days} days ago — no follow-up email detected.",
        "urgency": days * 5,
    }


def _rule_proposal(deal: dict) -> Optional[dict]:
    stage = (deal.get("stage") or "").strip()
    if stage not in {"Commercial Proposal", "Proposal/Price Quote", "Proposal"}:
        return None
    days = _days_since_activity(deal)
    if days is None or days < 10:
        return None

    # Buyer replied recently — lower urgency, different task
    if _buyer_replied_recently(deal, within_days=5):
        d_in = _days_since_inbound(deal)
        return {
            "task_type": "meeting",
            "task_text": (
                f"Schedule a follow-up call with {_contact(deal)} at {_prospect(deal)}. "
                f"They responded to the proposal {d_in} day(s) ago — move to next stage."
            ),
            "reason": f"Buyer engaged {d_in}d ago — close the loop.",
            "urgency": days * 2,
        }

    return {
        "task_type": "call",
        "task_text": (
            f"Call {_contact(deal)} at {_prospect(deal)} to follow up on commercial proposal "
            f"sent {days} days ago. No response received."
        ),
        "reason": f"Proposal sent {days} days ago — no response.",
        "urgency": days * 3,
    }


def _rule_evaluation(deal: dict) -> Optional[dict]:
    stage = (deal.get("stage") or "").strip()
    if stage not in {"Evaluation", "Technical Evaluation", "Value Proposition"}:
        return None
    days = _days_since_activity(deal)
    if days is None or days < 14:
        return None
    return {
        "task_type": "case_study",
        "task_text": (
            f"Prepare a relevant case study for {_prospect(deal)} "
            f"to re-engage their technical evaluation. Last contact {days} days ago."
        ),
        "reason": f"Evaluation stalled — no technical contact in {days} days.",
        "urgency": days * 2,
    }


def _rule_negotiation(deal: dict) -> Optional[dict]:
    stage = (deal.get("stage") or "").strip()
    if stage not in {"Negotiation", "Negotiation/Review", "Negotiation ongoing"}:
        return None
    days = _days_since_activity(deal)
    if days is None or days < 21:
        return None

    # Buyer engaged recently — ask for a decision
    if _buyer_replied_recently(deal, within_days=5):
        d_in = _days_since_inbound(deal)
        return {
            "task_type": "contract",
            "task_text": (
                f"Push for a decision with {_contact(deal)} at {_prospect(deal)}. "
                f"They engaged {d_in} day(s) ago — negotiation has been open {days} days."
            ),
            "reason": f"Buyer active {d_in}d ago but negotiation stalled {days}d.",
            "urgency": days * 3,
        }

    return {
        "task_type": "contract",
        "task_text": (
            f"Follow up with {_contact(deal)} at {_prospect(deal)} on negotiation. "
            f"No agreement reached after {days} days. Clarify remaining blockers."
        ),
        "reason": f"Negotiation ongoing for {days} days — no close.",
        "urgency": days * 3,
    }


def _rule_contract_sent(deal: dict) -> Optional[dict]:
    if (deal.get("stage") or "").strip() != "Contract Sent":
        return None
    days = _days_since_activity(deal)
    if days is None or days < 7:
        return None

    # If buyer signed / replied, flag it as a positive action
    if _buyer_replied_recently(deal, within_days=3):
        d_in = _days_since_inbound(deal)
        return {
            "task_type": "call",
            "task_text": (
                f"Call {_contact(deal)} at {_prospect(deal)} — they replied to the contract "
                f"{d_in} day(s) ago. Get verbal confirmation and move to close."
            ),
            "reason": f"Buyer replied to contract {d_in}d ago.",
            "urgency": 90,
        }

    return {
        "task_type": "whatsapp",
        "task_text": (
            f"Send a WhatsApp to {_contact(deal)} at {_prospect(deal)} "
            f"checking on contract status. Sent {days} days ago with no response."
        ),
        "reason": f"Contract sent {days} days ago — no response.",
        "urgency": days * 8,
    }


def _rule_contract_review(deal: dict) -> Optional[dict]:
    stage = (deal.get("stage") or "").strip()
    if stage not in {"Contract Review", "Legal Review"}:
        return None
    days = _days_since_activity(deal)
    if days is None or days < 7:
        return None
    return {
        "task_type": "call",
        "task_text": (
            f"Call {_contact(deal)} at {_prospect(deal)} to move contract review forward. "
            f"No movement in {days} days."
        ),
        "reason": f"Contract review stalled for {days} days.",
        "urgency": days * 6,
    }


_RULES = [
    _rule_sales_approved,
    _rule_demo_done,
    _rule_proposal,
    _rule_evaluation,
    _rule_negotiation,
    _rule_contract_sent,
    _rule_contract_review,
]


# --------------------------------------------------------------------------- #
# Ghost stakeholder tasks
# --------------------------------------------------------------------------- #

def _ghost_tasks(deal: dict) -> list[dict]:
    """Generate re-engagement tasks for ghost stakeholders flagged on this deal."""
    ghosts = deal.get("ghost_stakeholders") or []
    tasks = []
    for ghost in ghosts:
        if isinstance(ghost, dict):
            name = ghost.get("name") or "a key stakeholder"
            days_silent = ghost.get("days_silent") or 0
            role = ghost.get("role") or ""
            role_str = f" ({role})" if role else ""
        else:
            name = str(ghost)
            days_silent = 0
            role_str = ""

        if days_silent < 14:
            continue

        tasks.append({
            "task_type": "re_engage",
            "task_text": (
                f"Re-engage {name}{role_str} at {_prospect(deal)}. "
                f"They've been silent for {days_silent} days — a key stakeholder going dark is a risk signal."
            ),
            "reason": f"Ghost stakeholder: {name}{role_str} silent {days_silent}d.",
            "urgency": min(days_silent * 4, 100),
        })
    return tasks


# --------------------------------------------------------------------------- #
# Main generators
# --------------------------------------------------------------------------- #

def generate_tasks(deals: list[dict], today: str | None = None) -> list[dict]:
    """
    Generate today's prioritised task list from enriched deal objects.
    Each deal may carry enrichment keys:
      - health_label, health_score
      - contact_name
      - days_since_last_outbound (from Outlook / Zoho emails)
      - days_since_last_inbound  (buyer's last reply)
      - ghost_stakeholders       (list of GhostStakeholder dicts)
    """
    if today is None:
        today = date.today().isoformat()

    candidates: list[dict] = []

    for deal in deals:
        stage = (deal.get("stage") or "").strip()
        if stage in CLOSED_STAGES:
            continue

        # Skip deals with zero recent activity — tasks would be noise, not signal.
        # The router's pre-filter already handles this for real mode;
        # this guard is a safety net for demo data / direct calls.
        last_touch = _days_since_activity(deal)
        if last_touch is not None and last_touch > 60:
            continue

        deal_id = deal.get("id") or deal.get("zoho_id") or ""
        amount = deal.get("amount") or 0
        health_mult = _health_multiplier(deal)

        # Stage rules (max one per deal)
        task_result = None
        for rule in _RULES:
            task_result = rule(deal)
            if task_result:
                break

        if task_result:
            urgency = min(round(task_result["urgency"] * health_mult), 100)
            candidates.append({
                "id": str(uuid.uuid4()),
                "deal_id": deal_id,
                "deal_name": deal.get("name") or deal.get("deal_name") or "Unnamed deal",
                "company": deal.get("account_name") or deal.get("company") or "",
                "stage": stage,
                "amount": float(amount) if amount else None,
                "amount_fmt": _fmt_amount(amount) if amount else "",
                "task_type": task_result["task_type"],
                "task_type_label": TASK_TYPE_LABELS.get(task_result["task_type"], task_result["task_type"]),
                "task_text": task_result["task_text"],
                "reason": task_result.get("reason", ""),
                "urgency": urgency,
                "health_label": deal.get("health_label") or "",
                "is_completed": False,
                "completed_at": None,
            })

        # Ghost stakeholder tasks (in addition to stage task)
        for ghost_task in _ghost_tasks(deal):
            urgency = min(round(ghost_task["urgency"] * health_mult), 100)
            candidates.append({
                "id": str(uuid.uuid4()),
                "deal_id": deal_id,
                "deal_name": deal.get("name") or "Unnamed deal",
                "company": deal.get("account_name") or deal.get("company") or "",
                "stage": stage,
                "amount": float(amount) if amount else None,
                "amount_fmt": _fmt_amount(amount) if amount else "",
                "task_type": ghost_task["task_type"],
                "task_type_label": TASK_TYPE_LABELS.get(ghost_task["task_type"], ghost_task["task_type"]),
                "task_text": ghost_task["task_text"],
                "reason": ghost_task.get("reason", ""),
                "urgency": urgency,
                "health_label": deal.get("health_label") or "",
                "is_completed": False,
                "completed_at": None,
            })

    # Sort: urgency desc, then amount desc
    candidates.sort(key=lambda x: (-x["urgency"], -(x["amount"] or 0)))

    # Spread variety: ensure first 5 cover different task types
    seen_types: set[str] = set()
    varied: list[dict] = []
    remainder: list[dict] = []
    for c in candidates:
        if c["task_type"] not in seen_types and len(varied) < 5:
            seen_types.add(c["task_type"])
            varied.append(c)
        else:
            remainder.append(c)

    tasks = varied + remainder
    for i, t in enumerate(tasks):
        t["sort_order"] = i

    return tasks


def generate_untouched_deals(deals: list[dict], limit: int = 10) -> list[dict]:
    """
    Return up to `limit` deals that need attention, sorted by urgency.

    Two tiers:
      Tier 1 (days 14–29): Recently touched but showing warning signs
                           (at_risk / critical health, or no inbound reply)
      Tier 2 (30+ days):   Deals that have gone fully silent

    Within each tier, sort by deal amount descending so the highest-value
    at-risk deals surface first.
    """
    tier1: list[dict] = []
    tier2: list[dict] = []

    for deal in deals:
        stage = (deal.get("stage") or "").strip()
        if stage in CLOSED_STAGES:
            continue

        # Best estimate of last contact — prefer enriched email signals
        days_inbound = _days_since_inbound(deal)
        days_outbound = _days_since_outbound(deal)
        days_activity = _days_since_activity(deal)

        days_options = [d for d in [days_inbound, days_outbound, days_activity] if d is not None]
        if not days_options:
            continue
        days = min(days_options)

        amount = deal.get("amount") or 0
        health = deal.get("health_label") or "at_risk"

        entry = {
            "deal_id": deal.get("id") or deal.get("zoho_id") or "",
            "deal_name": deal.get("name") or deal.get("deal_name") or "Unnamed deal",
            "company": deal.get("account_name") or deal.get("company") or "",
            "stage": stage,
            "amount": float(amount) if amount else None,
            "amount_fmt": _fmt_amount(amount) if amount else "",
            "owner": deal.get("owner") or deal.get("owner_name") or "",
            "days_since_contact": days,
            "health_label": health,
            "suggested_action": _suggest_re_engagement(stage, days, deal),
        }

        if days >= 30:
            tier2.append(entry)
        elif days >= 14 and health in ("zombie", "critical", "at_risk"):
            # Recently touched but health is deteriorating — worth flagging
            tier1.append(entry)

    tier1.sort(key=lambda x: -(x["amount"] or 0))
    tier2.sort(key=lambda x: -(x["amount"] or 0))

    combined = tier1 + tier2
    return combined[:limit]


def _suggest_re_engagement(stage: str, days: int, deal: dict) -> str:
    contact = _contact(deal)
    health = deal.get("health_label") or ""

    if health in ("zombie", "critical"):
        return (
            f"This deal is marked {health}. Call {contact} directly to assess if it's "
            f"still a live opportunity or should be closed out."
        )
    if "Contract" in stage:
        return f"Call {contact} directly — a stalled contract this late is a serious risk."
    if "Negotiation" in stage:
        return (
            f"Email {contact} acknowledging the silence and asking what has changed on their side."
        )
    if "Proposal" in stage or "Evaluation" in stage:
        return (
            f"Send {contact} a re-engagement email with a relevant customer success story or ROI data point."
        )
    if "Demo" in stage:
        return (
            f"Send {contact} a short follow-up asking if they have outstanding questions from the demo."
        )
    return (
        f"Send {contact} a re-engagement email acknowledging the gap and asking if priorities have changed."
    )


def build_digest(deals: list[dict], existing_tasks: list[dict] | None = None) -> dict:
    """
    Build the full digest payload.
    `deals` should be enriched deal objects (health_label, contact_name,
    days_since_last_inbound, days_since_last_outbound, ghost_stakeholders set
    by the router before calling this).
    """
    tasks = generate_tasks(deals)
    untouched = generate_untouched_deals(deals)

    # Merge completion state from persisted tasks
    if existing_tasks:
        done_map = {
            t["deal_id"] + t["task_type"]: t
            for t in existing_tasks
            if t.get("is_completed")
        }
        for t in tasks:
            key = t["deal_id"] + t["task_type"]
            if key in done_map:
                t["is_completed"] = True
                t["completed_at"] = done_map[key].get("completed_at")
                t["id"] = done_map[key]["id"]

    completed = sum(1 for t in tasks if t["is_completed"])

    return {
        "date": date.today().isoformat(),
        "tasks": tasks,
        "untouched_deals": untouched,
        "progress": {"completed": completed, "total": len(tasks)},
    }
