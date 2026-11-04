"""Org persistence (departments + people). Tenant-scoped session → RLS.

Seed-on-read (the comms/tasks pattern): the first overview read for a demo tenant inserts the
roster from app/org/seed.py inside the tenant session — idempotent via deterministic uuid5 ids +
ON CONFLICT DO NOTHING. Tenants with no seeded roster get empty arrays, never an error.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session
from app.org.permissions import AGENT_CARDS
from app.org.seed import SEED_TENANTS, dept_id, person_id


async def ensure_seeded(tenant_id: uuid.UUID) -> None:
    """Seed the demo roster on first read (no-op for non-demo tenants / already-seeded tenants)."""
    spec = SEED_TENANTS.get(str(tenant_id))
    if spec is None:
        return
    async with tenant_session(tenant_id) as session:
        count = (await session.execute(text("SELECT count(*) FROM org_people"))).scalar_one()
        if count > 0:
            # Backfill external_ref on rows seeded before the roster-sync columns existed, so a
            # reconcile UPDATEs them in place instead of inserting duplicate people.
            for p in spec["people"]:
                await session.execute(
                    text(
                        "UPDATE org_people SET external_ref = :ext "
                        "WHERE id = :id AND external_ref IS NULL"
                    ),
                    {"ext": p["slug"], "id": str(person_id(p["slug"]))},
                )
            return
        insert_dept = text(
            "INSERT INTO org_departments (id, key, name, color, sort) "
            "VALUES (:id, :key, :name, :color, :sort) ON CONFLICT DO NOTHING"
        )
        for d in spec["departments"]:
            await session.execute(
                insert_dept,
                {"id": str(dept_id(d["key"])), "key": d["key"], "name": d["name"],
                 "color": d["color"], "sort": d["sort"]},
            )
        insert_person = text(
            "INSERT INTO org_people "
            "  (id, department_id, full_name, title, role_tier, manager_id, ai_context, sort, "
            "   external_ref, status) "
            "VALUES (:id, :department_id, :full_name, :title, :role_tier, :manager_id, "
            "        :ai_context, :sort, :external_ref, 'active') "
            "ON CONFLICT DO NOTHING"
        )
        # Roster order lists every manager before their reports, so the self-FK always resolves.
        for p in spec["people"]:
            await session.execute(
                insert_person,
                {
                    "id": str(person_id(p["slug"])),
                    "department_id": str(dept_id(p["department"])),
                    "full_name": p["full_name"],
                    "title": p["title"],
                    "role_tier": p["role_tier"],
                    "manager_id": str(person_id(p["manager_slug"])) if p["manager_slug"] else None,
                    "ai_context": p["ai_context"],
                    "sort": p["sort"],
                    "external_ref": p["slug"],
                },
            )


async def get_overview(tenant_id: uuid.UUID) -> dict:
    """Company + departments (+head_count) + people + agent cards (caller_access is the route's)."""
    async with tenant_session(tenant_id) as session:
        name_row = (
            await session.execute(text("SELECT name FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
        ).first()
        provider_row = (
            await session.execute(
                text("SELECT fsm_provider FROM tenant_settings WHERE tenant_id = :t"),
                {"t": str(tenant_id)},
            )
        ).first()
        dept_rows = (
            await session.execute(
                text(
                    """
                    SELECT d.id, d.key, d.name, d.color, d.sort, count(p.id) AS head_count
                    FROM org_departments d
                    LEFT JOIN org_people p ON p.department_id = d.id AND p.status = 'active'
                    GROUP BY d.id, d.key, d.name, d.color, d.sort
                    ORDER BY d.sort
                    """
                )
            )
        ).mappings().all()
        people_rows = (
            await session.execute(
                text(
                    """
                    SELECT p.id, p.full_name, p.title, d.key AS department_key, p.role_tier,
                           p.manager_id
                    FROM org_people p
                    JOIN org_departments d ON d.id = p.department_id
                    WHERE p.status = 'active'
                    ORDER BY d.sort, p.sort
                    """
                )
            )
        ).mappings().all()
    return {
        "company": {
            "name": name_row[0] if name_row else str(tenant_id),
            "employee_count": len(people_rows),
            "provider": provider_row[0] if provider_row else "servicetitan",
        },
        "departments": [
            {
                "id": str(d["id"]),
                "key": d["key"],
                "name": d["name"],
                "color": d["color"],
                "sort": d["sort"],
                "head_count": d["head_count"],
            }
            for d in dept_rows
        ],
        "people": [
            {
                "id": str(p["id"]),
                "full_name": p["full_name"],
                "title": p["title"],
                "department_key": p["department_key"],
                "role_tier": p["role_tier"],
                "manager_id": str(p["manager_id"]) if p["manager_id"] else None,
            }
            for p in people_rows
        ],
        "agents": AGENT_CARDS,
    }


async def get_person(tenant_id: uuid.UUID, pid: uuid.UUID) -> dict | None:
    """Person profile + manager + direct reports (ai_access is computed by the route)."""
    async with tenant_session(tenant_id) as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT p.id, p.full_name, p.title, p.role_tier, p.email, p.ai_context,
                           d.key AS department_key, d.name AS department_name, d.color,
                           m.id AS manager_pid, m.full_name AS manager_name, m.title AS manager_title
                    FROM org_people p
                    JOIN org_departments d ON d.id = p.department_id
                    LEFT JOIN org_people m ON m.id = p.manager_id
                    WHERE p.id = :pid
                    """
                ),
                {"pid": str(pid)},
            )
        ).mappings().first()
        if row is None:
            return None
        report_rows = (
            await session.execute(
                text(
                    "SELECT id, full_name, title FROM org_people "
                    "WHERE manager_id = :pid ORDER BY sort"
                ),
                {"pid": str(pid)},
            )
        ).mappings().all()
    return {
        "person": {
            "id": str(row["id"]),
            "full_name": row["full_name"],
            "title": row["title"],
            "department_key": row["department_key"],
            "department_name": row["department_name"],
            "color": row["color"],
            "role_tier": row["role_tier"],
            "email": row["email"],
            "ai_context": row["ai_context"],
        },
        "manager": (
            {
                "id": str(row["manager_pid"]),
                "full_name": row["manager_name"],
                "title": row["manager_title"],
            }
            if row["manager_pid"]
            else None
        ),
        "direct_reports": [
            {"id": str(r["id"]), "full_name": r["full_name"], "title": r["title"]}
            for r in report_rows
        ],
    }


async def get_person_min(tenant_id: uuid.UUID, pid: uuid.UUID) -> dict | None:
    """Just what authorization needs: the person's department key, manager, role tier."""
    async with tenant_session(tenant_id) as session:
        row = (
            await session.execute(
                text(
                    "SELECT p.role_tier, p.manager_id, d.key AS department_key "
                    "FROM org_people p JOIN org_departments d ON d.id = p.department_id "
                    "WHERE p.id = :pid"
                ),
                {"pid": str(pid)},
            )
        ).mappings().first()
    if row is None:
        return None
    return {
        "role_tier": row["role_tier"],
        "manager_id": str(row["manager_id"]) if row["manager_id"] else None,
        "department_key": row["department_key"],
    }


async def get_caller_person(tenant_id: uuid.UUID, person_id: str | None) -> dict | None:
    """The caller's own org-person row (role tier + department) — drives their manage authority.
    None when the login isn't linked to a person (e.g. an operator with no org seat)."""
    if not person_id:
        return None
    try:
        return await get_person_min(tenant_id, uuid.UUID(person_id))
    except (ValueError, TypeError):
        return None


async def get_person_overrides(tenant_id: uuid.UUID, pid: uuid.UUID) -> dict[str, str]:
    """agent_key -> 'grant'|'revoke' overrides set on this person (empty = pure department default)."""
    async with tenant_session(tenant_id) as session:
        rows = (
            await session.execute(
                text("SELECT agent_key, mode FROM org_person_agent_grants WHERE person_id = :pid"),
                {"pid": str(pid)},
            )
        ).mappings().all()
    return {r["agent_key"]: r["mode"] for r in rows}


async def set_person_override(
    tenant_id: uuid.UUID, pid: uuid.UUID, agent_key: str, mode: str, set_by: str | None
) -> None:
    """mode 'grant'|'revoke' upserts the override; 'default' clears it (back to the dept default)."""
    async with tenant_session(tenant_id) as session:
        if mode == "default":
            await session.execute(
                text(
                    "DELETE FROM org_person_agent_grants WHERE person_id = :pid AND agent_key = :a"
                ),
                {"pid": str(pid), "a": agent_key},
            )
        else:
            await session.execute(
                text(
                    "INSERT INTO org_person_agent_grants (person_id, agent_key, mode, set_by) "
                    "VALUES (:pid, :a, :m, :by) "
                    "ON CONFLICT (tenant_id, person_id, agent_key) WHERE person_id IS NOT NULL "
                    "DO UPDATE SET mode = :m, set_by = :by, set_at = now()"
                ),
                {"pid": str(pid), "a": agent_key, "m": mode, "by": set_by},
            )


async def reconcile_roster(tenant_id: uuid.UUID, roster: list[dict]) -> dict:
    """Idempotently sync org_people to the connected provider's employee roster (matched on
    external_ref): upsert everyone present as active, mark everyone absent as departed. This is the
    dynamic hire/fire population — re-runnable; a second run with the same roster is a no-op.

    roster items: {external_ref, full_name, title, department_key, role_tier?}.
    """
    async with tenant_session(tenant_id) as session:
        dept_rows = (
            await session.execute(text("SELECT id, key FROM org_departments"))
        ).mappings().all()
        dept_by_key = {d["key"]: str(d["id"]) for d in dept_rows}
        # Safety: an empty roster almost always means a provider outage, NOT that everyone quit.
        # Refuse to mark the whole org departed on an empty pull.
        if not any(e.get("external_ref") for e in roster):
            return {"synced": 0, "departed": 0, "active": 0, "skipped": "empty roster — no changes"}
        present: set[str] = set()
        upserted = 0
        for emp in roster:
            ext = emp.get("external_ref")
            dept = dept_by_key.get(emp.get("department_key", ""))
            if not ext or dept is None:
                continue
            present.add(str(ext))
            await session.execute(
                text(
                    "INSERT INTO org_people "
                    "  (department_id, full_name, title, role_tier, external_ref, status, synced_at) "
                    "VALUES (:d, :n, :t, :r, :ext, 'active', now()) "
                    "ON CONFLICT (tenant_id, external_ref) WHERE external_ref IS NOT NULL "
                    "DO UPDATE SET full_name = :n, title = :t, role_tier = :r, "
                    "  department_id = :d, status = 'active', synced_at = now()"
                ),
                {
                    "d": dept,
                    "n": emp["full_name"],
                    "t": emp.get("title", ""),
                    "r": emp.get("role_tier", "ic"),
                    "ext": str(ext),
                },
            )
            upserted += 1
        existing = (
            await session.execute(
                text(
                    "SELECT id, external_ref FROM org_people "
                    "WHERE external_ref IS NOT NULL AND status = 'active'"
                )
            )
        ).mappings().all()
        departed = 0
        for row in existing:
            if row["external_ref"] not in present:
                await session.execute(
                    text("UPDATE org_people SET status = 'departed', synced_at = now() WHERE id = :id"),
                    {"id": str(row["id"])},
                )
                departed += 1
    return {"synced": upserted, "departed": departed, "active": len(present)}


async def apply_employee_change(
    tenant_id: uuid.UUID,
    *,
    external_ref: str | None,
    action: str,
    full_name: str = "",
    title: str = "",
    department_key: str | None = None,
) -> dict:
    """Real-time single-person roster update from a hire/fire webhook. 'hired' upserts the person as
    active (placing an unmapped department into Field Operations); 'departed' marks them departed so
    they drop off the sphere. Idempotent on external_ref."""
    if not external_ref:
        return {"applied": False, "reason": "no external_ref"}
    async with tenant_session(tenant_id) as session:
        if action == "departed":
            res = await session.execute(
                text(
                    "UPDATE org_people SET status = 'departed', synced_at = now() "
                    "WHERE external_ref = :ext AND status = 'active'"
                ),
                {"ext": external_ref},
            )
            return {"applied": True, "action": "departed", "rows": res.rowcount}
        dept = (
            await session.execute(
                text("SELECT id FROM org_departments WHERE key = :k"),
                {"k": department_key or "field"},
            )
        ).first()
        if dept is None:
            dept = (
                await session.execute(text("SELECT id FROM org_departments WHERE key = 'field'"))
            ).first()
        if dept is None:
            return {"applied": False, "reason": "no department to place the hire"}
        await session.execute(
            text(
                "INSERT INTO org_people "
                "  (department_id, full_name, title, role_tier, external_ref, status, synced_at) "
                "VALUES (:d, :n, :t, 'ic', :ext, 'active', now()) "
                "ON CONFLICT (tenant_id, external_ref) WHERE external_ref IS NOT NULL "
                "DO UPDATE SET full_name = :n, title = :t, status = 'active', synced_at = now()"
            ),
            {"d": str(dept[0]), "n": full_name or "New hire", "t": title or "", "ext": external_ref},
        )
        return {"applied": True, "action": "hired"}
