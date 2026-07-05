"""Database access with per-request Row-Level Security scoping.

The critical function here is `tenant_session`: it opens a transaction and sets
`app.current_user_id` (a Postgres GUC) *inside that transaction* before any
query runs. Every RLS policy checks that GUC, so a query can only ever touch
the current user's rows — even if the ORM code forgets a filter.
"""
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@asynccontextmanager
async def tenant_session(user_id: UUID | None) -> AsyncIterator[AsyncSession]:
    """Yield a session whose transaction is scoped to `user_id` via RLS.

    Pass user_id=None only for the auth path (register/login), which uses the
    SECURITY DEFINER SQL functions and touches no tenant tables directly.
    """
    async with SessionLocal() as session:
        async with session.begin():
            if user_id is not None:
                # set_config(..., true) => scoped to this transaction only.
                await session.execute(
                    text("SELECT set_config('app.current_user_id', :uid, true)"),
                    {"uid": str(user_id)},
                )
            yield session


async def raw_auth_session() -> AsyncIterator[AsyncSession]:
    """Session for auth RPCs (auth_lookup_user / auth_create_user)."""
    async with SessionLocal() as session:
        async with session.begin():
            yield session
