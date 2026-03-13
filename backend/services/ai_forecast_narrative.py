"""
AI Forecast Narrative Engine
============================
Five AI-powered intelligence layers:
1. Pipeline Narrative    — The Monday morning briefing no one has time to write
2. Rep Coaching Cards    — Pattern recognition across each rep's full deal history
3. Rescue Prioritisation — Ranked action list with specific reasoning per deal
4. Rep Deal Patterns     — Why is this rep's at-risk bucket full?
5. Forecast Risk Summary — What could go wrong this month, specifically
"""

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
import json
import re
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


MODEL = "claude-sonnet-4-6"


def _extract_json(text: str) -> Any:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                continue
    raise ValueError(f"No valid JSON in response: {text[:400]}")


def _fmt(val: float) -> str:
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${round(val/1_000)}K"
    return f"${round(val)}"


# ── 1. Pipeline Narrative ─────────────────────────────────────────────────────

async def generate_pipeline_narrative(forecast_data: Dict[str, Any]) -> Dict[str, Any]:
    by_rep = forecast_data.get("by_rep", [])
    rep_summary = "\n".join([
        f"  - {r['name']}: {r['deal_count']} deals | pipeline {_fmt(r['total_pipeline'])} | "
        f"CRM says {_fmt(r['crm_forecast'])} → DealIQ says {_fmt(r['dealiq_forecast'])} | "
        f"avg health {r['avg_health_score']:.0f}/100 | "
        f"{r['healthy_count']}✓ {r['at_risk_count']}⚠ {r['critical_count']}✕ {r['zombie_count']}💀"
        for r in by_rep
    ])

    rescue = forecast_data.get("rescue_opportunities", [])
    rescue_summary = "\n".join([
        f"  - {d['name']} ({d['owner']}): {_fmt(d['amount'])}, closes in {d['days_to_close']}d, health: {d['health_label']}"
        for d in rescue[:5]
    ]) or "  None identified"

    prompt = f"""You are the Chief Revenue Officer of a B2B SaaS company reviewing this week's pipeline data.
Write a pipeline narrative that a VP would actually find useful — specific, honest, and action-oriented.
Do not summarise what the numbers say. Interpret what they MEAN for the business.

═══ PIPELINE DATA ═══
Total pipeline: {_fmt(forecast_data['total_pipeline'])}
CRM forecast (what reps believe): {_fmt(forecast_data['crm_forecast'])}
DealIQ realistic forecast (health-adjusted): {_fmt(forecast_data['dealiq_realistic'])}
Overforecast gap: {_fmt(forecast_data['forecast_gap'])} ({forecast_data['gap_percentage']:.0f}% above realistic)
Deals closing this month: {forecast_data['deals_closing_this_month']}
This month — CRM: {_fmt(forecast_data['this_month_crm'])} vs DealIQ: {_fmt(forecast_data['this_month_dealiq'])}
At-risk deals closing this month: {forecast_data['at_risk_this_month']}
Total deals analysed: {forecast_data['total_deals_analysed']}

═══ REP BREAKDOWN ═══
{rep_summary}

═══ TOP RESCUE OPPORTUNITIES ═══
{rescue_summary}

Return ONLY valid JSON:
{{
  "headline": "One punchy sentence (max 15 words) — the single most important thing leadership needs to hear right now",
  "status": "on_track|at_risk|behind",
  "paragraphs": [
    "Para 1 (2-3 sentences): The real state of the pipeline — CRM vs reality gap, what it means for the quarter. Name specific numbers.",
    "Para 2 (2-3 sentences): The rep-level story — who is over-forecasting, who has the strongest pipeline, who needs attention. Name names.",
    "Para 3 (2-3 sentences): What needs to happen THIS WEEK. Specific deals, specific reps, specific actions. Not general advice."
  ],
  "key_risks": [
    "Risk 1: specific deal or rep pattern that could hurt this month's number",
    "Risk 2: a timing or process risk based on the data",
    "Risk 3: a forecasting accuracy risk"
  ],
  "biggest_opportunity": "The single highest-leverage action — specific deal, specific rep, specific action — that would most move the number"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1400,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a B2B SaaS revenue forecasting expert. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "headline": "AI narrative unavailable",
            "status": "at_risk",
            "paragraphs": [f"Could not generate narrative: {str(e)[:100]}"],
            "key_risks": [],
            "biggest_opportunity": "",
        }


# ── 2. Rep Coaching Cards ─────────────────────────────────────────────────────

async def generate_rep_coaching(rep: Dict[str, Any]) -> Dict[str, Any]:
    deals_by_health = rep.get("deals_by_health", {})
    all_deals_text = []
    for label, deals in deals_by_health.items():
        for d in deals[:8]:
            all_deals_text.append(
                f"  [{label.upper()}] {d['name']} — {_fmt(d['amount'])} — {d['stage']} — health {d['health_score']}/100"
            )

    deals_text = "\n".join(all_deals_text) if all_deals_text else "  No deal details available"

    prompt = f"""You are a high-performance sales coach reviewing a rep's full pipeline. Be direct, honest, and specific.
Do not give generic coaching. Reference actual deal patterns in their pipeline.

═══ REP: {rep['name']} ═══
Total deals: {rep['deal_count']} | Pipeline: {_fmt(rep['total_pipeline'])}
CRM forecast: {_fmt(rep['crm_forecast'])} | DealIQ forecast: {_fmt(rep['dealiq_forecast'])}
Overconfidence gap: {_fmt(rep['overconfidence_gap'])} | Avg health: {rep['avg_health_score']:.0f}/100
Breakdown: {rep['healthy_count']} healthy / {rep['at_risk_count']} at-risk / {rep['critical_count']} critical / {rep['zombie_count']} zombie

