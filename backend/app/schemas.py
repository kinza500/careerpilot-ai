"""API schemas (Pydantic v2)."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


# --- Auth ---
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str | None = None


class GoogleStatusOut(BaseModel):
    connected: bool
    email: str | None = None
    # False means the connected account's token predates (or never granted)
    # gmail.readonly — reply-detection and sent-detection will silently never
    # work until the user reconnects. True/None (unknown) otherwise.
    has_readonly_scope: bool | None = None
    # Same idea for calendar.events — needed to confirm a suggested interview
    # slot onto the user's calendar.
    has_calendar_scope: bool | None = None


# --- Resume / profile ---
class ProfileOut(BaseModel):
    id: UUID
    resume_id: UUID | None
    profile: dict
    created_at: datetime


# --- Jobs ---
# Curated relocation destinations: strong/stable economies that commonly draw
# skilled-worker relocation, matched 1:1 against app.agents.discovery_agent's
# per-country job-board coverage.
DestinationCountry = Literal[
    "Pakistan", "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait",
    "USA", "Canada", "UK", "Germany", "Australia", "Singapore", "Ireland",
    "Netherlands", "New Zealand",
]


class DiscoverIn(BaseModel):
    query: str = Field(examples=["backend engineer"])
    location: DestinationCountry = "Pakistan"
    work_type: Literal["remote", "onsite", "hybrid"] = "remote"
    limit: int = Field(default=20, ge=1, le=100)


class JobOut(BaseModel):
    id: UUID
    title: str
    company: str | None = None
    location: str | None = None
    remote: bool | None = None
    salary: str | None = None
    url: str | None = None
    source: str | None = None
    company_url: str | None = None
    # Only ever a real address found written in the posting itself — never
    # invented. Most listings won't have one since job boards route
    # applications through their own portals, not email.
    contact_email: str | None = None


# --- Matches ---
class MatchOut(BaseModel):
    id: UUID
    job: JobOut
    score: float
    reasoning: str | None = None
    factors: dict | None = None


# --- Applications ---
class PrepIn(BaseModel):
    job_id: UUID


class ApplicationOut(BaseModel):
    id: UUID
    job_id: UUID
    job: JobOut
    status: str
    # Which resume this application was prepared from — lets a user who has
    # uploaded multiple CVs over time see which one produced each application.
    resume_filename: str | None = None
    resume_uploaded_at: datetime | None = None
    tailored_resume: str | None = None
    cover_letter: str | None = None
    outreach_email: str | None = None
    critic_notes: dict | None = None
    company_research: str | None = None
    # Whether company_research came from an actual live web search (Tavily)
    # vs. an ungrounded LLM guess — shown to the user so the effort is honest.
    company_research_grounded: bool = False
    # Real source links the research was drawn from — straight from Tavily's
    # own results, never LLM-generated, so nothing here can be a hallucinated URL.
    company_research_sources: list[dict] = Field(default_factory=list)
    followup_status: str | None = None
    # Whether this application was ever drafted into Gmail (has a thread to
    # check for replies / thread a follow-up into).
    has_gmail_draft: bool = False
    # Detected via a live gmail.readonly check (never assumed) — true once a
    # SENT message actually shows up in that Gmail thread.
    email_sent: bool = False
    # A reply landed on the application's own Gmail thread — checked
    # opportunistically, not gated behind the 14-day follow-up wait.
    reply_received: bool = False
    # Suggested interview slot extracted from the reply text (date/time/
    # timezone/duration_minutes/location_or_method/summary) — only ever a
    # suggestion for the user to confirm; null once dismissed or confirmed.
    interview_schedule: dict | None = None
    # Set once the user confirms and a real calendar event is created.
    calendar_event_id: str | None = None


class ApplicationEventOut(BaseModel):
    kind: str
    created_at: datetime


class ApproveIn(BaseModel):
    application_id: UUID
    confirm: bool = True


class GmailDraftOut(BaseModel):
    draft_id: str
    url: str | None = None


# --- Follow-ups ---
class FollowupOut(BaseModel):
    application_id: UUID
    job: JobOut
    days_since_applied: int
    followup_email: str
    # Whether the original application email was drafted via Gmail — only
    # then can a follow-up be threaded into the same conversation.
    can_thread: bool
    # Whether CareerPilot could actually check the Gmail thread for a reply
    # (requires gmail.readonly + a real thread). False means this is purely
    # the 14-day time-based nudge, with no reply verification behind it.
    reply_checked: bool


class FollowupDraftOut(BaseModel):
    application_id: UUID
    followup_status: str
    draft_id: str | None = None
    url: str | None = None
    threaded: bool = False


# --- Interview Prep ---
class InterviewTurnOut(BaseModel):
    role: str  # "interviewer" | "candidate"
    content: str


class InterviewSessionOut(BaseModel):
    id: UUID
    application_id: UUID
    status: str
    transcript: list[InterviewTurnOut]
    feedback: dict | None = None
    created_at: datetime


class InterviewStartIn(BaseModel):
    application_id: UUID


class InterviewRespondIn(BaseModel):
    answer: str
