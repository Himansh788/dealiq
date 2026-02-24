from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    zoho_user_id: str
    display_name: str
    email: str


class ZohoUser(BaseModel):
    id: str
    display_name: str
    email: str
    access_token: str
    refresh_token: str


# ── Deals ─────────────────────────────────────────────────────────────────────

class Deal(BaseModel):
    id: str
    name: str
    stage: str
    amount: Optional[float] = None
    closing_date: Optional[str] = None
    account_name: Optional[str] = None
    owner: Optional[str] = None
    last_activity_time: Optional[str] = None
    created_time: Optional[str] = None
    probability: Optional[float] = None
    # Computed by DealIQ
    health_score: Optional[int] = None
    health_label: Optional[str] = None  # "healthy" | "at_risk" | "critical" | "zombie"
    days_in_stage: Optional[int] = None
    next_step: Optional[str] = None


class DealList(BaseModel):
    deals: List[Deal]
    total: int
    simulated: bool = False  # True if using demo data


# ── Health Score ──────────────────────────────────────────────────────────────

class HealthSignal(BaseModel):
    name: str
    score: int          # 0-20 per signal
    max_score: int
    label: str
    detail: str


class DealHealthResult(BaseModel):
    deal_id: str
    deal_name: str
    total_score: int    # 0-100
    health_label: str   # healthy / at_risk / critical / zombie
    signals: List[HealthSignal]
    recommendation: str
    action_required: bool


# ── Narrative Mismatch ────────────────────────────────────────────────────────

class MismatchRequest(BaseModel):
    deal_id: Optional[str] = None
    transcript: str
    email_draft: str


class MismatchFlag(BaseModel):
    category: str       # pricing | timeline | next_step | feature_promise | commitment
    description: str    # plain-language, <30 words, directed at rep
    severity: str       # high | medium | low
    suggested_fix: str


class MismatchResult(BaseModel):
    mismatches: List[MismatchFlag]
    deal_health_impact: int   # negative number, e.g. -15
    clean: bool               # True if no mismatches found
    summary: str


# ── Discount Heat Map ─────────────────────────────────────────────────────────

class DiscountMention(BaseModel):
    mention_index: int
    context: str        # brief excerpt
    raised_by: str      # rep | buyer | unknown
    discount_value: Optional[str] = None


class DiscountAnalysis(BaseModel):
    deal_id: str
    total_mentions: int
    mentions: List[DiscountMention]
    pressure_level: str   # normal | elevated | critical
    benchmark_comparison: str
    recommendation: str


# ── Advance / Close / Kill ────────────────────────────────────────────────────

class ACKResult(BaseModel):
    deal_id: str
    deal_name: str
    days_stalled: int
    recommendation: str   # advance | close | kill | escalate
    reasoning: str
    supporting_signals: List[str]


class ACKDecision(BaseModel):
    deal_id: str
    decision: str         # advance | close | kill | escalate
    next_step: Optional[str] = None
    notes: Optional[str] = None


# ── Dashboard Summary ─────────────────────────────────────────────────────────

class PipelineMetrics(BaseModel):
    total_deals: int
    total_value: float
    average_health_score: float
    healthy_count: int
    at_risk_count: int
    critical_count: int
    zombie_count: int
    deals_needing_action: int
