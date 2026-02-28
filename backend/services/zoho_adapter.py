"""
Zoho CRM adapter — wraps the existing zoho_client.py without modifying it.

Translates Zoho-specific responses into the canonical CRMDeal / list[dict]
types defined in crm_adapter.py.  All Zoho exceptions are caught and
re-raised as CRMError subclasses so callers stay CRM-agnostic.
"""

from typing import Optional

import httpx

from services.crm_adapter import CRMAdapter, CRMDeal
from services.crm_errors import CRMAuthError, CRMError, CRMNotFoundError, CRMRateLimitError
import services.zoho_client as _zoho


_CRM_NAME = "zoho"


def _http_to_crm_error(exc: httpx.HTTPStatusError) -> CRMError:
    """Map httpx HTTP errors to the appropriate CRMError subclass."""
    code = exc.response.status_code
    if code in (401, 403):
        return CRMAuthError(
            f"Zoho auth failed ({code}). Token may be expired — re-authenticate.",
            crm=_CRM_NAME,
            status_code=code,
        )
    if code == 429:
        return CRMRateLimitError(
            "Zoho API rate limit reached. Back off and retry.",
            crm=_CRM_NAME,
            status_code=code,
        )
    return CRMError(
        f"Zoho API error {code}: {exc.response.text[:200]}",
        crm=_CRM_NAME,
        status_code=code,
    )


def _mapped_to_crm_deal(mapped: dict) -> CRMDeal:
    """
    Convert an already-mapped deal dict (output of zoho_client.map_zoho_deal)
    to a CRMDeal.  'owner' in the mapped dict is a display name, not an email;
    we surface it as owner_email as the best available identifier.
    """
    return CRMDeal(
        crm_id=mapped.get("id", ""),
        name=mapped.get("name", "Unnamed Deal"),
        company=mapped.get("account_name"),
        stage=mapped.get("stage"),
        amount=float(mapped["amount"]) if mapped.get("amount") is not None else None,
        owner_email=mapped.get("owner"),       # display name — email not returned by list API
        close_date=mapped.get("closing_date"),
        raw_data=mapped,
    )


class ZohoCRMAdapter(CRMAdapter):
    """
    Concrete adapter for Zoho CRM (India region, v2 API).
    All network calls delegate to the existing zoho_client functions.
    """

    async def get_deals(self, token: str) -> list[CRMDeal]:
        """Fetch all deals and map to CRMDeal.  Supports pagination via zoho_client defaults."""
        try:
            raw_deals = await _zoho.fetch_deals(token)
        except httpx.HTTPStatusError as exc:
            raise _http_to_crm_error(exc) from exc
        except Exception as exc:
            raise CRMError(f"Zoho get_deals failed: {exc}", crm=_CRM_NAME) from exc

        return [_mapped_to_crm_deal(_zoho.map_zoho_deal(raw)) for raw in raw_deals]

    async def get_deal(self, token: str, deal_id: str) -> Optional[CRMDeal]:
        """
        Fetch a single deal.  Returns None if Zoho returns no data for the ID.
        fetch_single_deal already calls map_zoho_deal internally.
        """
        try:
            mapped = await _zoho.fetch_single_deal(token, deal_id)
        except httpx.HTTPStatusError as exc:
            raise _http_to_crm_error(exc) from exc
        except Exception as exc:
            raise CRMError(f"Zoho get_deal failed: {exc}", crm=_CRM_NAME) from exc

        if mapped is None:
            return None
        return _mapped_to_crm_deal(mapped)

    async def get_deal_contacts(self, token: str, deal_id: str) -> list[dict]:
        """
        Returns contacts via Contact_Roles endpoint.
        Each dict: { id, name, email, role, title }
        """
        try:
            return await _zoho.get_contacts_for_deal(token, deal_id)
        except Exception as exc:
            raise CRMError(f"Zoho get_deal_contacts failed: {exc}", crm=_CRM_NAME) from exc

    async def get_deal_activities(self, token: str, deal_id: str) -> list[dict]:
        """
        Returns closed tasks and meetings, plus calls, as a flat list.
        Each dict has an injected '_type' key: 'task' | 'meeting' | 'call'.
        """
        try:
            acts = await _zoho.fetch_deal_activities_closed(token, deal_id)
            calls = await _zoho.fetch_deal_calls(token, deal_id)
        except Exception as exc:
            raise CRMError(f"Zoho get_deal_activities failed: {exc}", crm=_CRM_NAME) from exc

        tasks = [{**t, "_type": "task"} for t in acts.get("tasks", [])]
        meetings = [{**m, "_type": "meeting"} for m in acts.get("meetings", [])]
        call_items = [{**c, "_type": "call"} for c in calls]
        return tasks + meetings + call_items

    async def get_deal_notes(self, token: str, deal_id: str) -> list[dict]:
        """Returns notes attached to the deal."""
        try:
            return await _zoho.fetch_deal_notes(token, deal_id)
        except Exception as exc:
            raise CRMError(f"Zoho get_deal_notes failed: {exc}", crm=_CRM_NAME) from exc
