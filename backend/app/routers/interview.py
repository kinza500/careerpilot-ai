"""Interview Prep endpoints — a live, adaptive mock interview tied to one
already-prepared application (never a bare job), so it's grounded in the real
job description, tailored resume, and company research gathered for it."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents import interview_agent
from app.core.security import current_user
from app.db import tenant_session
from app.models import Application, InterviewSession, Job, SkillProfile
from app.schemas import (
    InterviewRespondIn,
    InterviewSessionOut,
    InterviewStartIn,
)

router = APIRouter(prefix="/interview", tags=["interview"])


async def _application_context(s, uid: UUID, application_id: UUID) -> tuple[dict, dict, str]:
    """Returns (profile_dict, job_dict, company_research) for a prepared
    application belonging to this user — the same grounding data already
    shown in that application's review drawer."""
    row = (await s.execute(
        select(Application, Job).join(Job, Job.id == Application.job_id)
        .where(Application.id == application_id, Application.user_id == uid)
    )).first()
    if not row:
        raise HTTPException(404, "Application not found")
    app_row, job = row
    profile = None
    if app_row.profile_id:
        profile = (await s.execute(
            select(SkillProfile).where(SkillProfile.id == app_row.profile_id)
        )).scalar_one_or_none()
    job_dict = {"title": job.title, "company": job.company, "location": job.location,
                "description": job.description}
    return (profile.profile if profile else {}), job_dict, (app_row.company_research or "")


@router.post("/start", response_model=InterviewSessionOut)
async def start(body: InterviewStartIn, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        profile, job_dict, company_research = await _application_context(s, uid, body.application_id)
        opening = interview_agent.start_interview(profile, job_dict, company_research)

        session_id = uuid4()
        stmt = pg_insert(InterviewSession).values(
            id=session_id, user_id=uid, application_id=body.application_id,
            status="in_progress",
            transcript=[{"role": "interviewer", "content": opening}],
        ).returning(InterviewSession)
        row = (await s.execute(stmt)).scalar_one()
        return row


@router.post("/{session_id}/respond", response_model=InterviewSessionOut)
async def respond(session_id: UUID, body: InterviewRespondIn, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        session = (await s.execute(
            select(InterviewSession).where(InterviewSession.id == session_id, InterviewSession.user_id == uid)
        )).scalar_one_or_none()
        if not session:
            raise HTTPException(404, "Interview session not found")
        if session.status != "in_progress":
            raise HTTPException(400, "This interview has already ended")

        transcript = [*session.transcript, {"role": "candidate", "content": body.answer}]
        asked_so_far = sum(1 for t in transcript if t["role"] == "interviewer")
        if asked_so_far < interview_agent.MAX_QUESTIONS:
            profile, job_dict, company_research = await _application_context(s, uid, session.application_id)
            next_question = interview_agent.next_turn(profile, job_dict, company_research, transcript)
            transcript = [*transcript, {"role": "interviewer", "content": next_question}]
        # else: all MAX_QUESTIONS asked and answered — no more questions;
        # the frontend prompts the candidate to end and get feedback instead.

        row = (await s.execute(
            update(InterviewSession).where(InterviewSession.id == session_id)
            .values(transcript=transcript).returning(InterviewSession)
        )).scalar_one()
        return row


@router.post("/{session_id}/end", response_model=InterviewSessionOut)
async def end(session_id: UUID, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        session = (await s.execute(
            select(InterviewSession).where(InterviewSession.id == session_id, InterviewSession.user_id == uid)
        )).scalar_one_or_none()
        if not session:
            raise HTTPException(404, "Interview session not found")
        if session.status == "completed":
            return session
        if not session.transcript:
            raise HTTPException(400, "Nothing to debrief yet")

        _, job_dict, _ = await _application_context(s, uid, session.application_id)
        feedback = interview_agent.end_interview(job_dict, session.transcript)

        row = (await s.execute(
            update(InterviewSession).where(InterviewSession.id == session_id)
            .values(status="completed", feedback=feedback).returning(InterviewSession)
        )).scalar_one()
        return row


@router.get("/sessions", response_model=list[InterviewSessionOut])
async def list_sessions(application_id: UUID | None = None, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        stmt = select(InterviewSession).where(InterviewSession.user_id == uid)
        if application_id:
            stmt = stmt.where(InterviewSession.application_id == application_id)
        rows = (await s.execute(stmt.order_by(InterviewSession.created_at.desc()))).scalars().all()
        return rows


@router.get("/{session_id}", response_model=InterviewSessionOut)
async def get_session(session_id: UUID, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        session = (await s.execute(
            select(InterviewSession).where(InterviewSession.id == session_id, InterviewSession.user_id == uid)
        )).scalar_one_or_none()
        if not session:
            raise HTTPException(404, "Interview session not found")
        return session
