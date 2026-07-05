"""ORM models. These mirror sql/001_init.sql. RLS lives in the DB, not here —
these models never bypass it because every query runs inside a tenant_session.
"""
from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    google_refresh_token_enc: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    google_email: Mapped[str | None] = mapped_column(Text, nullable=True)


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)   # encrypted at rest
    sha256: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillProfile(Base):
    __tablename__ = "skill_profiles"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    resume_id: Mapped[UUID | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    profile: Mapped[dict] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "source", "external_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user_id", "job_id", "profile_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("skill_profiles.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        CheckConstraint("status IN ('draft','review','approved','submitted','rejected')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    profile_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("skill_profiles.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, default="draft")
    tailored_resume: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)
    outreach_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    critic_notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    company_research: Mapped[str | None] = mapped_column(Text, nullable=True)
    company_research_grounded: Mapped[bool] = mapped_column(default=False)
    # [{"title": str, "url": str}, ...] — real URLs straight from Tavily's own
    # results, never LLM-generated, so there's no risk of a hallucinated link.
    company_research_sources: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    gmail_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Detected via gmail.readonly (never assumed) — true once a SENT-labelled
    # message shows up in gmail_thread_id, i.e. the user actually sent the
    # draft themselves from Gmail. CareerPilot still never sends anything.
    email_sent: Mapped[bool] = mapped_column(default=False)
    # A reply landed on gmail_thread_id (INBOX label) — checked opportunistically
    # for ANY application with a thread, not gated behind the 14-day follow-up
    # wait like followup_status='responded' is, so the Applications list can
    # reflect a reply the moment it actually arrives.
    reply_received: Mapped[bool] = mapped_column(default=False)
    # Suggested interview slot extracted from the reply's own text — only a
    # suggestion; never written to the calendar until the user confirms it
    # (see calendar_event_id). _checked prevents re-running the LLM
    # extraction on every load once a reply has already been evaluated once.
    interview_schedule: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interview_schedule_checked: Mapped[bool] = mapped_column(default=False)
    calendar_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The follow-up's own thread (equals gmail_thread_id when threaded into
    # the original conversation, or a fresh thread when it wasn't). Needed to
    # detect "was the follow-up itself sent" independent of the original.
    followup_gmail_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How many SENT messages already existed in that thread when the
    # follow-up was drafted — sent-detection looks for the count to grow
    # past this, not just ">0", since the original may already be sent.
    followup_sent_baseline: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class MemoryEvent(Base):
    __tablename__ = "memory_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InterviewSession(Base):
    """A mock-interview run for one application — scoped to applications the
    user has actually prepared, so it can be grounded in the job description,
    tailored resume, and company research already gathered for that one."""
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('in_progress','completed')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, default="in_progress")
    # [{"role": "interviewer" | "candidate", "content": str}, ...] in order.
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
