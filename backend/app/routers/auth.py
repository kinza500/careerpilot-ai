"""Auth endpoints. Registration and login use the SECURITY DEFINER SQL
functions so they can look up / create users without a broad RLS bypass."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from sqlalchemy import text

from app.agents import gmail_agent
from app.config import get_settings
from app.core.crypto import decrypt_bytes, encrypt_bytes
from app.core.security import (
    create_access_token,
    current_user,
    hash_password,
    verify_password,
)
from app.db import SessionLocal, tenant_session
from app.schemas import GoogleStatusOut, LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=TokenOut)
async def register(body: RegisterIn):
    async with SessionLocal() as s:
        async with s.begin():
            existing = await s.execute(
                text("SELECT id FROM auth_lookup_user(:e)"), {"e": body.email}
            )
            if existing.first():
                raise HTTPException(409, "Email already registered")
            res = await s.execute(
                text("SELECT auth_create_user(:e, :h, :n) AS id"),
                {"e": body.email, "h": hash_password(body.password), "n": body.full_name},
            )
            uid = res.scalar_one()
    return TokenOut(access_token=create_access_token(uid))


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn):
    async with SessionLocal() as s:
        async with s.begin():
            row = (await s.execute(
                text("SELECT id, password_hash FROM auth_lookup_user(:e)"),
                {"e": body.email},
            )).first()
    if not row or not verify_password(body.password, row.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return TokenOut(access_token=create_access_token(row.id))


@router.get("/me", response_model=UserOut)
async def me(uid: UUID = Depends(current_user)):
    # runs under RLS: the self_read policy means this only ever returns own row
    async with tenant_session(uid) as s:
        row = (await s.execute(
            text("SELECT id, email, full_name FROM users WHERE id = :id"), {"id": str(uid)}
        )).first()
    if not row:
        raise HTTPException(404, "User not found")
    return UserOut(id=row.id, email=row.email, full_name=row.full_name)


# --- Gmail draft integration (gmail.compose scope only; never sends) --------

@router.get("/google/authorize")
async def google_authorize(uid: UUID = Depends(current_user)):
    # The OAuth redirect is a full-page browser navigation with no Authorization
    # header, so the caller's identity is carried in `state` as a short-lived
    # signed JWT (reusing the same access-token machinery) instead.
    state = create_access_token(uid)
    return {"url": gmail_agent.build_authorize_url(state)}


@router.get("/google/callback")
async def google_callback(code: str, state: str):
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        uid = UUID(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise HTTPException(400, "Invalid or expired state")

    tokens = await gmail_agent.exchange_code(code)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Google omits refresh_token on repeat consents without prompt=consent;
        # we always pass prompt=consent, so this signals a real failure.
        raise HTTPException(400, "Google did not return a refresh token")
    email = await gmail_agent.get_email(tokens["access_token"])

    async with tenant_session(uid) as s:
        await s.execute(
            text("UPDATE users SET google_refresh_token_enc = :t, google_email = :e WHERE id = :id"),
            {"t": encrypt_bytes(refresh_token.encode()), "e": email, "id": str(uid)},
        )
    return RedirectResponse(url=f"{settings.frontend_origin}/dashboard?gmail_connected=1")


@router.get("/google/status", response_model=GoogleStatusOut)
async def google_status(uid: UUID = Depends(current_user)):
    """Re-checked on every call (the dashboard calls this on every login/mount,
    not just once) — a stored token can go dead between sessions (Google
    auto-expires refresh tokens after 7 days for unverified/testing apps, or
    the user can revoke access from their Google account), and this should
    read as disconnected rather than keep claiming "connected" until a draft
    action fails on it later."""
    async with tenant_session(uid) as s:
        row = (await s.execute(
            text("SELECT google_refresh_token_enc, google_email FROM users WHERE id = :id"),
            {"id": str(uid)},
        )).first()
    if not row or not row.google_refresh_token_enc:
        return GoogleStatusOut(connected=False, email=None)

    refresh_token = decrypt_bytes(row.google_refresh_token_enc).decode()
    try:
        access_token = await gmail_agent.refresh_access_token(refresh_token)
        readonly = await gmail_agent.has_readonly_scope(access_token)
        calendar = await gmail_agent.has_calendar_scope(access_token)
    except gmail_agent.GoogleTokenRevoked:
        # Google itself confirmed the token is dead — this is the only case
        # that should disconnect the user.
        async with tenant_session(uid) as s:
            await s.execute(
                text("UPDATE users SET google_refresh_token_enc = NULL, google_email = NULL WHERE id = :id"),
                {"id": str(uid)},
            )
        return GoogleStatusOut(connected=False, email=None)
    except Exception as exc:
        # Network hiccup, Google outage, etc. — NOT evidence of revocation.
        # Report the last-known state rather than destroying a valid token
        # over a transient failure.
        print(f"[google_status] couldn't verify token (treating as still connected): {exc}")
        return GoogleStatusOut(connected=True, email=row.google_email)

    return GoogleStatusOut(connected=True, email=row.google_email, has_readonly_scope=readonly, has_calendar_scope=calendar)
