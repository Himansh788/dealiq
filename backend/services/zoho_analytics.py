"""
Zoho Analytics API client for Regional Target gauge components.

Dashboard: "Sales Q1 2026 Goals" (id: 202252000056117001)
Each gauge component maps to a region and exposes:
  - achieved: component_chunks[0].data_map.T.aggregates[0].value
  - target:   component_chunks[0].component_markers[0].y.target.value

Usage:
    results = await fetch_all_regional_targets(access_token)
    # returns list of {"region", "achieved", "target", "component_id"}
"""
import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Dashboard config ──────────────────────────────────────────────────────────

DASHBOARD_ID = "202252000056117001"

# component_id → region label. TBD entries need to be discovered via /component-ids.
REGIONAL_COMPONENTS: dict[str, str] = {
    "202252000056117004": "SEA/Oceania",   # confirmed
    "TBD_AMERICAS":       "Americas",
    "TBD_MENA":           "MENA",
    "TBD_EU":             "EU",
    "TBD_ASIA":           "ASIA",
}

ZOHO_BASE = "https://www.zohoapis.in/crm/v2.2"
ANALYTICS_ENDPOINT = (
    "{base}/Analytics/{dashboard_id}/Components/{component_id}/actions/run"
    "?apply_filter_set_criteria=true"
)

# 5-minute in-process cache: { "all_targets": (timestamp, data) }
_CACHE: dict[str, tuple[float, list]] = {}
TTL = 300  # 5 minutes


# ── Core fetcher ──────────────────────────────────────────────────────────────

async def fetch_analytics_component(
    client: httpx.AsyncClient,
    access_token: str,
    component_id: str,
    region_label: str,
) -> Optional[dict]:
    """
    Fetch a single gauge component and extract achieved/target values.
    Returns None on any error (skipped gracefully).
    """
    if component_id.startswith("TBD"):
        logger.debug("Skipping TBD component for region=%s", region_label)
        return None

    url = ANALYTICS_ENDPOINT.format(
        base=ZOHO_BASE,
        dashboard_id=DASHBOARD_ID,
        component_id=component_id,
    )
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json",
    }

    try:
        resp = await client.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        body = resp.json()
    except Exception as e:
        logger.warning("fetch_analytics_component failed region=%s error=%s", region_label, e)
        return None

    try:
        chunks = body.get("component_chunks") or []
        if not chunks:
            logger.warning("No component_chunks for region=%s body_keys=%s", region_label, list(body.keys()))
            return None

        chunk = chunks[0]
        data_map = chunk.get("data_map", {})
        t_data = data_map.get("T", {})
        aggregates = t_data.get("aggregates", [])
        achieved = float(aggregates[0]["value"]) if aggregates else 0.0

        markers = chunk.get("component_markers", [])
        target = 0.0
        if markers:
            y_block = markers[0].get("y", {})
            target_block = y_block.get("target", {})
            target = float(target_block.get("value", 0))

        return {
            "region": region_label,
            "component_id": component_id,
            "achieved": achieved,
            "target": target,
        }
    except Exception as e:
        logger.warning("parse error region=%s error=%s body=%s", region_label, e, str(body)[:400])
        return None


# ── Parallel fetch for all components ─────────────────────────────────────────

async def fetch_all_regional_targets(access_token: str) -> list[dict]:
    """
    Fetch all configured gauge components in parallel.
    Results are cached for TTL seconds.
    Returns list of {region, component_id, achieved, target}.
    """
    cached = _CACHE.get("all_targets")
    if cached:
        ts, data = cached
        if time.monotonic() - ts < TTL:
            logger.debug("zoho_analytics: cache hit (entries=%d)", len(data))
            return data
        else:
            logger.debug("zoho_analytics: cache expired, re-fetching")

    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_analytics_component(client, access_token, cid, region)
            for cid, region in REGIONAL_COMPONENTS.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out = []
    for r in results:
        if isinstance(r, dict):
            out.append(r)
        elif isinstance(r, Exception):
            logger.warning("gather exception: %s", r)

    logger.info("zoho_analytics: fetched %d region(s) from Zoho Analytics", len(out))
    # Only cache successful (non-empty) results — don't poison cache on auth failure
    if out:
        _CACHE["all_targets"] = (time.monotonic(), out)
    return out


# ── Dashboard component discovery ─────────────────────────────────────────────

async def fetch_dashboard_components(access_token: str) -> list[dict]:
    """
    GET /crm/v2.2/Analytics/{dashboard_id}/Components
    Returns list of {component_id, name, type} for the dashboard.
    Used by /analytics/component-ids discovery endpoint.
    """
    url = f"{ZOHO_BASE}/Analytics/{DASHBOARD_ID}/Components"
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            body = resp.json()
        components = body.get("components") or body.get("data") or []
        return [
            {
                "component_id": str(c.get("id") or c.get("component_id", "")),
                "name": c.get("name") or c.get("title", ""),
                "type": c.get("type", ""),
            }
            for c in components
        ]
    except Exception as e:
        logger.warning("fetch_dashboard_components failed: %s", e)
        return []
