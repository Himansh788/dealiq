from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CRMDeal:
    id: str
    name: str
    company: str
    stage: str
    amount: float
    currency: str
    close_date: Optional[datetime]
    created_at: Optional[datetime]
    owner_id: str
    owner_name: str
    probability: Optional[float]
    pipeline: Optional[str]
    description: Optional[str]
    next_step: Optional[str]
    contacts: List[Dict[str, Any]]
    custom_fields: Dict[str, Any]
    raw: Dict[str, Any]


@dataclass
class CRMActivity:
    id: str
    deal_id: str
    type: str
    subject: str
    description: Optional[str]
    date: datetime
    owner_id: str
    owner_name: str
    direction: Optional[str]
    contacts: List[str]
    raw: Dict[str, Any]


@dataclass
class CRMEmail:
    id: str
    deal_id: Optional[str]
    thread_id: Optional[str]
    subject: str
    body: str
    from_email: str
    from_name: str
    to_emails: List[str]
    cc_emails: List[str]
    date: datetime
    direction: str
    has_attachments: bool
    raw: Dict[str, Any]


@dataclass
class CRMContact:
    id: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    role: Optional[str]
    company: Optional[str]
    raw: Dict[str, Any]


@dataclass
class CRMUser:
    id: str
    name: str
    email: str
    role: Optional[str]
    avatar_url: Optional[str]


@dataclass
class CRMAuthTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime
    provider: str
    extra: Dict[str, Any] = field(default_factory=dict)


class CRMAdapter(ABC):
    provider_name: str

    @abstractmethod
    async def authenticate(self, auth_code: str, redirect_uri: str) -> CRMAuthTokens:
        ...

    @abstractmethod
    async def refresh_token(self, tokens: CRMAuthTokens) -> CRMAuthTokens:
        ...

    @abstractmethod
    async def get_current_user(self, tokens: CRMAuthTokens) -> CRMUser:
        ...

    @abstractmethod
    async def get_deals(self, tokens: CRMAuthTokens, modified_since: Optional[datetime] = None) -> List[CRMDeal]:
        ...

    @abstractmethod
    async def get_deal(self, tokens: CRMAuthTokens, deal_id: str) -> CRMDeal:
        ...

    @abstractmethod
    async def get_activities(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMActivity]:
        ...

    @abstractmethod
    async def get_emails(self, tokens: CRMAuthTokens, deal_id: Optional[str] = None, entity_id: Optional[str] = None) -> List[CRMEmail]:
        ...

    @abstractmethod
    async def get_contacts(self, tokens: CRMAuthTokens, deal_id: str) -> List[CRMContact]:
        ...

    @abstractmethod
    async def update_deal(self, tokens: CRMAuthTokens, deal_id: str, updates: Dict[str, Any]) -> bool:
        ...

    @abstractmethod
    async def get_stages(self, tokens: CRMAuthTokens) -> List[Dict[str, Any]]:
        ...

    def get_auth_url(self, redirect_uri: str, state: str) -> str:
        raise NotImplementedError
