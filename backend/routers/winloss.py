from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional, Literal
import asyncio
import base64
import json
import os
from datetime import datetime, timezone
from groq import AsyncGroq

router = APIRouter()

# In-memory store — persists across requests, resets on server restart
_winloss_store: list[dict] = []

DEAL_PATTERNS = [
    "pricing_issue", "champion_lost", "no_urgency", "competitor_win",
    "single_threaded", "budget_cut", "good_execution", "multi_threaded",
    "strong_champion", "urgency_created",
]

# Cap on auto-analyzed Zoho deals per board request to avoid rate limits
AUTO_ANALYZE_CAP = 10


def _decode_session(authorization: str) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")
    token = authorization.replace("Bearer ", "").strip()
    try:
        payload = json.loads(base64.b64decode(token).decode())
        return payload
    except Exception:
        pass
    if len(token) > 10:
        return {"user_id": "zoho_user", "display_name": "Zoho User", "email": "", "access_token": token, "refresh_token": ""}
    raise HTTPException(status_code=401, detail="Invalid session token")


def _is_demo(session: dict) -> bool:
    return session.get("access_token") == "DEMO_MODE"


def _get_groq_client() -> AsyncGroq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set")
    return AsyncGroq(api_key=api_key)


def _classify_outcome(stage: str) -> Optional[str]:
    """Return 'won', 'lost', or None for an active deal based on Zoho stage name."""
    s = stage.lower()
    if "closed won" in s or s == "won":
        return "won"
    if "closed lost" in s or s == "lost":
        return "lost"
    return None


class AnalyzeRequest(BaseModel):
    deal_id: str
    outcome: Literal["won", "lost"]
    notes: Optional[str] = None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


async def _call_groq_full(deal_json: dict, outcome: str, deal_name: str) -> dict:
    """Full analysis prompt (used for manual /analyze calls)."""
    client = _get_groq_client()
    signals_key = "success_signals" if outcome == "won" else "warning_signs_missed"

    prompt = f"""Analyze this B2B SaaS deal outcome.

Deal data: {json.dumps(deal_json, indent=2)}
Outcome: {outcome.upper()}
Deal name: {deal_name}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "primary_reason": "one clear sentence explaining the main reason for this outcome",
  "contributing_factors": ["factor 1", "factor 2", "factor 3"],
  "{signals_key}": ["signal 1", "signal 2", "signal 3"],
  "deal_pattern": "exactly one of: pricing_issue, champion_lost, no_urgency, competitor_win, single_threaded, budget_cut, good_execution, multi_threaded, strong_champion, urgency_created",
  "lesson": "one actionable sentence for future deals"
}}"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
    )
    return json.loads(_strip_json_fences(response.choices[0].message.content))


async def _call_groq_lightweight(deal: dict, outcome: str) -> dict:
    """Lighter prompt for auto-detected Zoho closed deals."""
    client = _get_groq_client()
    name = deal.get("name", "Unknown")
    amount = deal.get("amount", 0)
    description = deal.get("description") or deal.get("next_step") or ""
    stage = deal.get("stage", "")

    prompt = f"""This B2B deal was {outcome.upper()}.
Deal name: {name}, Amount: ${amount}, Stage: {stage}, Notes: {description}

