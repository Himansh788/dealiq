import os
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,          # works with MySQL 5.7+ natively; falls back for PostgreSQL
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Use PostgreSQL JSONB (binary, indexable) when available; fall back to JSON for MySQL.
_DB_URL = os.getenv("DATABASE_URL", "")
if "postgresql" in _DB_URL or "asyncpg" in _DB_URL:
    from sqlalchemy.dialects.postgresql import JSONB as _FlexJSON  # type: ignore[assignment]
else:
    _FlexJSON = JSON  # type: ignore[misc,assignment]


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# deals
# ---------------------------------------------------------------------------

class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    zoho_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[float | None] = mapped_column(Numeric(15, 2))
    owner_email: Mapped[str | None] = mapped_column(String(255))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cache fields — populated when deal is synced from Zoho
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    closing_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_activity_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sync_source: Mapped[str | None] = mapped_column(String(50), nullable=True, default="zoho")  # zoho | manual | demo
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    # JSONB columns for flexible metadata & cached AI results (PostgreSQL: JSONB with GIN index; MySQL: JSON)
    health_signals: Mapped[dict | None] = mapped_column(_FlexJSON, nullable=True, default=dict)
    ai_analysis: Mapped[dict | None] = mapped_column(_FlexJSON, nullable=True, default=dict)
    deal_metadata: Mapped[dict | None] = mapped_column(_FlexJSON, nullable=True, default=dict)
    activity_summary: Mapped[dict | None] = mapped_column(_FlexJSON, nullable=True, default=dict)

    __table_args__ = (
        # GIN index on health_signals for fast JSONB queries (PostgreSQL only; ignored on MySQL)
        Index("ix_deals_health_signals", "health_signals", postgresql_using="gin"),
    )

    # relationships
    health_scores: Mapped[list["HealthScore"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    decisions: Mapped[list["Decision"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    emails: Mapped[list["Email"]] = relationship(back_populates="deal", cascade="all, delete-orphan")
    transcripts: Mapped[list["Transcript"]] = relationship(back_populates="deal", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# health_scores
# ---------------------------------------------------------------------------

class HealthScore(Base):
    __tablename__ = "health_scores"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    deal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    health_label: Mapped[str] = mapped_column(String(20), nullable=False)  # healthy/at_risk/critical/zombie
    recommendation: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    score_version: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)  # bump when algorithm changes

    deal: Mapped["Deal"] = relationship(back_populates="health_scores")

    __table_args__ = (
        # Fast trend queries: latest score per deal
        Index("ix_health_scores_deal_scored_at", "deal_id", "scored_at"),
    )


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    deal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # advance/escalate/kill
    reasoning: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal: Mapped["Deal"] = relationship(back_populates="decisions")


# ---------------------------------------------------------------------------
# emails
# ---------------------------------------------------------------------------

class Email(Base):
    __tablename__ = "emails"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    deal_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("deals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)  # Gmail message ID
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    to_addresses: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # inbound/outbound
    classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_analysed: Mapped[bool] = mapped_column(Boolean, default=False)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    zoho_email_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal: Mapped["Deal | None"] = relationship(back_populates="emails")
    analyses: Mapped[list["EmailAnalysis"]] = relationship(back_populates="email", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# email_analyses
# ---------------------------------------------------------------------------

class EmailAnalysis(Base):
    __tablename__ = "email_analyses"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    email_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mismatch/discount/sentiment/next_step
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    health_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True, default="claude-haiku")  # stale if model upgraded

    email: Mapped["Email"] = relationship(back_populates="analyses")


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------

class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    deal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # gong/fireflies/manual/zoom
    transcript_text: Mapped[str] = mapped_column(Text, nullable=False)
    call_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    participants: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_analysed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal: Mapped["Deal"] = relationship(back_populates="transcripts")


# ---------------------------------------------------------------------------
# transcript_summaries  (pre-processed call intelligence — reused across AI calls)
# ---------------------------------------------------------------------------

class TranscriptSummary(Base):
    __tablename__ = "transcript_summaries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    transcript_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    deal_zoho_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    rep_commitments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    buyer_commitments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    next_steps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    objections_raised: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    budget_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    competition_mentioned: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    key_stakeholders: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # positive/negative/neutral/mixed
    call_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# email_extractions  (extracted next-step / commitments per email)
# ---------------------------------------------------------------------------

class EmailExtraction(Base):
    __tablename__ = "email_extractions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    email_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    deal_zoho_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    commitments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    open_questions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# meeting_log
# ---------------------------------------------------------------------------

class MeetingLog(Base):
    __tablename__ = "meeting_log"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    calendar_event_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    deal_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    attendees: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quick_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # great/ok/concern
    topics_confirmed: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_items: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    crm_updates_applied: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    follow_up_email_draft: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# pending_crm_update
# ---------------------------------------------------------------------------

class PendingCrmUpdate(Base):
    __tablename__ = "pending_crm_update"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    deal_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)  # high/medium/low
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # meeting/email/daily_scan
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending/approved/rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# api_cache  (generic external-API response cache — prevents Zoho 429 floods)
# ---------------------------------------------------------------------------

class ApiCache(Base):
    __tablename__ = "api_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    response_data: Mapped[str] = mapped_column(Text, nullable=False)   # JSON string
    source: Mapped[str] = mapped_column(String(64), nullable=False)    # "zoho"
    endpoint: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("ix_api_cache_source_key", "source", "cache_key"),
        Index("ix_api_cache_expires", "expires_at"),
    )


# ---------------------------------------------------------------------------
# audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    deal_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# crm_connections  (multi-CRM adapter — stores OAuth tokens per user/org/provider)
# ---------------------------------------------------------------------------

class CRMConnection(Base):
    __tablename__ = "crm_connections"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )
    org_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)  # zoho | salesforce | hubspot
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    instance_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Salesforce instance URL / extra JSON
    crm_org_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="idle")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# microsoft_tokens  (persisted MS OAuth tokens — survives server restarts)
