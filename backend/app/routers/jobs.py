"""Job discovery + ranking endpoints. Discovery and ranking run the LangGraph
pipeline; results are persisted per-user (RLS-scoped) and returned with
explainable reasoning."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents.graph import run_pipeline
from app.core.security import current_user
from app.db import tenant_session
from app.models import Application, Job, Match, SkillProfile
from app.schemas import DiscoverIn, JobOut, MatchOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


async def _saved_job_ids(s, uid: UUID) -> set[UUID]:
    """Jobs the user has already saved for later — these shouldn't clutter
    current listings since they're no longer something to act on."""
    rows = (await s.execute(
        select(Application.job_id).where(Application.user_id == uid, Application.status == "approved")
    )).scalars().all()
    return set(rows)


@router.post("/discover", response_model=list[MatchOut])
async def discover_and_rank(body: DiscoverIn, uid: UUID = Depends(current_user)):
    # need the latest profile to rank against
    async with tenant_session(uid) as s:
        profile_row = (await s.execute(
            select(SkillProfile).where(SkillProfile.user_id == uid)
            .order_by(SkillProfile.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if not profile_row:
        raise HTTPException(400, "Upload a resume first")

    state = run_pipeline({
        "profile": profile_row.profile,
        "profile_emb": profile_row.embedding,
        "query": body.query,
        "location": body.location,
        "work_type": body.work_type,
        "limit": body.limit,
    })

    jobs = state.get("jobs", [])
    ranked = state.get("ranked", [])
    if not jobs:
        return []

    by_tmp = {j["tmp_id"]: j for j in jobs}

    # Persist jobs (upsert on natural key); build tmp_id -> db id map.
    tmp_to_db: dict[str, UUID] = {}
    async with tenant_session(uid) as s:
        for j in jobs:
            jid = uuid4()
            stmt = pg_insert(Job).values(
                id=jid, user_id=uid, source=j["source"], external_id=j["external_id"],
                title=j["title"], company=j["company"], location=j["location"],
                remote=j["remote"], salary=str(j["salary"]) if j["salary"] else None,
                url=j["url"], company_url=j.get("company_url"), description=j["description"],
                contact_email=j.get("contact_email"), embedding=j.get("embedding"),
            ).on_conflict_do_nothing(index_elements=["user_id", "source", "external_id"]) \
             .returning(Job.id)
            res = (await s.execute(stmt)).scalar_one_or_none()
            if res is None:  # conflict: fetch the existing row's id
                res = (await s.execute(
                    select(Job.id).where(Job.user_id == uid, Job.source == j["source"],
                                         Job.external_id == j["external_id"])
                )).scalar_one_or_none() or jid
            tmp_to_db[j["tmp_id"]] = res

    # Persist matches and build the response (ranked is already sorted desc).
    out: list[MatchOut] = []
    async with tenant_session(uid) as s:
        saved_ids = await _saved_job_ids(s, uid)
        for r in ranked:
            j = by_tmp.get(r["tmp_id"])
            db_job_id = tmp_to_db.get(r["tmp_id"])
            if j is None or db_job_id is None:
                continue
            stmt = pg_insert(Match).values(
                id=uuid4(), user_id=uid, job_id=db_job_id, profile_id=profile_row.id,
                score=r["score"], reasoning=r["reasoning"], factors=r["factors"],
            ).on_conflict_do_update(
                index_elements=["user_id", "job_id", "profile_id"],
                set_={"score": r["score"], "reasoning": r["reasoning"], "factors": r["factors"]},
            )
            await s.execute(stmt)
            if db_job_id in saved_ids:  # already saved for later — don't relist it
                continue
            out.append(MatchOut(
                id=db_job_id,
                job=JobOut(id=db_job_id, title=j["title"], company=j["company"],
                           location=j["location"], remote=j["remote"],
                           salary=str(j["salary"]) if j["salary"] else None,
                           url=j["url"], source=j["source"],
                           company_url=j.get("company_url"),
                           contact_email=j.get("contact_email")),
                score=r["score"], reasoning=r["reasoning"], factors=r["factors"],
            ))
    return out


@router.get("/matches", response_model=list[MatchOut])
async def list_matches(uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        # Only surface matches computed against the current resume/profile —
        # otherwise a stale ranking from before a resume replace keeps reappearing.
        latest_profile_id = (await s.execute(
            select(SkillProfile.id).where(SkillProfile.user_id == uid)
            .order_by(SkillProfile.created_at.desc()).limit(1)
        )).scalar_one_or_none()
        if latest_profile_id is None:
            return []
        saved_ids = await _saved_job_ids(s, uid)
        rows = (await s.execute(
            select(Match, Job).join(Job, Job.id == Match.job_id)
            .where(Match.profile_id == latest_profile_id, Match.user_id == uid)
            .order_by(Match.score.desc()).limit(50)
        )).all()
    return [
        MatchOut(
            id=m.job_id,
            job=JobOut(id=j.id, title=j.title, company=j.company, location=j.location,
                       remote=j.remote, salary=j.salary, url=j.url, source=j.source,
                       company_url=j.company_url, contact_email=j.contact_email),
            score=m.score, reasoning=m.reasoning, factors=m.factors,
        )
        for m, j in rows if j.id not in saved_ids
    ]
