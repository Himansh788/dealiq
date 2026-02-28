"""
Demo CRM adapter — serves the existing SIMULATED_DEALS / SIMULATED_ACTIVITIES
data through the CRMAdapter interface.

The `token` argument is accepted but ignored — demo mode needs no auth.
"""

from typing import Optional

from services.crm_adapter import CRMAdapter, CRMDeal
from services.crm_errors import CRMNotFoundError
from services.demo_data import SIMULATED_ACTIVITIES, SIMULATED_DEALS


_CRM_NAME = "demo"


def _sim_deal_to_crm_deal(d: dict) -> CRMDeal:
    """Map a SIMULATED_DEALS entry to CRMDeal."""
    entry = SIMULATED_ACTIVITIES.get(d["id"], {})
    contacts = entry.get("contacts", [])
    activities = [a for a in entry.get("activities", []) if a.get("type") != "email"]

    return CRMDeal(
        crm_id=d["id"],
        name=d.get("name", "Unnamed Deal"),
        company=d.get("account_name"),
        stage=d.get("stage"),
        amount=float(d["amount"]) if d.get("amount") is not None else None,
        owner_email=d.get("owner"),
        close_date=d.get("closing_date"),
        contacts=contacts,
        activities=activities,
        notes=[],
        raw_data=d,
    )


class DemoCRMAdapter(CRMAdapter):
    """Returns fixed simulated data — no network calls, no auth required."""

    async def get_deals(self, token: str) -> list[CRMDeal]:
        return [_sim_deal_to_crm_deal(d) for d in SIMULATED_DEALS]

    async def get_deal(self, token: str, deal_id: str) -> Optional[CRMDeal]:
        match = next((d for d in SIMULATED_DEALS if d["id"] == deal_id), None)
        if match is None:
            return None
        return _sim_deal_to_crm_deal(match)

    async def get_deal_contacts(self, token: str, deal_id: str) -> list[dict]:
        entry = SIMULATED_ACTIVITIES.get(deal_id, {})
        return entry.get("contacts", [])

    async def get_deal_activities(self, token: str, deal_id: str) -> list[dict]:
        entry = SIMULATED_ACTIVITIES.get(deal_id, {})
        # Return non-email activities (calls, meetings, tasks)
        return [a for a in entry.get("activities", []) if a.get("type") != "email"]

    async def get_deal_notes(self, token: str, deal_id: str) -> list[dict]:
        # Demo data has no separate notes — return empty list
        return []
