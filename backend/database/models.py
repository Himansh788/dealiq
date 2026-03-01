import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# deals
# ---------------------------------------------------------------------------

class Deal(Base):
    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    zoho_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255))
    stage: Mapped[str | None] = mapped_column(String(100))
    amount: Mapped[float | None] = mapped_column(Numeric(15, 2))
    owner_email: Mapped[str | None] = mapped_column(String(255))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    total_score: Mapped[int] = mapped_column(Integer, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    health_label: Mapped[str] = mapped_column(String(20), nullable=False)  # healthy/at_risk/critical/zombie
    recommendation: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal: Mapped["Deal"] = relationship(back_populates="health_scores")

    __table_args__ = (
        # Fast trend queries: latest score for a deal first
        Index("ix_health_scores_deal_scored_at", "deal_id", scored_at.desc()),
    )


# ---------------------------------------------------------------------------
# decisions
# ---------------------------------------------------------------------------

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    deal: Mapped["Deal | None"] = relationship(back_populates="emails")
    analyses: Mapped[list["EmailAnalysis"]] = relationship(back_populates="email", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# email_analyses
# ---------------------------------------------------------------------------

class EmailAnalysis(Base):
    __tablename__ = "email_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("emails.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # mismatch/discount/sentiment/next_step
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    health_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    analysed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    email: Mapped["Email"] = relationship(back_populates="analyses")


# ---------------------------------------------------------------------------
# transcripts
# ---------------------------------------------------------------------------

class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    transcript_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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
# audit_log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_email: Mapped[str] = mapped_column(String(255), nullable=False)
    deal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