# ---------------------------------------------------------------------------

class MicrosoftToken(Base):
    __tablename__ = "microsoft_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    # Keyed by Zoho user email or user_id from the session
    user_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    ms_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # UTC datetime when access_token expires
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


# ---------------------------------------------------------------------------
# deal_personas  (contact intelligence — Zoho contacts + Outlook-discovered)
# ---------------------------------------------------------------------------

class DealPersona(Base):
    __tablename__ = "deal_personas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    deal_zoho_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # Identity
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Source
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # zoho | outlook_discovered
    # Rep decision
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # confirmed | pending | rejected
    confirmed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Extra metadata from email (display name from email headers)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_seen_at: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ISO date of last email
    email_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        # One record per (deal, email) — upsert on conflict
        Index("uq_deal_personas_deal_email", "deal_zoho_id", "email", unique=True),
    )


# ---------------------------------------------------------------------------
# regional_targets
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# user_preferences  (per-user settings — digest, notifications, etc.)
# ---------------------------------------------------------------------------

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    # Same pattern as MicrosoftToken — keyed by decoded session user_id / email
    user_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    digest_time: Mapped[str] = mapped_column(String(5), nullable=False, default="09:00")  # HH:MM
    digest_email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    digest_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    email_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())


# ---------------------------------------------------------------------------
# digest_tasks  (generated tasks per user per day + completion state)
# ---------------------------------------------------------------------------

class DigestTask(Base):
    __tablename__ = "digest_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    deal_id: Mapped[str] = mapped_column(String(50), nullable=False)
    deal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)  # email/call/whatsapp/case_study/meeting/contract
    task_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_digest_tasks_user_date", "user_key", "date"),
    )


class RegionalTarget(Base):
    __tablename__ = "regional_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    quarter: Mapped[str] = mapped_column(String(10), nullable=False)   # "Q1"/"Q2"/"Q3"/"Q4"
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    target_amount: Mapped[float] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    __table_args__ = (
        Index("uq_regional_targets_region_quarter_fy", "region", "quarter", "fiscal_year", unique=True),
    )


# ---------------------------------------------------------------------------
# contract_intelligence
# ---------------------------------------------------------------------------

class StandardContract(Base):
    __tablename__ = "standard_contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    clauses_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProspectContract(Base):
    __tablename__ = "prospect_contracts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    deal_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    deal_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prospect_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    region: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    clauses_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard_contract_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("standard_contracts.id"), nullable=True)


class ContractDeviation(Base):
    __tablename__ = "contract_deviations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    prospect_contract_id: Mapped[str] = mapped_column(String(36), ForeignKey("prospect_contracts.id"), nullable=False, index=True)
    clause_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    clause_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    standard_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    prospect_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    deviation_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_counter_suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_discount_related: Mapped[bool] = mapped_column(Boolean, default=False)
    discount_standard_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    discount_prospect_pct: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# vervotech_content  (scraped marketing content for case study recommendations)
# ---------------------------------------------------------------------------

class DealAICache(Base):
    """
    Persistent AI analysis cache — PostgreSQL-first, survives restarts.
    One active entry per (deal_id, analysis_type, scope_key).
    """
    __tablename__ = "deal_ai_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False, default="__global__")

    # Cached AI output
    result: Mapped[dict] = mapped_column(_FlexJSON, nullable=False)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Change detection
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Versioning (bump when prompt/schema changes)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Metadata
    model_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tokens_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generation_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("uq_deal_analysis", "deal_id", "analysis_type", "scope_key", unique=True),
        Index("idx_dac_lookup", "deal_id", "analysis_type", "scope_key"),
        Index("idx_dac_stale", "updated_at"),
    )


class VervotechContent(Base):
    __tablename__ = "vervotech_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)  # case_study | blog | ebook | documentation | infographic | video | impact_story
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # AI-tagged arrays — stored as JSON strings on MySQL, JSONB on PG
    client_types: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")  # JSON array e.g. ["TMC","OTA"]
    products: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")      # JSON array
    topics: Mapped[str | None] = mapped_column(Text, nullable=True, default="[]")        # JSON array

    has_specific_numbers: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    scraped_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, onupdate=func.now())

    __table_args__ = (
        Index("ix_vervotech_content_type", "content_type"),
    )
