"""Resume endpoints.

Upload flow: bytes are hashed, ENCRYPTED, and stored; then the Resume
Understanding Agent decrypts in-memory to produce a structured profile +
embedding. Plaintext resume bytes are never persisted and never logged.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import insert, select

from app.agents.resume_agent import parse_resume
from app.core.crypto import decrypt_bytes, encrypt_bytes, sha256_hex
from app.core.security import current_user
from app.db import tenant_session
from app.models import Resume, SkillProfile
from app.schemas import ProfileOut

router = APIRouter(prefix="/resumes", tags=["resumes"])

MAX_BYTES = 5 * 1024 * 1024


@router.post("/upload", response_model=ProfileOut)
async def upload_resume(file: UploadFile, uid: UUID = Depends(current_user)):
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File too large (5MB max)")

    ciphertext = encrypt_bytes(data)                 # encrypt before storage
    digest = sha256_hex(data)
    resume_id = uuid4()

    async with tenant_session(uid) as s:
        await s.execute(insert(Resume).values(
            id=resume_id, user_id=uid, filename=file.filename or "resume",
            mime_type=file.content_type or "application/octet-stream",
            ciphertext=ciphertext, sha256=digest,
        ))

    # Parse in-memory (data still in scope; encrypted at rest already).
    profile, embedding = parse_resume(data, file.content_type or "", file.filename or "")
    del data  # drop plaintext reference promptly

    profile_id = uuid4()
    async with tenant_session(uid) as s:
        await s.execute(insert(SkillProfile).values(
            id=profile_id, user_id=uid, resume_id=resume_id,
            profile=profile, embedding=embedding,
        ))
    return ProfileOut(id=profile_id, resume_id=resume_id, profile=profile, created_at=datetime.now(timezone.utc))


@router.get("/profile", response_model=ProfileOut)
async def latest_profile(uid: UUID = Depends(current_user)):
    async with tenant_session(uid) as s:
        row = (await s.execute(
            select(SkillProfile).order_by(SkillProfile.created_at.desc()).limit(1)
        )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "No profile yet — upload a resume first")
    return ProfileOut(id=row.id, resume_id=row.resume_id, profile=row.profile, created_at=row.created_at)


@router.get("/{resume_id}/download")
async def download_resume(resume_id: UUID, uid: UUID = Depends(current_user)):
    """Decrypt and return the original file — only ever for its owner (RLS + the
    tenant session guarantee the row belongs to this user)."""
    from fastapi.responses import Response
    async with tenant_session(uid) as s:
        row = (await s.execute(
            select(Resume).where(Resume.id == resume_id)
        )).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Not found")
    plaintext = decrypt_bytes(row.ciphertext)
    return Response(content=plaintext, media_type=row.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="{row.filename}"'})
