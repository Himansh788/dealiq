"""
AI Forecast Narrative Engine
============================
This is where DealIQ stops being a dashboard and starts being
a VP of Sales who has read every deal in your pipeline.

Five AI-powered intelligence layers:

1. Pipeline Narrative    — The Monday morning briefing no one has time to write
2. Rep Coaching Cards    — Pattern recognition across each rep's full deal history
3. Rescue Prioritisation — Ranked action list with specific reasoning per deal
4. Rep Deal Patterns     — Why is this rep's at-risk bucket full? What's the pattern?
5. Forecast Risk Summary — What could go wrong this month, specifically

All calls are async. Results are returned as structured dicts so the
frontend can render them with full control over layout.
"""

import openai
import json
import re
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

# Lazy client — only created on first AI call, never at import time.
_client: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client
    if _client is None:
        _client = openai.OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1",
        )
    return _client


MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# ── Shared JSON extractor ─────────────────────────────────────────────────────

def _extract_json(text: str) -> Any:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    # Try direct parse first
    try:
        return json.loads(clean)
    except Exception:
        pass
    # Find first JSON object or array
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        match = re.search(pattern, clean, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                continue
    raise ValueError(f"No valid JSON in response: {text[:400]}")


def _fmt(val: float) -> str:
    """Format currency for prompts."""
    if val >= 1_000_000:
        return f"${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"${round(val/1_000)}K"
    return f"${round(val)}"


# ── 1. Pipeline Narrative ─────────────────────────────────────────────────────

async def generate_pipeline_narrative(forecast_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    The VP of Sales Monday morning briefing.
    Reads the full pipeline and writes a 3-paragraph executive summary
    that a CEO could read in 60 seconds and immediately understand
    whether they're going to hit their number this month.
    """
    by_rep = forecast_data.get("by_rep", [])
    rep_summary = "\n".join([
        f"  - {r['name']}: {r['deal_count']} deals, pipeline {_fmt(r['total_pipeline'])}, "
        f"CRM forecast {_fmt(r['crm_forecast'])}, DealIQ says {_fmt(r['dealiq_forecast'])}, "
        f"avg health {r['avg_health_score']:.0f}/100, "
        f"{r['healthy_count']} healthy / {r['at_risk_count']} at-risk / "
        f"{r['critical_count']} critical / {r['zombie_count']} zombie"
        for r in by_rep
    ])

    rescue = forecast_data.get("rescue_opportunities", [])
    rescue_summary = "\n".join([
        f"  - {d['name']} ({d['owner']}): {_fmt(d['amount'])}, {d['days_to_close']}d to close, {d['health_label']}"
        for d in rescue[:5]
    ]) or "  None identified"

    prompt = f"""You are the Head of Revenue at a B2B SaaS company. You have just received this week's pipeline intelligence report. Write a concise, honest, executive briefing.

PIPELINE DATA:
- Total pipeline: {_fmt(forecast_data['total_pipeline'])}
- CRM forecast (what reps believe): {_fmt(forecast_data['crm_forecast'])}
- DealIQ realistic forecast (health-adjusted): {_fmt(forecast_data['dealiq_realistic'])}
- Forecast gap (overestimate): {_fmt(forecast_data['forecast_gap'])} ({forecast_data['gap_percentage']:.0f}% overforecast)
- Deals closing this month: {forecast_data['deals_closing_this_month']}
- This month CRM: {_fmt(forecast_data['this_month_crm'])} vs DealIQ: {_fmt(forecast_data['this_month_dealiq'])}
- At-risk deals closing this month: {forecast_data['at_risk_this_month']}
- Total deals analysed: {forecast_data['total_deals_analysed']}

REP BREAKDOWN:
{rep_summary}

TOP RESCUE OPPORTUNITIES:
{rescue_summary}

Write a JSON response with this exact structure:
{{
  "headline": "One punchy sentence (max 15 words) that captures the single most important thing about this pipeline right now",
  "status": "on_track" | "at_risk" | "critical",
  "paragraphs": [
    "Paragraph 1 (2-3 sentences): Overall pipeline health and the CRM vs reality gap. Be specific with numbers.",
    "Paragraph 2 (2-3 sentences): The rep-level story. Who is over-forecasting? Who has the healthiest pipeline? Name names.",
    "Paragraph 3 (2-3 sentences): What needs to happen this week. Specific deals or reps to focus on. Actionable."
  ],
  "key_risks": ["Risk 1 in one sentence", "Risk 2 in one sentence", "Risk 3 in one sentence"],
  "biggest_opportunity": "The single highest-leverage action the team could take this week"
}}

Be direct. Use real numbers from the data. Do not use generic phrases like 'it is important to'. Write like a VP who has seen 500 pipeline reviews and has no patience for fluff."""

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
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
    """
    Pattern recognition for a single rep's pipeline.
    Looks at the distribution of their deals and identifies
    behavioural patterns — not just 'you have 18 zombies'
    but 'your zombies are concentrated in Demo Done, suggesting
    you're not converting demos to proposals.'
    """
    deals_by_health = rep.get("deals_by_health", {})

    # Build a compact deal list for the prompt
    all_deals_text = []
    for label, deals in deals_by_health.items():
        for d in deals[:8]:  # cap per label to keep prompt tight
            all_deals_text.append(
                f"  [{label.upper()}] {d['name']} — {_fmt(d['amount'])} — Stage: {d['stage']} — Health: {d['health_score']}/100"
            )

    deals_text = "\n".join(all_deals_text) if all_deals_text else "  No deal details available"

    prompt = f"""You are a sales performance coach analysing a rep's pipeline data.

REP: {rep['name']}
Total deals: {rep['deal_count']}
Pipeline value: {_fmt(rep['total_pipeline'])}
CRM forecast: {_fmt(rep['crm_forecast'])}
DealIQ forecast: {_fmt(rep['dealiq_forecast'])}
Overconfidence gap: {_fmt(rep['overconfidence_gap'])}
Average health score: {rep['avg_health_score']:.0f}/100
Health breakdown: {rep['healthy_count']} healthy / {rep['at_risk_count']} at-risk / {rep['critical_count']} critical / {rep['zombie_count']} zombie

DEAL BREAKDOWN:
{deals_text}

Analyse this rep's pipeline and identify:
1. Any stage where deals are getting stuck (concentration in one stage)
2. Whether their zombie/critical deals share a common pattern
3. One specific strength (what are their healthy deals doing right?)
4. One specific behaviour change that would move the needle most

Respond ONLY with this JSON structure:
{{
  "summary": "One sentence characterising this rep's pipeline situation honestly",
  "pattern_identified": "The main pattern you see across their struggling deals (1-2 sentences, be specific)",
  "strength": "What their healthy deals have in common — what is this rep doing right (1 sentence)",
  "coaching_action": "The single most impactful thing this rep should do differently this week (specific, not generic)",
  "priority_deal": "Name of the one deal they should focus on most urgently and why (1 sentence)"
}}"""

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
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
    """
    Takes the list of at-risk deals closing soon and returns
    an AI-ranked priority list with specific reasoning for each.
    Not just 'this deal is at risk' — but 'call this one first
    because the stakeholder was active 4 days ago and the
    contract stage means one nudge could close it.'
    """
    if not rescue_opportunities:
        return {"generated": True, "priorities": [], "total_rescue_potential": 0, "strategy": ""}

    deals_text = "\n".join([
        f"{i+1}. {d['name']} ({d['owner']})\n"
        f"   Amount: {_fmt(d['amount'])} | Stage: {d['stage']} | "
        f"Health: {d['health_label']} (score: {d.get('health_score', '?')}) | "
        f"Days to close: {d['days_to_close']} | "
        f"Rescue upside: {_fmt(d['rescue_upside'])}"
        for i, d in enumerate(rescue_opportunities[:8])
    ])

    prompt = f"""You are a sales manager who needs to help your team recover revenue this month.

CONTEXT:
- This month's forecast gap (likely to miss by): {_fmt(this_month_gap)}
- These are at-risk deals closing soon that could still be saved:

{deals_text}

Your job: rank these deals by rescue priority and explain WHY for each one.
Prioritise based on: days remaining, amount, health label, stage (later stage = easier to close), rescue upside.

Respond ONLY with this JSON:
{{
  "strategy": "One sentence overall rescue strategy for this month",
  "total_rescue_potential": <sum of rescue_upside values for top 3 deals as a number>,
  "priorities": [
    {{
      "rank": 1,
      "deal_name": "exact deal name",
      "owner": "rep name",
      "amount": <number>,
      "action": "Specific action to take — what to say, who to call, what to send (2 sentences max)",
      "why_this_one": "Why this deal is ranked here — what signal makes it worth prioritising (1 sentence)",
      "urgency": "today" | "this_week" | "before_month_end"
    }}
  ]
}}

Include all deals but rank them. Be specific in the action — not 'follow up' but 'send a one-question email asking if the legal review is complete.'"""

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=1400,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        result = _extract_json(resp.choices[0].message.content)
        result["generated"] = True
        return result
    except Exception as e:
        return {
            "generated": False,
            "strategy": f"Could not generate rescue priorities: {str(e)[:80]}",
            "priorities": [],
            "total_rescue_potential": 0,
        }


# ── 4. Rep Deal Pattern Analysis (for drill-down) ────────────────────────────

async def generate_rep_health_pattern(
    rep_name: str,
    health_label: str,
    deals: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Called when a user clicks a health badge on a rep card.
    Analyses the specific group of deals (e.g. Vijendra's 49 at-risk deals)
    and finds the common pattern.
    """
    deals_text = "\n".join([
        f"  - {d['name']}: {_fmt(d['amount'])}, Stage: {d['stage']}, Health: {d['health_score']}/100"
        for d in deals[:15]
    ])

    label_context = {
        "healthy":  "These are the rep's best deals. What are they doing right?",
        "at_risk":  "These deals are in danger. What pattern is causing the risk?",
        "critical": "These deals are nearly dead. What went wrong and can anything be saved?",
        "zombie":   "These deals are effectively dead but still in the CRM. What should happen?",
    }.get(health_label, "Analyse these deals.")

    prompt = f"""Sales coach analysing {rep_name}'s {health_label.replace('_', '-')} deals.

{label_context}

DEALS ({len(deals)} total, showing top {min(len(deals), 15)}):
{deals_text}

Respond ONLY with this JSON:
{{
  "pattern": "The main thing these deals have in common — stage, amount range, timing, or behaviour pattern (2 sentences)",
  "insight": "What this pattern tells us about {rep_name}'s selling behaviour or where deals are getting stuck (1-2 sentences)",
  "action": "The one thing {rep_name} or their manager should do about this group of deals (1 sentence, specific)"
}}"""

    try:
        resp = _get_client().chat.completions.create(
            model=MODEL,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
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