Return ONLY valid JSON:
{{
  "primary_reason": "one sentence",
  "contributing_factors": ["factor 1", "factor 2"],
  "deal_pattern": "one of: pricing_issue, champion_lost, no_urgency, competitor_win, single_threaded, budget_cut, good_execution, multi_threaded, strong_champion, urgency_created",
  "lesson": "one actionable sentence"
}}"""

    response = await client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300,
    )
    return json.loads(_strip_json_fences(response.choices[0].message.content))


def _normalize_pattern(analysis: dict, outcome: str) -> dict:
    pattern = analysis.get("deal_pattern", "")
    if pattern not in DEAL_PATTERNS:
        analysis["deal_pattern"] = "good_execution" if outcome == "won" else "no_urgency"
    return analysis


@router.post("/analyze")
async def analyze_outcome(
    body: AnalyzeRequest,
    authorization: str = Header(default=""),
):
    """Analyze a deal outcome with Groq and store the result."""
    session = _decode_session(authorization)
    is_demo = _is_demo(session) or body.deal_id.startswith("sim_")

    if is_demo:
        from services.demo_data import SIMULATED_DEALS
        deal = next((d for d in SIMULATED_DEALS if d["id"] == body.deal_id), None)
        if not deal:
            deal = {
                "id": body.deal_id,
                "name": "Demo Deal",
                "stage": "Closed",
                "amount": 50000,
                "probability": 0 if body.outcome == "lost" else 100,
                "description": "Demo deal",
            }
    else:
        from services.zoho_client import fetch_single_deal
        access_token = session.get("access_token", "")
        try:
            deal = await fetch_single_deal(access_token, body.deal_id) or {}
        except Exception:
            deal = {"id": body.deal_id, "name": body.deal_id}

    if body.notes:
        deal = {**deal, "additional_context": body.notes}

    deal_name = deal.get("name", body.deal_id)

    try:
        analysis = await _call_groq_full(deal, body.outcome, deal_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI analysis failed: {str(e)}")

    analysis = _normalize_pattern(analysis, body.outcome)

    entry = {
        "deal_id": body.deal_id,
        "deal_name": deal_name,
        "amount": deal.get("amount", 0),
        "outcome": body.outcome,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "auto_detected": False,
        **analysis,
    }

    global _winloss_store
    _winloss_store = [e for e in _winloss_store if e["deal_id"] != body.deal_id]
    _winloss_store.append(entry)

    return entry


@router.get("/board")
async def get_board(
    authorization: str = Header(default=""),
):
    """
    Return all analyzed deals grouped by outcome with pattern summary.
    Also auto-detects and lightly analyzes Zoho Closed Won/Lost deals
    that haven't been manually marked yet. Capped at AUTO_ANALYZE_CAP.
    """
    session = _decode_session(authorization)
    is_demo = _is_demo(session)

    already_analyzed_ids = {e["deal_id"] for e in _winloss_store}

    # ── Auto-detect closed deals from Zoho / demo ─────────────────────────────
    auto_entries: list[dict] = []
    auto_analyzed_count = 0

    try:
        if is_demo:
            from services.demo_data import SIMULATED_DEALS
            all_deals = SIMULATED_DEALS
        else:
            from services.zoho_client import fetch_deals, map_zoho_deal
            access_token = session.get("access_token", "")
            raw = await fetch_deals(access_token, page=1, per_page=200)
            all_deals = [map_zoho_deal(r) for r in raw] if raw else []

        # For demo mode: classify by health score since demo deals don't have
        # "Closed Won"/"Closed Lost" stage labels.
        closed_deals: list[tuple[dict, str]] = []  # (deal, outcome)
        for deal in all_deals:
            deal_id = deal.get("id", "")
            if deal_id in already_analyzed_ids:
                continue

            if is_demo:
                score = deal.get("health_score") or deal.get("probability", 50)
                if score >= 75:
                    closed_deals.append((deal, "won"))
                elif score < 25:
                    closed_deals.append((deal, "lost"))
            else:
                outcome = _classify_outcome(deal.get("stage", ""))
                if outcome:
                    closed_deals.append((deal, outcome))

        # Analyze in parallel — cap to avoid rate limits
        to_analyze = closed_deals[:AUTO_ANALYZE_CAP]

        async def _analyze_one(deal: dict, outcome: str) -> Optional[dict]:
            try:
                analysis = await _call_groq_lightweight(deal, outcome)
                analysis = _normalize_pattern(analysis, outcome)
                return {
                    "deal_id": deal.get("id", f"auto_{deal.get('name', 'unknown')}"),
                    "deal_name": deal.get("name", "Unknown Deal"),
                    "amount": deal.get("amount", 0),
                    "outcome": outcome,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "auto_detected": True,
                    **analysis,
                }
            except Exception:
                return None

        results = await asyncio.gather(
            *[_analyze_one(d, o) for d, o in to_analyze],
            return_exceptions=False,
        )
        auto_entries = [r for r in results if r is not None]
        auto_analyzed_count = len(auto_entries)

    except Exception:
        # Board still works if Zoho/Groq fails — just shows manual entries
        pass

    # Merge: manual store takes priority (auto entries for IDs not in manual store)
    manual_ids = {e["deal_id"] for e in _winloss_store}
    merged = list(_winloss_store) + [e for e in auto_entries if e["deal_id"] not in manual_ids]

    won = [e for e in merged if e["outcome"] == "won"]
    lost = [e for e in merged if e["outcome"] == "lost"]

    def _pattern_counts(entries: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for e in entries:
            p = e.get("deal_pattern", "unknown")
            counts[p] = counts.get(p, 0) + 1
        return counts

    def _avg_amount(entries: list[dict]) -> float:
        amounts = [e.get("amount", 0) for e in entries if e.get("amount")]
        return round(sum(amounts) / len(amounts)) if amounts else 0

    def _top_pattern(counts: dict) -> str:
        if not counts:
            return ""
        return max(counts, key=lambda k: counts[k])

    won_patterns = _pattern_counts(won)
    lost_patterns = _pattern_counts(lost)

    return {
        "summary": {
            "won": {
                "count": len(won),
                "avg_amount": _avg_amount(won),
                "top_pattern": _top_pattern(won_patterns),
                "pattern_counts": won_patterns,
            },
            "lost": {
                "count": len(lost),
                "avg_amount": _avg_amount(lost),
                "top_pattern": _top_pattern(lost_patterns),
                "pattern_counts": lost_patterns,
            },
        },
        "deals": merged,
        "auto_analyzed_count": auto_analyzed_count,
    }
