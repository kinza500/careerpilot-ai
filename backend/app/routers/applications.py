"""Application endpoints — preparation and saving for later.

/prepare runs the Resume-Optimiser → Writer → Critic loop and stores a DRAFT in
status 'review'. /approve flips status to 'approved' purely to mark it as
finalised/saved for the user's own tracking — CareerPilot never sends
anything on its own; the user finds and sends the application themselves
(optionally via the Gmail draft created by /draft-gmail).
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents import gmail_agent
from app.agents.application_agents import prepare_application
from app.agents.stubs import draft_followup, extract_interview_schedule, research_company
from app.core.crypto import decrypt_bytes
from app.core.security import current_user
from app.db import tenant_session
from app.models import Application, Job, MemoryEvent, Resume, SkillProfile
from app.schemas import (
    ApplicationEventOut,
    ApplicationOut,
    ApproveIn,
    FollowupDraftOut,
    FollowupOut,
    GmailDraftOut,
    JobOut,
    PrepIn,
)

router = APIRouter(prefix="/applications", tags=["applications"])

# A follow-up is only offered once the application email was actually sent
# (detected via Gmail, same signal as Application.email_sent) — drafting or
# saving for later alone doesn't start the clock, since there's nothing to
# follow up on until something has actually gone out.
FOLLOWUP_TRIGGER_EVENT = "application_email_sent"
FOLLOWUP_DAYS = 14


def _to_out(a: Application, job: Job, resume: Resume | None = None) -> ApplicationOut:
    return ApplicationOut(
        id=a.id, job_id=a.job_id, status=a.status,
        job=JobOut(id=job.id, title=job.title, company=job.company, location=job.location,
                   remote=job.remote, salary=job.salary, url=job.url, source=job.source,
                   company_url=job.company_url, contact_email=job.contact_email),
        resume_filename=resume.filename if resume else None,
        resume_uploaded_at=resume.created_at if resume else None,
        tailored_resume=a.tailored_resume, cover_letter=a.cover_letter,
        outreach_email=a.outreach_email, critic_notes=a.critic_notes,
        company_research=a.company_research,
        company_research_grounded=a.company_research_grounded,
        company_research_sources=a.company_research_sources or [],
        followup_status=a.followup_status,
        has_gmail_draft=bool(a.gmail_thread_id),
        email_sent=a.email_sent,
        reply_received=a.reply_received,
        interview_schedule=a.interview_schedule,
        calendar_event_id=a.calendar_event_id,
    )


async def _resume_for_profile(s, profile_id: UUID | None) -> Resume | None:
    if profile_id is None:
        return None
    row = (await s.execute(
        select(Resume).join(SkillProfile, SkillProfile.resume_id == Resume.id)
        .where(SkillProfile.id == profile_id)
    )).scalar_one_or_none()
    return row


async def _log_event(s, uid: UUID, kind: str, application_id: UUID, job_id: UUID | None = None) -> None:
    """Full audit trail of every action taken on an application — prepared,
    saved for later, drafted to Gmail, followed up — for the user's own record."""
    await s.execute(pg_insert(MemoryEvent).values(
        id=uuid4(), user_id=uid, kind=kind,
        payload={"application_id": str(application_id), "job_id": str(job_id) if job_id else None},
    ))


async def _email_sent_at(s, application_id: UUID) -> datetime | None:
    return (await s.execute(
        select(func.min(MemoryEvent.created_at)).where(
            MemoryEvent.kind == FOLLOWUP_TRIGGER_EVENT,
            MemoryEvent.payload["application_id"].astext == str(application_id),
        )
    )).scalar_one_or_none()


