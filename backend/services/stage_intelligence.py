"""
Stage Intelligence — Single Source of Truth
============================================
Defines the full DealIQ sales pipeline with:
  - Stage definitions and expected behaviour
  - Time thresholds for flag generation
  - Next action templates
  - Flag condition checkers

Referenced by: health_scorer.py, deal_health_ai.py, routers/deals.py
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class StageFlag:
    flag_type: str           # "overdue" | "no_followup" | "no_response" | etc.
    severity: str            # "critical" | "warning"
    message: str             # Plain English explanation shown on deal card
    days_threshold: Optional[int] = None


@dataclass
class StageConfig:
    name: str
    stage_number: int
    definition: str
    benchmark_days: int              # Expected days at this stage (velocity scoring)
    primary_goal: str                # One-sentence goal of this stage
    flag_conditions: List[dict] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    paths_out: List[str] = field(default_factory=list)


# ── Stage Configuration ─────────────────────────────────────────────────────────

STAGE_CONFIGS: Dict[str, StageConfig] = {

    "Sales Approved Deal": StageConfig(
        name="Sales Approved Deal",
        stage_number=1,
        definition=(
            "Deal was created after meeting the prospect at an event. "
            "A full demo has not been given yet. Exclusively for event-sourced deals."
        ),
        benchmark_days=10,
        primary_goal="Convert the event meeting into a formal demo as quickly as possible.",
        paths_out=["Demo Done"],
        flag_conditions=[
            {
                "type": "no_demo_scheduled",
                "days": 14,
                "severity": "critical",
                "message": (
                    "This deal has been in Sales Approved Deal for {days_in_stage} days with no demo "
                    "scheduled or completed. Event-sourced leads go cold fast — schedule a demo "
                    "immediately or the window will close."
                ),
            },
            {
                "type": "no_followup_email",
                "days": 3,
                "severity": "warning",
                "message": (
                    "No follow-up email sent within 3 days of the event. The prospect's memory of your "
                    "conversation is fading — send a personalised follow-up and propose a specific demo time."
                ),
            },
        ],
        next_actions=[
            "Send a personalised follow-up email within 3 days of the event.",
            "Propose 2-3 specific demo time slots — not an open-ended 'let me know when you're free'.",
            "Confirm the demo on the calendar before moving to the next stage.",
        ],
    ),

    "Demo Done": StageConfig(
        name="Demo Done",
        stage_number=2,
        definition=(
            "Full product demo has been given to the prospect. Two paths: "
            "Path A — prospect asks for commercial proposal → move to Commercial Proposal. "
            "Path B — prospect asks for API docs/sandbox without commercials → move to Evaluation directly."
        ),
        benchmark_days=14,
        primary_goal="Identify which path the prospect is on (commercial or technical) and move accordingly.",
        paths_out=["Commercial Proposal", "Evaluation"],
        flag_conditions=[
            {
                "type": "no_movement",
                "days": 21,
                "severity": "critical",
                "message": (
                    "This deal has been in Demo Done for {days_in_stage} days with no movement. "
                    "Deals that stall here usually indicate the prospect lost internal support or was "
                    "never a real opportunity. Force a path decision today."
                ),
            },
            {
                "type": "no_followup_email",
                "days": 2,
                "severity": "critical",
                "message": (
                    "No follow-up email sent within 48 hours of the demo. A demo without a follow-up "
                    "loses most of its impact — send a summary of what was shown and a clear next step now."
                ),
            },
        ],
        next_actions=[
            "Send a demo follow-up email within 48 hours summarising key points and pain points identified.",
            "Ask directly: 'Would you like commercial pricing, or would you prefer to explore the API first?'",
            "Based on their answer, move to Commercial Proposal (Path A) or Evaluation (Path B).",
            "Do not leave deals in Demo Done without a defined next step.",
        ],
    ),

    "Commercial Proposal": StageConfig(
        name="Commercial Proposal",
        stage_number=3,
        definition=(
            "Prospect has asked for pricing. Commercial proposal has been sent. "
            "Sandbox credentials and API documentation are also sent at this stage. "
            "Both commercial and technical materials are now with the prospect."
        ),
        benchmark_days=21,
        primary_goal="Generate a response that reveals whether the prospect is moving toward evaluation or negotiation.",
        paths_out=["Evaluation", "Negotiation"],
        flag_conditions=[
            {
                "type": "no_response",
                "days": 10,
                "severity": "critical",
                "message": (
                    "No response from prospect within 10 days of sending the commercial proposal. "
                    "Proposals that go unanswered this long typically mean the prospect is comparing "
                    "alternatives or the internal champion has lost momentum. Send a follow-up with a "
                    "specific question — not a generic 'any questions?'."
                ),
            },
            {
                "type": "no_movement",
                "days": 30,
                "severity": "critical",
                "message": (
                    "This deal has been in Commercial Proposal for {days_in_stage} days with no movement. "
                    "At 30 days, a stalled proposal is usually a soft no. Schedule a direct conversation — "
                    "ask plainly whether they are still evaluating or if priorities have shifted."
                ),
            },
        ],
        next_actions=[
            "Follow up on the commercial proposal with a specific question about pricing review.",
            "Ask if they have explored the sandbox and if any technical questions have come up.",
            "If no response after 10 days, send a re-engagement email referencing the proposal specifically.",
        ],
    ),

    "Evaluation": StageConfig(
        name="Evaluation",
        stage_number=4,
        definition=(
            "Prospect is actively evaluating the product technically. They have API documentation and "
            "sandbox credentials. Can be reached directly from Demo Done (technical-first path) or "
            "after Commercial Proposal."
        ),
        benchmark_days=30,
        primary_goal="Surface any blockers — technical, commercial, or internal — before moving to negotiation.",
        paths_out=["Negotiation"],
        flag_conditions=[
            {
                "type": "no_technical_questions",
                "days": 14,
                "severity": "critical",
                "message": (
                    "No technical questions or feedback received within 14 days of sending credentials. "
                    "Evaluation deals stall here when the prospect's technical team is not actually running "
                    "the evaluation. Schedule a technical follow-up call to unblock the evaluation."
                ),
            },
            {
                "type": "buyer_silent",
                "days": 14,
                "severity": "critical",
                "message": (
                    "Prospect has gone silent during evaluation — no emails, questions, or meeting requests "
                    "in {days_since_activity} days. This is the most common point where deals die quietly. "
                    "Reach out with a specific technical question or offer a sandbox walkthrough call."
                ),
            },
            {
                "type": "evaluation_too_long",
                "days": 45,
                "severity": "critical",
                "message": (
                    "Evaluation has exceeded 45 days with no movement toward negotiation. "
                    "Evaluations that run this long typically have an unresolved internal blocker — "
                    "budget approval, competing priorities, or an unengaged decision maker. "
                    "Escalate to your champion and ask what needs to happen to move forward."
                ),
            },
        ],
        next_actions=[
            "Schedule a technical follow-up call within 14 days of sending credentials.",
            "Ask for specific feedback: which API parts they have tested, any integration issues.",
            "If silent for 14+ days, send a re-engagement email with a direct technical question.",
            "Identify any blockers — technical, commercial, or internal — and address them explicitly.",
        ],
    ),

    "Negotiation": StageConfig(
        name="Negotiation",
        stage_number=5,
        definition=(
            "Evaluation is complete. Prospect has initiated a follow-up conversation about pricing or "
            "contract terms. Genuine buying intent is confirmed here. If the prospect went through "
            "Evaluation without seeing commercials, the commercial discussion happens here for the first time."
        ),
        benchmark_days=14,
        primary_goal="Clearly document agreed commercials before moving to Contract Sent.",
        paths_out=["Contract Sent"],
        flag_conditions=[
            {
                "type": "negotiation_too_long",
                "days": 21,
                "severity": "critical",
                "message": (
                    "Negotiation has been ongoing for {days_in_stage} days without reaching agreement. "
                    "Negotiations that exceed 21 days typically have an unresolved commercial term or a "
                    "decision maker who hasn't approved the deal. Identify the specific sticking point "
                    "and escalate if needed."
                ),
            },
            {
                "type": "discount_requests",
                "count": 2,
                "severity": "warning",
                "message": (
                    "Prospect has asked for a discount more than twice without a counter-proposal from our "
                    "side. Repeated discount requests without a counter signal the rep is not controlling "
                    "the negotiation. Link any concession to a specific ask from the buyer."
                ),
            },
        ],
        next_actions=[
            "Document the agreed commercials: final price, payment terms, contract duration.",
            "Get explicit confirmation from the prospect in writing before sending the contract.",
            "Do not send the contract until commercial terms are confirmed by both sides.",
            "If stuck on a term, identify whether it is a real blocker or a negotiating tactic.",
        ],
    ),

    # Legacy Zoho stage name — same position as Negotiation
    "Negotiation/Review": StageConfig(
        name="Negotiation/Review",
        stage_number=5,
        definition=(
            "Evaluation is complete. Prospect has initiated a follow-up conversation about pricing or "
            "contract terms. Genuine buying intent is confirmed here."
        ),
        benchmark_days=14,
        primary_goal="Clearly document agreed commercials before moving to Contract Sent.",
        paths_out=["Contract Sent"],
        flag_conditions=[
            {
                "type": "negotiation_too_long",
                "days": 21,
                "severity": "critical",
                "message": (
                    "Negotiation has been ongoing for {days_in_stage} days without reaching agreement. "
                    "Identify the specific sticking point and escalate if needed."
                ),
            },
            {
                "type": "discount_requests",
                "count": 2,
                "severity": "warning",
                "message": (
                    "Prospect has requested discounts multiple times without a counter-proposal. "
                    "Link any concession to a specific ask from the buyer."
                ),
            },
        ],
        next_actions=[
            "Document the agreed commercials: final price, payment terms, contract duration.",
            "Get explicit written confirmation from the prospect before sending the contract.",
        ],
    ),

    "Contract Sent": StageConfig(
        name="Contract Sent",
        stage_number=6,
        definition=(
            "Commercial terms have been agreed by both parties. Initial contract draft has been sent. "
            "Prospect may respond with redlines. Deal stays here until redlines are received or "
            "contract is accepted as-is."
        ),
        benchmark_days=14,
        primary_goal="Get a response to the contract — either acceptance or redlines.",
        paths_out=["Contract Review", "Closed Won"],
        flag_conditions=[
            {
                "type": "no_response",
                "days": 14,
                "severity": "critical",
                "message": (
                    "No response to the contract within 14 days of sending. Contracts that go "
                    "unacknowledged this long suggest the deal has stalled internally — budget freeze, "
                    "legal backlog, or the champion has lost support. Follow up directly and ask if "
                    "there is a specific reason for the delay."
                ),
            },
            {
                "type": "no_movement",
                "days": 30,
                "severity": "critical",
                "message": (
                    "Deal has been in Contract Sent for {days_in_stage} days. Escalate to your champion "
                    "or their legal team. If no progress after 35 days, this deal is at serious risk of going dead."
                ),
            },
        ],
        next_actions=[
            "Follow up on the contract within 7 days if no response.",
            "If redlines received, move immediately to Contract Review.",
            "If no response after 14 days, escalate to your champion directly.",
        ],
    ),

    "Contract Review": StageConfig(
        name="Contract Review",
        stage_number=7,
        definition=(
            "Prospect has sent back redlines and both parties are reviewing contract clauses. "
            "Commercial terms are agreed — this stage is purely about legal and contractual language. "
            "NOTE: This stage must be created manually in Zoho CRM."
        ),
        benchmark_days=14,
        primary_goal="Resolve all redlines and reach a signed agreement.",
        paths_out=["Closed Won", "Closed Lost"],
        flag_conditions=[
            {
                "type": "review_too_long",
                "days": 21,
                "severity": "critical",
                "message": (
                    "Contract Review has exceeded 21 days with no resolution. Protracted contract "
                    "reviews typically indicate a clause that neither party wants to escalate. "
                    "Set a deadline for both parties and escalate to legal on any unresolved clause."
                ),
            },
            {
                "type": "no_communication",
                "days": 7,
                "severity": "critical",
                "message": (
                    "No communication for more than 7 days during contract review. Contract reviews "
                    "that go silent almost always indicate an internal blocker. Reach out immediately "
                    "to understand what changed."
                ),
            },
        ],
        next_actions=[
            "Address redlines clause by clause — do not send an entirely new draft without tracking changes.",
            "Set a clear deadline for both parties to finalise the contract.",
            "If a clause cannot be agreed, escalate to legal or a decision maker.",
            "Confirm both parties' signatures before moving to Closed Won.",
        ],
    ),

    "Closed Won": StageConfig(
        name="Closed Won",
        stage_number=8,
        definition="Contract signed by both parties. Deal is won.",
        benchmark_days=0,
        primary_goal="Trigger handoff to onboarding and log final commercials for benchmarking.",
        paths_out=[],
        flag_conditions=[],
        next_actions=[
            "Trigger handoff to onboarding team immediately.",
            "Log the final agreed commercials for future pricing benchmarks.",
        ],
    ),

    "Closed Lost": StageConfig(
        name="Closed Lost",
        stage_number=8,
        definition="Deal abandoned — prospect went silent, budget cancelled, or competitor chosen.",
        benchmark_days=0,
        primary_goal="Capture the loss reason explicitly for future learning.",
        paths_out=[],
        flag_conditions=[],
        next_actions=[
            "Capture the loss reason: Lost to competitor / Budget cancelled / No decision made / "
            "Technical fit issue / Commercial terms not agreed / Prospect went silent.",
        ],
    ),
}

# ── Pipeline stage order (for regression detection) ────────────────────────────

PIPELINE_STAGE_ORDER = [
    "Sales Approved Deal",
    "Demo Done",
    "Commercial Proposal",
    "Evaluation",
    "Negotiation",
    "Negotiation/Review",
    "Contract Sent",
    "Contract Review",
    "Closed Won",
    "Closed Lost",
]

# ── Dashboard display order and labels ─────────────────────────────────────────

PIPELINE_DISPLAY_STAGES = [
    "Sales Approved Deal",
    "Demo Done",
    "Commercial Proposal",
    "Evaluation",
    "Negotiation",
    "Negotiation/Review",   # show alongside Negotiation if both present
    "Contract Sent",
    "Contract Review",
]


# ── Helper functions ────────────────────────────────────────────────────────────

def get_stage_config(stage: str) -> Optional[StageConfig]:
    """Returns the StageConfig for a given stage name, or None if not found."""
    return STAGE_CONFIGS.get(stage)


def get_stage_benchmark(stage: str) -> int:
    """Returns the benchmark days for a stage. Default 14 if unknown."""
    config = STAGE_CONFIGS.get(stage)
    return config.benchmark_days if config else 14


def get_stage_flags(
    stage: str,
    days_in_stage: Optional[int],
    days_since_activity: Optional[int],
    discount_mention_count: int = 0,
) -> List[StageFlag]:
    """
    Evaluate all flag conditions for a deal and return any triggered flags.
    Returns an empty list if the stage is not configured or no conditions are met.
    """
    config = STAGE_CONFIGS.get(stage)
    if not config:
        return []

    flags: List[StageFlag] = []

    for condition in config.flag_conditions:
        flag_type = condition["type"]
        severity = condition["severity"]
        template = condition["message"]

        # Time-based overdue conditions
        if flag_type in (
            "no_movement", "no_demo_scheduled", "negotiation_too_long",
            "review_too_long", "evaluation_too_long",
        ):
            threshold = condition.get("days", 0)
            if days_in_stage is not None and days_in_stage > threshold:
                message = template.format(
                    days_in_stage=days_in_stage,
                    days_since_activity=days_since_activity or "unknown",
                )
                flags.append(StageFlag(
                    flag_type=flag_type, severity=severity,
                    message=message, days_threshold=threshold,
                ))

        # Silence / no-response conditions
        elif flag_type in (
            "buyer_silent", "no_technical_questions", "no_communication",
            "no_response", "no_followup_email",
        ):
            threshold = condition.get("days", 0)
            silence = days_since_activity
            if silence is not None and silence > threshold:
                message = template.format(
                    days_in_stage=days_in_stage or "unknown",
                    days_since_activity=silence,
                )
                flags.append(StageFlag(
                    flag_type=flag_type, severity=severity,
                    message=message, days_threshold=threshold,
                ))

        # Count-based conditions (e.g. repeated discount requests)
        elif flag_type == "discount_requests":
            count_threshold = condition.get("count", 2)
            if discount_mention_count >= count_threshold:
                flags.append(StageFlag(
                    flag_type=flag_type, severity=severity,
                    message=template, days_threshold=None,
                ))

    return flags


def get_stage_context_for_ai(stage: str, days_in_stage: Optional[int] = None) -> str:
    """
    Returns a plain-English stage context block to inject into AI prompts.
    Tells the AI what normally happens at this stage and what to look for.
    """
    config = STAGE_CONFIGS.get(stage)
    if not config:
        return f"Stage: {stage} (no definition on file — assess based on deal signals only)."

    lines = [
        f"## Stage Context: {config.name} (Stage {config.stage_number}/8)",
        f"Definition: {config.definition}",
        f"Primary goal at this stage: {config.primary_goal}",
        f"Benchmark: deals should spend approximately {config.benchmark_days} days here.",
    ]

    if days_in_stage is not None and config.benchmark_days > 0:
        ratio = days_in_stage / config.benchmark_days
        if ratio > 2.5:
            lines.append(
                f"ALERT: This deal is {days_in_stage} days in this stage — "
                f"{int(ratio)}x over the benchmark. This is a serious velocity warning."
            )
        elif ratio > 1.5:
            lines.append(
                f"WARNING: This deal is {days_in_stage} days in this stage — "
                f"over the {config.benchmark_days}-day benchmark."
            )

    if config.paths_out:
        lines.append(f"Expected next stages: {', '.join(config.paths_out)}")

    if config.next_actions:
        lines.append("Expected next actions at this stage:")
        for action in config.next_actions[:3]:
            lines.append(f"  - {action}")

    return "\n".join(lines)
