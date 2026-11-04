"""user_memberships — the auth directory (IdP user -> tenant + role).

Resolution runs BEFORE any tenant context exists, so these reads use a plain (no-GUC) session:
the table is a routing directory with permissive RLS for the app role (see migration 0013), and
holds no customer business data. Writes are exposed only through the operator-only admin API.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text

from app.db import get_sessionmaker


@dataclass(frozen=True)
class Membership:
    id: uuid.UUID
    auth_user_id: uuid.UUID | None
    email: str
    tenant_id: uuid.UUID
    role: str
    status: str
    department: str | None = None  # NULL = unrestricted / executive view
    person_id: uuid.UUID | None = None  # link to the org_people row this login represents


def _row_to_membership(row) -> Membership:
    return Membership(
        id=row.id,
        auth_user_id=row.auth_user_id,
        email=row.email,
        tenant_id=row.tenant_id,
        role=row.role,
        status=row.status,
        department=row.department,
        person_id=row.person_id,
    )


async def resolve(*, auth_user_id: uuid.UUID, email: str | None) -> Membership | None:
    """Find the active membership for a verified IdP identity.

    Prefer the auth_user_id link; fall back to the e-mail invite and backfill auth_user_id on
    first login (the standard invite pattern).
    """
    maker = get_sessionmaker()
    first_login = False  # the backfill actually linked a previously-unlinked invite = a "new signup"
    async with maker() as session:
        async with session.begin():  # one transaction for the lookup + the first-login backfill
            row = (
                await session.execute(
                    text(
                        "SELECT id, auth_user_id, email, tenant_id, role, status, department, person_id "
                        "FROM user_memberships "
                        "WHERE auth_user_id = :uid AND status = 'active' "
                        "ORDER BY role = 'admin' DESC, created_at LIMIT 1"
                    ),
                    {"uid": str(auth_user_id)},
                )
            ).first()
            if row is None and email:
                row = (
                    await session.execute(
                        text(
                            "SELECT id, auth_user_id, email, tenant_id, role, status, department, person_id "
                            "FROM user_memberships "
                            "WHERE lower(email) = lower(:email) AND status = 'active' "
                            "ORDER BY role = 'admin' DESC, created_at LIMIT 1"
                        ),
                        {"email": email},
                    )
                ).first()
                if row is not None and row.auth_user_id is None:
                    updated = await session.execute(
                        text(
                            "UPDATE user_memberships SET auth_user_id = :uid, updated_at = now() "
                            "WHERE id = :id AND auth_user_id IS NULL"
                        ),
                        {"uid": str(auth_user_id), "id": str(row.id)},
                    )
                    first_login = updated.rowcount == 1  # fires exactly ONCE per invited account
        membership = _row_to_membership(row) if row is not None else None
    if membership is not None and first_login:
        # Operator reporting (AFTER commit): a new user activated their invite. Scheduled FIRE-AND-FORGET
        # so neither a notification failure nor its transport latency can delay the login the user is
        # mid-flight on. The rowcount==1 guard above already ensures this fires exactly once per account.
        try:
            from app.notify.capture import schedule_capture

            schedule_capture(
                kind="signup",
                name=None,
                email=membership.email,
                message=f"{membership.email} activated their account (role={membership.role})",
                source="membership",
                meta={"tenant_id": str(membership.tenant_id), "role": membership.role},
            )
        except Exception:  # pragma: no cover - scheduling is already best-effort internally
            pass
    return membership


async def list_for_tenant(tenant_id: uuid.UUID) -> list[dict]:
    maker = get_sessionmaker()
    async with maker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, auth_user_id, email, tenant_id, role, status, department, person_id, "
                    "created_at "
                    "FROM user_memberships WHERE tenant_id = :t ORDER BY created_at"
                ),
                {"t": str(tenant_id)},
            )
        ).mappings().all()
    out = []
    for m in rows:
        d = dict(m)
        d["id"] = str(d["id"])
        d["auth_user_id"] = str(d["auth_user_id"]) if d["auth_user_id"] else None
        d["tenant_id"] = str(d["tenant_id"])
        d["person_id"] = str(d["person_id"]) if d["person_id"] else None
        d["created_at"] = d["created_at"].isoformat()
        d["linked"] = d["auth_user_id"] is not None
        out.append(d)
    return out


async def invite(
    *,
    email: str,
    tenant_id: uuid.UUID,
    role: str,
    department: str | None = None,
    person_id: uuid.UUID | None = None,
) -> dict:
    """Create (or re-activate/update) an e-mail invite; idempotent per (email, tenant)."""
    maker = get_sessionmaker()
    async with maker() as session:
        async with session.begin():
            row = (
                await session.execute(
                    text(
                        "INSERT INTO user_memberships (email, tenant_id, role, department, person_id) "
                        "VALUES (lower(:email), :t, :role, :department, :person_id) "
                        "ON CONFLICT (lower(email), tenant_id) DO UPDATE "
                        "SET role = EXCLUDED.role, department = EXCLUDED.department, "
                        "person_id = EXCLUDED.person_id, status = 'active', updated_at = now() "
                        "RETURNING id, email, tenant_id, role, status, department, person_id"
                    ),
                    {
                        "email": email,
                        "t": str(tenant_id),
                        "role": role,
                        "department": department,
                        "person_id": str(person_id) if person_id else None,
                    },
                )
            ).first()
    return {
        "id": str(row.id),
        "email": row.email,
        "tenant_id": str(row.tenant_id),
        "role": row.role,
        "status": row.status,
        "department": row.department,
        "person_id": str(row.person_id) if row.person_id else None,
    }