@router.post("/prepare", response_model=ApplicationOut)
async def prepare(body: PrepIn, uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        job = (await s.execute(select(Job).where(Job.id == body.job_id))).scalar_one_or_none()
        profile = (await s.execute(
            select(SkillProfile).where(SkillProfile.user_id == uid)
            .order_by(SkillProfile.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    if not profile:
        raise HTTPException(400, "Upload a resume first")

    job_dict = {"title": job.title, "company": job.company, "location": job.location,
                "description": job.description}
    research = research_company(job.company)
    package = prepare_application(profile.profile, job_dict, research["brief"])

    app_id = uuid4()
    async with tenant_session(uid) as s:
        stmt = pg_insert(Application).values(
            id=app_id, user_id=uid, job_id=body.job_id, profile_id=profile.id, status="review",
            tailored_resume=package["tailored_resume"],
            cover_letter=package["cover_letter"],
            outreach_email=package["outreach_email"],
            critic_notes=package["critic_notes"],
            company_research=research["brief"],
            company_research_grounded=research["grounded"],
            company_research_sources=research["sources"],
        ).on_conflict_do_update(
            index_elements=["user_id", "job_id"],
            set_={
                "profile_id": profile.id,
                "status": "review",
                "tailored_resume": package["tailored_resume"],
                "cover_letter": package["cover_letter"],
                "outreach_email": package["outreach_email"],
                "critic_notes": package["critic_notes"],
                "company_research": research["brief"],
                "company_research_grounded": research["grounded"],
                "company_research_sources": research["sources"],
            },
        ).returning(Application)
        row = (await s.execute(stmt)).scalar_one()
        await _log_event(s, uid, "application_prepared", row.id, job.id)
        resume = await _resume_for_profile(s, row.profile_id)
        return _to_out(row, job, resume)


@router.post("/approve", response_model=ApplicationOut)
async def approve(body: ApproveIn, uid: UUID = Depends(current_user)):
    """Mark an application as finalised/saved. This only updates status for the
    user's own tracking — CareerPilot has no send capability of any kind."""
    if not body.confirm:
        raise HTTPException(400, "Saving requires explicit confirmation")
    async with tenant_session(uid) as s:
        row = (await s.execute(
            update(Application).where(Application.id == body.application_id)
            .values(status="approved").returning(Application)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Application not found")
        job = (await s.execute(select(Job).where(Job.id == row.job_id))).scalar_one()
        await _log_event(s, uid, "application_saved_for_later", row.id, job.id)
        resume = await _resume_for_profile(s, row.profile_id)
    return _to_out(row, job, resume)


@router.get("", response_model=list[ApplicationOut])
async def list_applications(uid: UUID = Depends(current_user)):
    """Lists every application, opportunistically checking Gmail (readonly)
    for any that are drafted-but-not-yet-confirmed-sent — same pattern as the
    reply check in /followups-due. Only ever detects what the user already
    did in Gmail themselves; CareerPilot still never sends anything."""
    access_token: str | None = None
    async with tenant_session(uid) as s:
        token_row = (await s.execute(
            text("SELECT google_refresh_token_enc FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()
    if token_row and token_row.google_refresh_token_enc:
        try:
            refresh_token = decrypt_bytes(token_row.google_refresh_token_enc).decode()
            access_token = await gmail_agent.refresh_access_token(refresh_token)
        except Exception as exc:  # revoked/expired — degrade to no sent-detection this load
            print(f"[applications] Gmail token refresh failed: {exc}")

    async with tenant_session(uid) as s:
        rows = (await s.execute(
            select(Application, Job, Resume)
            .join(Job, Job.id == Application.job_id)
            .outerjoin(SkillProfile, SkillProfile.id == Application.profile_id)
            .outerjoin(Resume, Resume.id == SkillProfile.resume_id)
            .order_by(Application.updated_at.desc())
        )).all()

        if access_token:
            for a, j, _r in rows:
                if a.gmail_thread_id and not a.email_sent:
                    sent = await gmail_agent.count_sent_in_thread(access_token, a.gmail_thread_id)
                    if sent is not None and sent > 0:
                        await s.execute(update(Application).where(Application.id == a.id).values(email_sent=True))
                        await _log_event(s, uid, "application_email_sent", a.id, j.id)
                        a.email_sent = True

                # Reply detection here is deliberately NOT gated behind the
                # 14-day follow-up wait (unlike followup_status='responded')
                # so the Applications list reflects a reply the moment it
                # actually lands, not two weeks later.
                if a.gmail_thread_id and not a.reply_received:
                    has_reply = await gmail_agent.thread_has_reply(access_token, a.gmail_thread_id)
                    if has_reply:
                        await s.execute(update(Application).where(Application.id == a.id).values(reply_received=True))
                        await _log_event(s, uid, "application_reply_received", a.id, j.id)
                        a.reply_received = True

                # Once a reply exists, look at what it actually says — ONLY to
                # check for a specific interview date/time to suggest, never
                # acted on automatically (see /schedule-interview/confirm).
                # _checked prevents re-running this every single page load.
                if a.reply_received and not a.interview_schedule_checked:
                    reply_text = await gmail_agent.get_latest_reply_text(access_token, a.gmail_thread_id)
                    suggestion = extract_interview_schedule(reply_text, {"title": j.title, "company": j.company})
                    await s.execute(
                        update(Application).where(Application.id == a.id)
                        .values(interview_schedule=suggestion, interview_schedule_checked=True)
                    )
                    if suggestion:
                        await _log_event(s, uid, "interview_schedule_suggested", a.id, j.id)
                    a.interview_schedule = suggestion
                    a.interview_schedule_checked = True

                if a.followup_status == "drafted" and a.followup_gmail_thread_id:
                    sent = await gmail_agent.count_sent_in_thread(access_token, a.followup_gmail_thread_id)
                    if sent is not None and sent > a.followup_sent_baseline:
                        await s.execute(update(Application).where(Application.id == a.id).values(followup_status="sent"))
                        await _log_event(s, uid, "followup_email_sent", a.id, j.id)
                        a.followup_status = "sent"

    return [_to_out(a, j, r) for a, j, r in rows]


@router.post("/{application_id}/schedule-interview/confirm", response_model=ApplicationOut)
async def confirm_interview_schedule(application_id: UUID, uid: UUID = Depends(current_user)):
    """Create the suggested interview slot as a real calendar event — ONLY
    ever called by an explicit user click; nothing schedules itself off the
    back of just reading a reply. Uses the exact date/time already extracted
    and shown to the user, not a fresh re-read of the email."""
    async with tenant_session(uid) as s:
        app_row = (await s.execute(
            select(Application).where(Application.id == application_id)
        )).scalar_one_or_none()
        if not app_row:
            raise HTTPException(404, "Application not found")
        if not app_row.interview_schedule:
            raise HTTPException(400, "No interview schedule suggestion to confirm")
        job = (await s.execute(select(Job).where(Job.id == app_row.job_id))).scalar_one()
        token_row = (await s.execute(
            text("SELECT google_refresh_token_enc FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()

    if not token_row or not token_row.google_refresh_token_enc:
        raise HTTPException(400, "Connect Gmail first")

    sched = app_row.interview_schedule
    tz_name = sched.get("timezone") or "UTC"
    try:
        start = datetime.fromisoformat(f"{sched['date']}T{sched['time']}:00")
    except (KeyError, ValueError):
        raise HTTPException(400, "The suggested schedule is missing a valid date/time")
    end = start + timedelta(minutes=sched.get("duration_minutes") or 60)

    refresh_token = decrypt_bytes(token_row.google_refresh_token_enc).decode()
    access_token = await gmail_agent.refresh_access_token(refresh_token)
    event = await gmail_agent.create_calendar_event(
        access_token,
        summary=sched.get("summary") or f"Interview: {job.title} at {job.company or 'company'}",
        description=(
            f"Auto-suggested by CareerPilot from a reply on this application.\n\n"
            f"Location/method: {sched.get('location_or_method') or 'not specified in the email'}"
        ),
        start_iso=start.isoformat(), end_iso=end.isoformat(), timezone=tz_name,
        location=sched.get("location_or_method"),
    )

    async with tenant_session(uid) as s:
        row = (await s.execute(
            update(Application).where(Application.id == application_id)
            .values(calendar_event_id=event.get("id")).returning(Application)
        )).scalar_one()
        await _log_event(s, uid, "interview_scheduled_confirmed", application_id, job.id)
        resume = await _resume_for_profile(s, row.profile_id)
    return _to_out(row, job, resume)


@router.post("/{application_id}/schedule-interview/dismiss", response_model=ApplicationOut)
async def dismiss_interview_schedule(application_id: UUID, uid: UUID = Depends(current_user)):
    """Discard a suggested interview slot without creating anything — e.g.
    the extraction was wrong, or it's not actually relevant."""
    async with tenant_session(uid) as s:
        row = (await s.execute(
            update(Application).where(Application.id == application_id)
            .values(interview_schedule=None).returning(Application)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Application not found")
        job = (await s.execute(select(Job).where(Job.id == row.job_id))).scalar_one()
        await _log_event(s, uid, "interview_schedule_dismissed", application_id, job.id)
        resume = await _resume_for_profile(s, row.profile_id)
    return _to_out(row, job, resume)


@router.post("/{application_id}/draft-gmail", response_model=GmailDraftOut)
async def draft_gmail(application_id: UUID, uid: UUID = Depends(current_user)):
    """Create a Gmail draft: outreach email as the body, cover letter and
    tailored resume attached as .docx files. gmail.compose scope only — this
    never sends anything; the user reviews and sends it themselves from Gmail."""
    async with tenant_session(uid) as s:
        app_row = (await s.execute(
            select(Application).where(Application.id == application_id)
        )).scalar_one_or_none()
        if not app_row:
            raise HTTPException(404, "Application not found")
        job = (await s.execute(select(Job).where(Job.id == app_row.job_id))).scalar_one()
        token_row = (await s.execute(
            text("SELECT google_refresh_token_enc FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()
        resume = await _resume_for_profile(s, app_row.profile_id)

    if not token_row or not token_row.google_refresh_token_enc:
        raise HTTPException(400, "Connect Gmail first")

    # The exact file the user uploaded, attached as-is (whatever format it
    # already is — PDF stays PDF) so its layout is guaranteed unchanged,
    # rather than risking a lossy re-conversion into another format.
    original_resume = None
    if resume:
        original_resume = (decrypt_bytes(resume.ciphertext), resume.filename, resume.mime_type)

    refresh_token = decrypt_bytes(token_row.google_refresh_token_enc).decode()
    access_token = await gmail_agent.refresh_access_token(refresh_token)
    subject = f"Application for {job.title} at {job.company or 'your company'}"
    body = app_row.outreach_email or app_row.cover_letter or ""
    draft = await gmail_agent.create_draft(
        access_token, subject, body,
        cover_letter=app_row.cover_letter,
        tailored_resume=app_row.tailored_resume,
        original_resume=original_resume,
    )

    message_id = draft.get("message", {}).get("id")
    thread_id = draft.get("message", {}).get("threadId")
    url = f"https://mail.google.com/mail/u/0/#drafts?compose={message_id}" if message_id else None

    # Capture thread continuity so a 14-day follow-up (if one is ever drafted)
    # can reply into this same Gmail conversation instead of starting a new one.
    rfc_message_id = await gmail_agent.get_message_id_header(access_token, message_id) if message_id else None
    async with tenant_session(uid) as s:
        await s.execute(
            update(Application).where(Application.id == application_id)
            .values(gmail_thread_id=thread_id, gmail_message_id=rfc_message_id)
        )
        await _log_event(s, uid, "application_gmail_draft_created", application_id, job.id)

    return GmailDraftOut(draft_id=draft["id"], url=url)


@router.get("/followups-due", response_model=list[FollowupOut])
async def followups_due(uid: UUID = Depends(current_user)):
    """Applications whose email was actually sent (detected via Gmail) 14+
    days ago, with no reply since. The thread is checked (gmail.readonly) for
    an actual reply first — if one arrived, the application is marked
    'responded' and never surfaced as needing a follow-up. Applications that
    were only saved for later or drafted but never sent don't start the
    14-day clock at all, since there's nothing to follow up on yet."""
    now = datetime.now(timezone.utc)

    access_token: str | None = None
    async with tenant_session(uid) as s:
        token_row = (await s.execute(
            text("SELECT google_refresh_token_enc FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()
    if token_row and token_row.google_refresh_token_enc:
        try:
            refresh_token = decrypt_bytes(token_row.google_refresh_token_enc).decode()
            access_token = await gmail_agent.refresh_access_token(refresh_token)
        except Exception as exc:  # revoked/expired — degrade to time-based only
            print(f"[followups] Gmail token refresh failed: {exc}")

    out: list[FollowupOut] = []
    async with tenant_session(uid) as s:
        candidates = (await s.execute(
            select(Application, Job).join(Job, Job.id == Application.job_id)
            .where(Application.followup_status.is_(None), Application.email_sent.is_(True))
        )).all()
        for a, job in candidates:
            sent_at = await _email_sent_at(s, a.id)
            if sent_at is None:
                continue
            if sent_at.tzinfo is None:
                sent_at = sent_at.replace(tzinfo=timezone.utc)
            days_since = (now - sent_at).days
            if days_since < FOLLOWUP_DAYS:
                continue

            reply_checked = False
            if access_token and a.gmail_thread_id:
                has_reply = await gmail_agent.thread_has_reply(access_token, a.gmail_thread_id)
                if has_reply is True:
                    await s.execute(
                        update(Application).where(Application.id == a.id)
                        .values(followup_status="responded")
                    )
                    await _log_event(s, uid, "followup_auto_responded", a.id, job.id)
                    continue
                reply_checked = has_reply is False  # False = checked cleanly, no reply found

            if not a.followup_email:
                followup_text = draft_followup(
                    {"title": job.title, "company": job.company}, days_since
                )
                await s.execute(
                    update(Application).where(Application.id == a.id)
                    .values(followup_email=followup_text)
                )
                a.followup_email = followup_text

            out.append(FollowupOut(
                application_id=a.id,
                job=JobOut(id=job.id, title=job.title, company=job.company, location=job.location,
                           remote=job.remote, salary=job.salary, url=job.url, source=job.source,
                           company_url=job.company_url, contact_email=job.contact_email),
                days_since_applied=days_since,
                followup_email=a.followup_email,
                can_thread=bool(a.gmail_thread_id and a.gmail_message_id),
                reply_checked=reply_checked,
            ))
    return out


@router.post("/{application_id}/followup/save", response_model=FollowupDraftOut)
async def followup_save(application_id: UUID, uid: UUID = Depends(current_user)):
    """Save the follow-up for later without sending anything anywhere."""
    async with tenant_session(uid) as s:
        row = (await s.execute(
            update(Application).where(Application.id == application_id)
            .values(followup_status="saved").returning(Application)
        )).scalar_one_or_none()
        if not row:
            raise HTTPException(404, "Application not found")
        await _log_event(s, uid, "followup_saved", application_id, row.job_id)
    return FollowupDraftOut(application_id=application_id, followup_status="saved")


@router.post("/{application_id}/followup/draft-gmail", response_model=FollowupDraftOut)
async def followup_draft_gmail(application_id: UUID, uid: UUID = Depends(current_user)):
    """Create the follow-up as a Gmail draft — threaded into the original
    application's conversation when it was itself drafted via Gmail."""
    async with tenant_session(uid) as s:
        app_row = (await s.execute(
            select(Application).where(Application.id == application_id)
        )).scalar_one_or_none()
        if not app_row:
            raise HTTPException(404, "Application not found")
        job = (await s.execute(select(Job).where(Job.id == app_row.job_id))).scalar_one()
        token_row = (await s.execute(
            text("SELECT google_refresh_token_enc FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()

    if not token_row or not token_row.google_refresh_token_enc:
        raise HTTPException(400, "Connect Gmail first")
    if not app_row.followup_email:
        raise HTTPException(400, "No follow-up generated yet — check /applications/followups-due first")

    refresh_token = decrypt_bytes(token_row.google_refresh_token_enc).decode()
    access_token = await gmail_agent.refresh_access_token(refresh_token)

    threaded = bool(app_row.gmail_thread_id and app_row.gmail_message_id)
    # Baseline count of already-sent messages in the thread this follow-up
    # will land in — captured BEFORE creating the draft, so later sent-
    # detection can tell "the follow-up was sent" apart from "the original
    # application email was already sent" when they share a thread.
    baseline = 0
    if threaded:
        baseline = await gmail_agent.count_sent_in_thread(access_token, app_row.gmail_thread_id) or 0

    subject = f"Re: Application for {job.title} at {job.company or 'your company'}"
    draft = await gmail_agent.create_draft(
        access_token, subject, app_row.followup_email,
        thread_id=app_row.gmail_thread_id if threaded else None,
        in_reply_to=app_row.gmail_message_id if threaded else None,
    )
    message_id = draft.get("message", {}).get("id")
    followup_thread_id = draft.get("message", {}).get("threadId")
    url = f"https://mail.google.com/mail/u/0/#drafts?compose={message_id}" if message_id else None

    async with tenant_session(uid) as s:
        await s.execute(
            update(Application).where(Application.id == application_id)
            .values(followup_status="drafted", followup_gmail_thread_id=followup_thread_id,
                    followup_sent_baseline=baseline)
        )
        await _log_event(s, uid, "followup_gmail_draft_created", application_id, job.id)

    return FollowupDraftOut(
        application_id=application_id, followup_status="drafted",
        draft_id=draft["id"], url=url, threaded=threaded,
    )


@router.get("/{application_id}/history", response_model=list[ApplicationEventOut])
async def application_history(application_id: UUID, uid: UUID = Depends(current_user)):
    """Full audit trail for one application — every prepare/save/draft/
    follow-up action taken on it, in order."""
    async with tenant_session(uid) as s:
        app_row = (await s.execute(
            select(Application.id).where(Application.id == application_id)
        )).scalar_one_or_none()
        if not app_row:
            raise HTTPException(404, "Application not found")
        rows = (await s.execute(
            select(MemoryEvent).where(
                MemoryEvent.payload["application_id"].astext == str(application_id)
            ).order_by(MemoryEvent.created_at.asc())
        )).scalars().all()
    return [ApplicationEventOut(kind=r.kind, created_at=r.created_at) for r in rows]
