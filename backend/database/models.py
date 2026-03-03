import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,          # works with MySQL 5.7+ natively
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
