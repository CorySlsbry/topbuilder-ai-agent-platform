"""Async database access with per-request tenant scoping.

Every request opens a transaction and sets `app.current_tenant` via `set_config(..., true)`
(transaction-local). Because the app connects as the non-superuser `app_user` role, the RLS
policies in migrations/0002_rls.sql are *enforced* — see ADR 0002.
"""
from __future__ import annotations

import asyncio
import ssl
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def db_ssl_context(database_url: str, verify: bool | None = None) -> ssl.SSLContext | None:
    """A TLS-1.2-minimum SSL context for a REMOTE database host, or None for a local socket.

    Encryption in transit is mandatory for the managed (Supabase) connection — TLS 1.2 is the floor.
    Default is encrypt-only (no CA/hostname verification) so the pooler's cert chain can never break
    connectivity; set ``db_ssl_verify=true`` (or pass ``verify=True``) to require full certificate
    validation once the pooler CA is pinned. Local dev (loopback Postgres) needs no TLS context.
    """
    host = (urlparse(database_url.replace("postgresql+asyncpg", "postgresql")).hostname or "").lower()
    if host in _LOCAL_HOSTS or host.endswith(".local"):
        return None
    if verify is None:
        verify = get_settings().db_ssl_verify
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx

# An async engine is bound to the event loop it was created on. In prod there is one loop, so this
# behaves like a singleton. Under pytest each test gets its own loop, so we key by loop to avoid
# "attached to a different loop" errors. `.cache_clear()` is kept for test-teardown compatibility.
_engines: dict[int, AsyncEngine] = {}
_sessionmakers: dict[int, async_sessionmaker[AsyncSession]] = {}


def _loop_key() -> int:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return 0


def get_engine() -> AsyncEngine:
    key = _loop_key()
    engine = _engines.get(key)
    if engine is None:
        # asyncpg connect args. Transaction-mode pooler (Supabase Supavisor :6543) compatibility:
        # asyncpg must not cache prepared statements when the pooler multiplexes clients over
        # backends, or we get DuplicatePreparedStatement errors and (in session mode) the
        # EMAXCONNSESSION cap that capped concurrency at ~10 requests. The matching dialect-level
        # `prepared_statement_cache_size=0` is set in the DATABASE_URL query string. The TLS-1.2
        # context pins encryption-in-transit for the remote (managed) connection.
        connect_args: dict[str, object] = {"statement_cache_size": 0}
        ssl_ctx = db_ssl_context(get_settings().database_url)
        if ssl_ctx is not None:
            connect_args["ssl"] = ssl_ctx
        engine = create_async_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            future=True,
            connect_args=connect_args,
        )
        _engines[key] = engine
    return engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    key = _loop_key()
    maker = _sessionmakers.get(key)
    if maker is None:
        maker = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
        _sessionmakers[key] = maker
    return maker


get_engine.cache_clear = _engines.clear  # type: ignore[attr-defined]
get_sessionmaker.cache_clear = _sessionmakers.clear  # type: ignore[attr-defined]


@asynccontextmanager
async def tenant_session(tenant_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Yield a session whose transaction is pinned to `tenant_id` for RLS.

    All queries issued on the yielded session see only rows for this tenant. The setting is
    transaction-local, so it cannot leak across pooled connections.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_tenant', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            yield session


@asynccontextmanager
async def operator_session() -> AsyncIterator[AsyncSession]:
    """Yield a session for PLATFORM-OPERATOR (non-tenant) data — the Ads-CRM tables (ADR 0009).

    Sets `app.operator='on'` (transaction-local) so the operator-only RLS policies in
    migrations/0023_ads_crm.sql grant access. It does NOT set `app.current_tenant`, so tenant tables
    remain unreachable from this session. This is defense-in-depth UNDER the app-layer operator gate
    (require_admin + the PLATFORM_OPERATOR_EMAILS allowlist): a normal tenant_session (app.operator
    unset) sees ZERO rows in the operator tables, fail-closed.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(text("SELECT set_config('app.operator', 'on', true)"))
            yield session


async def healthcheck() -> bool:
    """Lightweight DB liveness probe (no tenant context required)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar_one() == 1
