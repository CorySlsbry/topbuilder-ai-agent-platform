"""Tenant-scoped issue store for the L10 Issues list.

The seeded issues come from the fixture (``eos_data.get_seed_issues``); create/resolve are applied as
PURE transforms (``eos.apply_issue_create`` / ``apply_issue_resolve``) over a per-tenant overlay kept
here. This is a demo-grade in-process store (no migration) — like the OrgSphere demo state — so the
communication hub is fully interactive in the sales demo without standing up a new table. At go-live
this module's two write functions become the seam where issues persist to a DB table (RLS-scoped),
leaving the route + engine untouched.

Thread-safety: guarded by a lock so concurrent requests can't corrupt the overlay list.
"""
from __future__ import annotations

import threading
import uuid

from app.org.eos import Issue, apply_issue_create, apply_issue_resolve, make_issue
from app.org.eos_data import get_seed_issues

_lock = threading.Lock()
# tenant_id -> the current issue list (seed + applied creates/resolves). Lazily seeded on first use.
_by_tenant: dict[str, list[Issue]] = {}


def _ensure(tenant_id: uuid.UUID) -> list[Issue]:
    key = str(tenant_id)
    if key not in _by_tenant:
        _by_tenant[key] = list(get_seed_issues())
    return _by_tenant[key]


def list_issues(tenant_id: uuid.UUID) -> list[Issue]:
    """The tenant's current issues (seed + overlay). Returns a copy — callers can't mutate the store."""
    with _lock:
        return list(_ensure(tenant_id))


def create_issue(
    tenant_id: uuid.UUID,
    *,
    title: str,
    owner: str,
    department: str,
    priority: object,
    created: str,
) -> Issue:
    """Validate + add a new OPEN issue (newest first). Returns the created issue. Raises ValueError
    on an empty title (the route maps that to 422)."""
    issue = make_issue(
        issue_id=f"iss-{uuid.uuid4().hex[:12]}",
        title=title,
        owner=owner,
        department=department,
        priority=priority,
        created=created,
    )
    with _lock:
        _by_tenant[str(tenant_id)] = apply_issue_create(_ensure(tenant_id), issue)
    return issue


def resolve_issue(tenant_id: uuid.UUID, issue_id: str, *, resolved_on: str) -> Issue | None:
    """Close the matching open issue (idempotent). Returns the resolved issue, or None if the id is
    unknown."""
    with _lock:
        updated = apply_issue_resolve(_ensure(tenant_id), issue_id, resolved_on=resolved_on)
        _by_tenant[str(tenant_id)] = updated
        return next((i for i in updated if i.id == issue_id), None)


def reset(tenant_id: uuid.UUID | None = None) -> None:
    """Drop the overlay (re-seed on next read). For tests; or all tenants when called with None."""
    with _lock:
        if tenant_id is None:
            _by_tenant.clear()
        else:
            _by_tenant.pop(str(tenant_id), None)
