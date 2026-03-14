"""
AI Analysis Cache — PostgreSQL-first persistence layer.

Every feature that needs AI analysis for a deal goes through this service.
PostgreSQL is the primary cache (persistent). Redis is burst protection only (60s TTL).

Usage:
    from services.ai_cache import get_or_generate, build_input_hash

    result = await get_or_generate(
        deal_id="12345",
        analysis_type="health_analysis",
        input_hash=build_input_hash({"stage": "Proposal", "amount": 50000}),
        generator=lambda: generate_deal_health_analysis(...),
        result_text_fn=lambda r: r.get("analysis_summary", ""),
        model_used="claude-sonnet-4-6",
    )
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# ANALYSIS VERSIONS — Bump when you change a prompt or schema
# ══════════════════════════════════════════════════════════════

ANALYSIS_VERSIONS = {
    "health_analysis":       1,   # deal_health_ai.py
    "nba":                   1,   # ai_rep.py — Next Best Action
    "email_draft":           1,   # ai_rep.py — email draft
    "objection":             1,   # ai_rep.py — objection handler
    "call_brief":            1,   # ai_rep.py — pre-call brief
    "mismatch":              1,   # claude_client.py — narrative mismatch
    "discount":              1,   # claude_client.py — discount analysis
    "deal_insights":         1,   # claude_client.py — deal AI insights
    "email_coach":           1,   # email_coach.py — live email coaching
    "deal_autopsy":          1,   # deal_autopsy.py — post-mortem
    "pipeline_narrative":    1,   # ai_forecast_narrative.py
    "rep_coaching":          1,   # ai_forecast_narrative.py
    "rescue_priorities":     1,   # ai_forecast_narrative.py
    "rep_health_pattern":    1,   # ai_forecast_narrative.py
    "ask_deal":              1,   # ask_dealiq_service.py
    "ask_meddic":            1,   # ask_dealiq_service.py
    "ask_brief":             1,   # ask_dealiq_service.py
    "ask_follow_up":         1,   # ask_dealiq_service.py
    "signal_detection":      1,   # signal_detector.py
    "smart_tracker":         1,   # smart_tracker.py
    "transcript_analysis":   1,   # transcript_analyzer.py
    "battlecard":            1,   # battlecard.py
    "next_steps":            1,   # next_steps.py
    "win_loss":              1,   # winloss.py
}

# User-scoped: result depends on which mailbox was queried
USER_SCOPED_TYPES = {"email_coach", "mismatch"}

# Time-scoped: result depends on date
TIME_SCOPED_TYPES = {"pipeline_narrative", "rescue_priorities"}

# Types that should NOT be cached (interactive/unique per request)
SKIP_CACHE_TYPES = {"email_coach", "email_draft", "objection", "ask_deal"}


# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

async def get_or_generate(
    deal_id: str,
    analysis_type: str,
    input_hash: str,
    generator: Callable[[], Awaitable[dict]],
    scope_key: str = "__global__",
    result_text_fn: Optional[Callable[[dict], str]] = None,
    model_used: str = None,
) -> dict:
    """
    High-level API: check cache, return if valid, else generate + save.

    Args:
        deal_id: Zoho deal ID or identifier
        analysis_type: Key from ANALYSIS_VERSIONS
        input_hash: SHA-256 of relevant input data
        generator: Async callable that produces the AI result (only called on cache miss)
        scope_key: "__global__" for shared, "user:xxx" for user-scoped
        result_text_fn: Optional fn to extract a text summary from the result
        model_used: Model identifier for metadata tracking
    """
    if analysis_type in SKIP_CACHE_TYPES:
        return await generator()

    # 1. Check Redis burst cache (60s)
    burst_key = f"dealiq:ai_cache:{deal_id}:{analysis_type}:{scope_key}:{input_hash[:12]}"
    burst = await _redis_burst_check(burst_key)
    if burst is not None:
        logger.debug("ai_cache BURST HIT: deal=%s type=%s", deal_id, analysis_type)
        return burst

    # 2. Check PostgreSQL
    cached = await _db_get_cached(deal_id, analysis_type, input_hash, scope_key)
    if cached is not None:
        await _redis_burst_set(burst_key, cached)
        return cached

    # 3. Cache miss — generate
    t0 = time.time()
    result = await generator()
    gen_ms = int((time.time() - t0) * 1000)

    # 4. Save to PostgreSQL + Redis
    result_text = result_text_fn(result) if result_text_fn and result else None
    await _db_save(
        deal_id=deal_id,
        analysis_type=analysis_type,
        scope_key=scope_key,
        result=result,
        result_text=result_text,
        input_hash=input_hash,
        model_used=model_used,
        generation_ms=gen_ms,
    )
    await _redis_burst_set(burst_key, result)

    return result


async def get_cached_analysis(
    deal_id: str,
    analysis_type: str,
    input_hash: str,
    scope_key: str = "__global__",
) -> Optional[dict]:
    """Direct cache lookup — returns the result dict or None."""
    return await _db_get_cached(deal_id, analysis_type, input_hash, scope_key)


async def save_analysis(
    deal_id: str,
    analysis_type: str,
    result: dict,
    input_hash: str,
    scope_key: str = "__global__",
    result_text: str = None,
    model_used: str = None,
    generation_ms: int = None,
) -> None:
    """Direct save — for callers that manage their own generate flow."""
    await _db_save(
        deal_id=deal_id,
        analysis_type=analysis_type,
        scope_key=scope_key,
        result=result,
        result_text=result_text,
        input_hash=input_hash,
        model_used=model_used,
        generation_ms=generation_ms,
    )


async def get_all_analyses_for_deal(deal_id: str) -> dict:
    """
    Get ALL persisted analyses for a deal in one DB call.
    Returns: {"health_analysis": {"result": {...}, "text": "..."}, ...}

    Used for compound intelligence — later features use earlier analyses as context.
    """
    from database.connection import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return {}

    try:
        from sqlalchemy import select
        from database.models import DealAICache

        async with AsyncSessionLocal() as session:
            stmt = select(
                DealAICache.analysis_type,
                DealAICache.result,
                DealAICache.result_text,
            ).where(DealAICache.deal_id == deal_id)
            rows = (await session.execute(stmt)).all()

        return {
            row.analysis_type: {
                "result": row.result,
                "text": row.result_text,
            }
            for row in rows
        }
    except Exception as e:
        logger.warning("get_all_analyses_for_deal failed deal=%s: %s", deal_id, e)
        return {}


async def invalidate_deal(deal_id: str) -> int:
    """Invalidate ALL cached analyses for a deal (e.g., after CRM field update)."""
    from database.connection import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return 0

    try:
        from sqlalchemy import delete
        from database.models import DealAICache

        async with AsyncSessionLocal() as session:
            stmt = delete(DealAICache).where(DealAICache.deal_id == deal_id)
            result = await session.execute(stmt)
            await session.commit()
            count = result.rowcount
            logger.info("ai_cache INVALIDATED: deal=%s entries=%d", deal_id, count)
            return count
    except Exception as e:
        logger.warning("invalidate_deal failed deal=%s: %s", deal_id, e)
        return 0


def build_input_hash(data: dict) -> str:
    """
    Create a deterministic SHA-256 hash of input data.
    Only include fields that actually affect the AI output.
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()