═══ DEAL BREAKDOWN ═══
{deals_text}

Return ONLY this JSON:
{{
  "summary": "One sentence that honestly characterises this rep's pipeline situation right now",
  "pattern_identified": "The main pattern across their struggling deals — specific to actual deal names/data (1-2 sentences)",
  "strength": "What their healthy deals have in common — what this rep does well when they close (1 sentence)",
  "coaching_action": "The single highest-impact change this rep should make THIS WEEK — specific, not generic. E.g., not 'follow up more' but 'call {rep['name']}'s zombie deals directly instead of emailing'",
  "priority_deal": "The one deal they must focus on most urgently — name it and explain why in one sentence"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=700,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a B2B sales coach. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "summary": "",
            "pattern_identified": f"Could not generate coaching: {str(e)[:80]}",
            "strength": "",
            "coaching_action": "",
            "priority_deal": "",
        }


# ── 3. Rescue Prioritisation ──────────────────────────────────────────────────

async def generate_rescue_priorities(
    rescue_opportunities: List[Dict[str, Any]],
    total_pipeline: float,
    this_month_gap: float,
) -> Dict[str, Any]:
    if not rescue_opportunities:
        return {"generated": True, "priorities": [], "total_rescue_potential": 0, "strategy": ""}

    # Build deal lines with EXACT computed values — AI must copy these verbatim
    deal_lines = []
    for i, d in enumerate(rescue_opportunities[:8]):
        deal_lines.append(
            f"{i+1}. {d['name']} ({d['owner']})\n"
            f"   Full amount: {_fmt(d['amount'])} (EXACT — do not change)\n"
            f"   Rescue upside: {_fmt(d['rescue_upside'])} (EXACT — copy this value into 'rescue_upside' field)\n"
            f"   Stage: {d['stage']} | Health: {d['health_label']} (score: {d.get('health_score', '?')}) | "
            f"Closes in {d['days_to_close']}d"
        )
    deals_text = "\n".join(deal_lines)

    # Pre-compute total so AI cannot hallucinate it
    computed_total = sum(d["rescue_upside"] for d in rescue_opportunities[:8])

    prompt = f"""You are a sales manager trying to close this month's gap. You have limited time and need to prioritise ruthlessly.

Month's forecast gap to close: {_fmt(this_month_gap)}

AT-RISK DEALS THAT COULD STILL BE SAVED:
{deals_text}

CRITICAL RULES:
- Use ONLY the deal names, amounts, and rescue_upside values shown above. Do NOT invent or estimate any dollar amounts.
- Copy the exact "Rescue upside" figure into the "rescue_upside" field for each priority.
- total_rescue_potential MUST be exactly {_fmt(computed_total)} — do not compute it yourself.
- For each action: be specific — not "follow up" but "send a one-question email: 'Is the legal review blocking us or is something else?'"

Return ONLY this JSON:
{{
  "strategy": "One sentence overall rescue strategy for this month — what's the focus?",
  "total_rescue_potential": {round(computed_total)},
  "priorities": [
    {{
      "rank": 1,
      "deal_name": "exact deal name from the list above",
      "owner": "rep name",
      "rescue_upside": 0,
      "action": "Specific, exact action — what to say, who to contact, which channel. 2 sentences max.",
      "why_this_one": "Why ranked here — probability + urgency reasoning (1 sentence)",
      "urgency": "today|this_week|next_week"
    }}
  ]
}}

Include ALL deals in the priorities array. Be specific — reference actual deal names and situations."""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1600,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a B2B SaaS revenue forecasting expert. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        # Always overwrite with server-computed value — never trust AI math
        result["total_rescue_potential"] = round(computed_total)
        return result
    except Exception as e:
        return {
            "generated": False,
            "strategy": f"Could not generate rescue priorities: {str(e)[:80]}",
            "priorities": [],
            "total_rescue_potential": round(computed_total),
        }


# ── 4. Rep Deal Pattern Analysis ─────────────────────────────────────────────

async def generate_rep_health_pattern(
    rep_name: str,
    health_label: str,
    deals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    deals_text = "\n".join([
        f"  - {d['name']}: {_fmt(d['amount'])}, {d['stage']}, health {d['health_score']}/100"
        for d in deals[:15]
    ])

    label_context = {
        "healthy":  f"These are {rep_name}'s best deals. What are they doing differently here vs their at-risk deals?",
        "at_risk":  f"These deals are in danger. What pattern is causing the stall? What specifically went wrong in each?",
        "critical": f"These deals are nearly dead. What is the common thread? Is anything salvageable?",
        "zombie":   f"These deals are dead weight in the CRM. What does their presence say about {rep_name}'s pipeline hygiene?",
    }.get(health_label, "Analyse these deals for patterns.")

    prompt = f"""Sales performance analysis for {rep_name}'s {health_label.replace('_', '-')} deals.

{label_context}

{health_label.upper()} DEALS ({len(deals)} total, showing top {min(len(deals), 15)}):
{deals_text}

Return ONLY this JSON:
{{
  "pattern": "The main thing these deals have in common — be specific to actual deal names/stages (2 sentences)",
  "insight": "What this pattern reveals about {rep_name}'s selling behaviour or pipeline management (1-2 sentences)",
  "action": "The single most impactful action for {rep_name} or their manager to take on this deal group — specific, not generic (1 sentence)"
}}"""

    try:
        resp = await _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=500,
            temperature=0.3,
            messages=[
                {"role": "system", "content": "You are a B2B sales coach. Return ONLY valid JSON — no markdown, no explanation outside the JSON object."},
                {"role": "user", "content": prompt},
            ],
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "pattern": "",
            "insight": f"Could not analyse pattern: {str(e)[:80]}",
            "action": "",
        }
