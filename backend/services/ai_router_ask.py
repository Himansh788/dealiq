"""
AI Router for Ask DealIQ
========================
Wraps Groq (primary) for Ask DealIQ tasks.
Matches the existing claude_client.py / ai_rep.py pattern exactly.
"""

from services.ai_client import AsyncAnthropicCompat as AsyncGroq
import json
import re
import os
from typing import Dict, Any

_client: AsyncGroq | None = None


def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = AsyncGroq(api_key=api_key)
    return _client


def is_configured() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


# Model selection — quality tasks use the larger model
MODEL_QUALITY = "claude-sonnet-4-5-20250929"   # deal Q&A, MEDDIC, brief
MODEL_FAST = "claude-haiku-4-5-20251001"        # cross-deal summaries, follow-up email


def _extract_json(text: str) -> Dict[str, Any]:
    clean = re.sub(r"```json\s*|\s*```", "", text).strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"No JSON found in AI response: {text[:300]}")


async def ask_deal_question(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
) -> Dict[str, Any]:
    """Route deal Q&A to quality model. Returns parsed JSON dict."""
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL_QUALITY,
            max_tokens=max_tokens,
            temperature=0.15,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return _extract_json(raw)
    except Exception as e:
        return {"error": str(e), "generated": False}


async def generate_structured_analysis(
    system_prompt: str,
    context: str,
    max_tokens: int = 3000,
) -> Dict[str, Any]:
    """Route analysis tasks (MEDDIC, deal brief) to quality model."""
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL_QUALITY,
            max_tokens=max_tokens,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return _extract_json(raw)
    except Exception as e:
        return {"error": str(e), "generated": False}


async def generate_email_draft(
    system_prompt: str,
    context: str,
    max_tokens: int = 2000,
) -> Dict[str, Any]:
    """Route email generation to quality model — richer context requires better reasoning.
    response_format=json_object enforces valid JSON and prevents parse errors."""
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL_QUALITY,
            max_tokens=max_tokens,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return _extract_json(raw)
    except Exception as e:
        return {"error": str(e), "generated": False}


async def ask_pipeline_question(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
) -> Dict[str, Any]:
    """Route cross-deal pipeline queries to fast model (smaller context, structured)."""
    try:
        response = await _get_client().chat.completions.create(
            model=MODEL_FAST,
            max_tokens=max_tokens,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        return _extract_json(raw)
    except Exception as e:
        return {"error": str(e), "generated": False}