async def build_prior_context(deal_id: str, requested_types: list[str] = None) -> str:
    """
    Build a compact text block from all cached analyses for a deal.
    Used to feed pre-computed intelligence into downstream prompts.

    Args:
        deal_id: The deal to look up
        requested_types: Optional list of analysis types to include.
            If None, includes all available.

    Returns:
        A formatted string like:
            PRE-COMPUTED INTELLIGENCE:
            [HEALTH ANALYSIS]: Health score 54, declining...
            [NBA]: Recommended: Send follow-up email...
        Or empty string if nothing cached.
    """
    cached = await get_all_analyses_for_deal(deal_id)
    if not cached:
        return ""

    # Label mapping for readable prompt sections
    LABELS = {
        "health_analysis": "HEALTH ANALYSIS",
        "nba": "NEXT BEST ACTION",
        "call_brief": "CALL BRIEF",
        "deal_autopsy": "DEAL AUTOPSY",
        "deal_insights": "DEAL INSIGHTS",
        "discount": "DISCOUNT ANALYSIS",
        "mismatch": "NARRATIVE MISMATCH",
        "ask_meddic": "MEDDIC ANALYSIS",
        "ask_brief": "DEAL BRIEF",
        "signal_detection": "BUYING SIGNALS",
        "smart_tracker": "TRACKER MATCHES",
        "transcript_analysis": "TRANSCRIPT ANALYSIS",
    }

    sections = []
    for atype, data in cached.items():
        if requested_types and atype not in requested_types:
            continue
        label = LABELS.get(atype, atype.upper().replace("_", " "))
        # Prefer result_text (compact summary); fall back to truncated JSON
        text = data.get("text")
        if not text and data.get("result"):
            result = data["result"]
            # Extract common summary fields
            text = (
                result.get("analysis_summary")
                or result.get("summary")
                or result.get("situation_read")
                or result.get("recommendation")
                or result.get("cause_of_death")
                or result.get("headline")
                or json.dumps(result, default=str)[:400]
            )
        if text:
            sections.append(f"[{label}]: {text[:500]}")

    if not sections:
        return ""

    return "PRE-COMPUTED INTELLIGENCE (from prior analyses):\n" + "\n".join(sections)


