"""
CRM adapter abstraction layer.

Defines the unified interface (CRMAdapter) and canonical data model (CRMDeal)
that all CRM implementations must satisfy.  Concrete implementations live in
zoho_adapter.py, demo_adapter.py, etc.
"""

from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel


class CRMDeal(BaseModel):
    """Unified deal representation across any CRM."""

    crm_id: str
    name: str
    company: Optional[str] = None
    stage: Optional[str] = None
    amount: Optional[float] = None
    owner_email: Optional[str] = None   # best available owner identifier
    close_date: Optional[str] = None
    contacts: list = []
    activities: list = []
    notes: list = []
    raw_data: dict = {}                 # original CRM payload — nothing is lost


class CRMAdapter(ABC):
    """
    Abstract CRM adapter.

    Every method accepts a `token` string whose meaning is implementation-
    specific (OAuth access token for Zoho, ignored for demo, API key for
    HubSpot, etc.).  Implementations raise CRMError subclasses on failure
    so callers never need to import CRM-specific exception types.
    """

    @abstractmethod
    async def get_deals(self, token: str) -> list[CRMDeal]:
        """Return all active deals visible to this token."""
        ...

    @abstractmethod
    async def get_deal(self, token: str, deal_id: str) -> Optional[CRMDeal]:
        """
        Return a single deal by its CRM record ID.
        Returns None if the deal does not exist.
        """
        ...

    @abstractmethod
    async def get_deal_contacts(self, token: str, deal_id: str) -> list[dict]:
        """
        Return contacts associated with the deal.
        Each dict contains at minimum: name, email, role.
        """
        ...

    @abstractmethod
    async def get_deal_activities(self, token: str, deal_id: str) -> list[dict]:
        """
        Return activities (calls, tasks, meetings) for the deal.
        Each dict contains at minimum: type, subject, date.
        """
        ...

    @abstractmethod
    async def get_deal_notes(self, token: str, deal_id: str) -> list[dict]:
        """Return notes attached to the deal."""
        ...
