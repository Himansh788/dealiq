"""
Deal Context Builder
====================
Fetches and caches the deal metadata needed by the email attribution engine.

Provides: deal_id, deal_name, account_name, stage, created_time,
          closing_date, modified_time, contacts (from Zoho Contact_Roles)

Cache strategy
--------------
  L1: Redis  (TTL 5 min)  — avoids repeated Zoho calls within a request burst
  L2: Zoho API            — single GET /Deals/{id} + Contact_Roles

Usage
-----
    ctx = await build_deal_context(zoho_token, deal_id)
    # ctx is a dict or {} on failure — callers handle empty dict gracefully
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_FIELDS = "Deal_Name,Account_Name,Stage,Created_Time,Closing_Date,Modified_Time"
_CACHE_TTL = 300   # 5 minutes


async def build_deal_context(zoho_token: str, deal_id: str) -> dict:
    """
    Return deal context dict for email attribution.
    Returns {} if the deal cannot be fetched (callers must guard).
    """
    if not zoho_token or not deal_id:
        logger.warning("deal_context_builder [deal=%s]: missing zoho_token=%s or deal_id — returning {}", deal_id, bool(zoho_token))
        return {}

    cache_key = f"dealiq:deal_ctx:{deal_id}"

    # L1: Redis cache
    try:
        from services.cache import cache_get, cache_set
        cached = await cache_get(cache_key)
        if cached:
            parsed = json.loads(cached)
            logger.info("deal_context_builder [deal=%s]: cache hit contacts=%d", deal_id, len(parsed.get("contacts", [])))
            return parsed
    except Exception as e:
        logger.warning("deal_context_builder [deal=%s]: cache read error: %s", deal_id, e)

    logger.info("deal_context_builder [deal=%s]: cache miss — fetching from Zoho", deal_id)

    # L2: Zoho API
    ctx = await _fetch_from_zoho(zoho_token, deal_id)
    if not ctx:
        logger.warning("deal_context_builder [deal=%s]: Zoho fetch returned nothing — no deal context", deal_id)
        return {}

    # Write to cache
    try:
        from services.cache import cache_set
        await cache_set(cache_key, json.dumps(ctx), ttl=_CACHE_TTL)
    except Exception:
        pass

    return ctx


async def _fetch_from_zoho(zoho_token: str, deal_id: str) -> Optional[dict]:
    try:
        import httpx
        from services.zoho_client import ZOHO_API_BASE, get_contacts_for_deal

        headers = {"Authorization": f"Zoho-oauthtoken {zoho_token}"}

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{ZOHO_API_BASE}/Deals/{deal_id}",
                headers=headers,
                params={"fields": _FIELDS},
            )

        if resp.status_code != 200:
            logger.warning(
                "deal_context_builder: deal=%s Zoho returned %d", deal_id, resp.status_code
            )
            return None

        records = resp.json().get("data", [])
        if not records:
            return None
        data = records[0]

        # Fetch contacts in parallel via Contact_Roles (most reliable for email matching)
        contacts = await get_contacts_for_deal(zoho_token, deal_id)

        logger.info(
            "deal_context_builder [deal=%s]: fetched deal_name=%r account_name=%r contacts=%d contact_emails=%s",
            deal_id,
            data.get("Deal_Name"),
            data.get("Account_Name"),
            len(contacts),
            [c.get("email") for c in contacts],
        )

        return {
            "deal_id":       deal_id,
            "deal_name":     data.get("Deal_Name") or "",
            "account_name":  data.get("Account_Name") or "",
            "stage":         data.get("Stage") or "",
            "created_time":  data.get("Created_Time") or "",
            "closing_date":  data.get("Closing_Date") or "",
            "modified_time": data.get("Modified_Time") or "",
            "contacts":      contacts,   # [{id, email, name, role, title}]
        }

    except Exception as e:
        logger.warning("deal_context_builder [deal=%s]: EXCEPTION during Zoho fetch: %s", deal_id, e)
        return None