def get_scope_key(analysis_type: str, user_key: str = None, period: str = None) -> str:
    """Determine scope key based on analysis type."""
    if analysis_type in USER_SCOPED_TYPES and user_key:
        return f"user:{user_key.replace(':', '_')}"
    if analysis_type in TIME_SCOPED_TYPES:
        from datetime import date
        return f"date:{period or date.today().isoformat()}"
    return "__global__"


# ══════════════════════════════════════════════════════════════
# INTERNAL: PostgreSQL operations
# ══════════════════════════════════════════════════════════════

async def _db_get_cached(
    deal_id: str,
    analysis_type: str,
    input_hash: str,
    scope_key: str,
) -> Optional[dict]:
    """Check PostgreSQL for a valid cached analysis."""
    from database.connection import AsyncSessionLocal
    if AsyncSessionLocal is None:
        return None

    expected_version = ANALYSIS_VERSIONS.get(analysis_type, 1)

    try:
        from sqlalchemy import select
        from database.models import DealAICache

        async with AsyncSessionLocal() as session:
            stmt = select(DealAICache).where(
                DealAICache.deal_id == deal_id,
                DealAICache.analysis_type == analysis_type,
                DealAICache.scope_key == scope_key,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()

        if not row:
            logger.debug("ai_cache MISS: no entry deal=%s type=%s", deal_id, analysis_type)
            return None

        if row.analysis_version != expected_version:
            logger.info(
                "ai_cache STALE (version): deal=%s type=%s cached_v=%s want_v=%s",
                deal_id, analysis_type, row.analysis_version, expected_version,
            )
            return None

        if row.input_hash != input_hash:
            logger.info(
                "ai_cache STALE (data): deal=%s type=%s hash=%s->%s",
                deal_id, analysis_type, row.input_hash[:8], input_hash[:8],
            )
            return None

        age = datetime.now(timezone.utc) - (row.updated_at.replace(tzinfo=timezone.utc) if row.updated_at.tzinfo is None else row.updated_at)
        logger.info("ai_cache HIT: deal=%s type=%s age=%s", deal_id, analysis_type, age)
        return row.result

    except Exception as e:
        logger.warning("ai_cache DB read failed deal=%s type=%s: %s", deal_id, analysis_type, e)
        return None


async def _db_save(
    deal_id: str,
    analysis_type: str,
    scope_key: str,
    result: dict,
    result_text: Optional[str],
    input_hash: str,
    model_used: Optional[str] = None,
    generation_ms: Optional[int] = None,
) -> None:
    """Upsert an analysis result into PostgreSQL."""
    from database.connection import AsyncSessionLocal, IS_POSTGRES
    if AsyncSessionLocal is None:
        return

    version = ANALYSIS_VERSIONS.get(analysis_type, 1)

    try:
        from sqlalchemy import select
        from database.models import DealAICache

        async with AsyncSessionLocal() as session:
            stmt = select(DealAICache).where(
                DealAICache.deal_id == deal_id,
                DealAICache.analysis_type == analysis_type,
                DealAICache.scope_key == scope_key,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if existing:
                existing.result = result
                existing.result_text = result_text
                existing.input_hash = input_hash
                existing.analysis_version = version
                existing.model_used = model_used
                existing.generation_ms = generation_ms
                existing.updated_at = datetime.now(timezone.utc)
            else:
                entry = DealAICache(
                    deal_id=deal_id,
                    analysis_type=analysis_type,
                    scope_key=scope_key,
                    result=result,
                    result_text=result_text,
                    input_hash=input_hash,
                    analysis_version=version,
                    model_used=model_used,
                    generation_ms=generation_ms,
                )
                session.add(entry)

            await session.commit()
            logger.info("ai_cache SAVED: deal=%s type=%s v=%s ms=%s", deal_id, analysis_type, version, generation_ms)

    except Exception as e:
        logger.warning("ai_cache DB save failed deal=%s type=%s: %s", deal_id, analysis_type, e)


# ══════════════════════════════════════════════════════════════
# INTERNAL: Redis burst protection (60s TTL)
# ══════════════════════════════════════════════════════════════

async def _redis_burst_check(cache_key: str) -> Optional[dict]:
    try:
        from services.cache import cache_get
        return await cache_get(cache_key)
    except Exception:
        return None


async def _redis_burst_set(cache_key: str, result: dict) -> None:
    try:
        from services.cache import cache_set
        await cache_set(cache_key, result, ttl=60)
    except Exception:
        pass
