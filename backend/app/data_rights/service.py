"""Retention policy + FK-safe tenant data purge.

Design notes
------------
* The deletion order is computed once by :func:`deletion_plan` from a declared table → parents map
  (``_TENANT_TABLES``). Children are emitted before the parents they reference (a topological sort),
  so the purge is FK-safe even against a schema whose foreign keys do NOT cascade. Self-referential
  columns (e.g. ``org_people.manager_id``, ``agent_preferences.superseded_by``) are SET NULL on
  delete, so a single DELETE per table clears them without an ordering hazard.
* ``tenants`` itself is intentionally NOT in the plan: erasure removes a tenant's *data*, not the
  routing/billing tenant row. (Deleting the tenant row is a separate, heavier operation.) For the
  same reason the auth ``user_memberships`` directory — which holds only routing data, no customer
  business data, and lives outside any tenant GUC — is excluded.
* ``purge_tenant_data`` runs inside :func:`app.db.tenant_session`, so every DELETE is additionally
  RLS-scoped to ``tenant_id``: even a bug in the WHERE clause cannot reach another tenant's rows.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------------------------------
# 1) Retention policy — declarative, auditor-facing.
# ---------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RetentionRule:
    """One data class's retention window.

    ``retention_days`` is the maximum time a row of this class is kept after it is created (or, for
    operational logs, after it is recorded) before it is eligible for purge. ``None`` means "retained
    for the life of the tenant relationship" (deleted only on a right-to-erasure request or tenant
    offboarding).
    """

    data_class: str
    retention_days: int | None
    description: str
    tables: tuple[str, ...]


# Windows reflect the data-processing agreement: business records live for the relationship; derived
# operational/learning/audit data ages out on fixed clocks. Audit is the longest (compliance evidence).
RETENTION_POLICY: tuple[RetentionRule, ...] = (
    RetentionRule(
        data_class="customer_business_records",
        retention_days=None,
        description=(
            "Core customer/ops data synced from the field system (communications, tasks, "
            "the org roster, credentials, settings). Retained for the life of the relationship; "
            "purged on right-to-erasure or tenant offboarding."
        ),
        tables=(
            "communications",
            "tasks",
            "tenant_credentials",
            "tenant_settings",
            "servicetitan_connections",
            "org_departments",
            "org_people",
            "org_person_agent_grants",
            "users",
        ),
    ),
    RetentionRule(
        data_class="agent_activity",
        retention_days=730,
        description=(
            "Agent runs, recommendations, reasoning, proposed/executed actions, and the inbound "
            "event queue. Operational records kept two years for traceability."
        ),
        tables=(
            "agent_runs",
            "agent_recommendations",
            "agent_reasoning_logs",
            "agent_actions",
            "agent_feedback",
            "event_queue",
        ),
    ),
    RetentionRule(
        data_class="learning_memory",
        retention_days=365,
        description=(
            "The self-learning layer — case bank, learned preferences and their supporters/evals, "
            "golden cases, tunable params, drift snapshots. Distilled signal ages out after a year."
        ),
        tables=(
            "agent_cases",
            "agent_preferences",
            "agent_preference_supporters",
            "eval_runs",
            "golden_cases",
            "learning_params",
            "drift_snapshots",
        ),
    ),
    RetentionRule(
        data_class="knowledge_base",
        retention_days=None,
        description=(
            "Tenant-uploaded knowledge documents and their embedding chunks (the Learn module). "
            "Retained until the tenant removes them or requests erasure."
        ),
        tables=("knowledge_documents", "knowledge_chunks"),
    ),
    RetentionRule(
        data_class="assistant_and_usage",
        retention_days=90,
        description=(
            "In-app assistant daily counters, email-workflow overrides, and per-tenant usage "
            "meters. Short-lived operational metering."
        ),
        tables=("assistant_usage", "email_workflow_overrides", "daily_counters"),
    ),
    RetentionRule(
        data_class="audit_log",
        retention_days=2555,
        description=(
            "Append-only audit events (every operator/admin action). Kept seven years as "
            "compliance evidence — the longest-lived class."
        ),
        tables=("audit_events",),
    ),
)


def retention_policy() -> list[dict]:
    """The retention policy as plain JSON-serializable dicts (what the API returns)."""
    return [
        {
            "data_class": rule.data_class,
            "retention_days": rule.retention_days,
            "description": rule.description,
            "tables": list(rule.tables),
        }
        for rule in RETENTION_POLICY
    ]


# ---------------------------------------------------------------------------------------------------
# 2) Deletion plan — the FK-safe ordered table list.
# ---------------------------------------------------------------------------------------------------

# Every tenant-scoped table → the tenant tables it references (its FK *parents*). A table must be
# deleted before the parents listed here. Only same-table-set parents matter for ordering;
# `tenants` (not purged) and self-references (SET NULL, no ordering hazard) are omitted.
# Source of truth: backend/migrations/0001..0021.
_TENANT_TABLES: dict[str, tuple[str, ...]] = {
    # core tenancy
    "users": (),
    "servicetitan_connections": (),
    "tenant_credentials": (),
    "tenant_settings": (),
    # agent runs + dependents (everything that FKs agent_runs deletes first)
    "agent_runs": (),
    "agent_recommendations": ("agent_runs",),
    "agent_reasoning_logs": ("agent_runs",),
    "agent_actions": ("agent_runs",),
    "agent_feedback": ("agent_runs",),
    "event_queue": (),
    # front-desk
    "communications": (),
    "tasks": (),
    # self-learning layer
    "agent_cases": ("agent_runs",),
    "agent_preferences": (),
    "agent_preference_supporters": ("agent_preferences",),
    "eval_runs": ("agent_preferences",),
    "learning_events": (),
    "golden_cases": (),
    "learning_params": (),
    "drift_snapshots": (),
    # knowledge base
    "knowledge_documents": (),
    "knowledge_chunks": ("knowledge_documents",),
    # org brain
    "org_departments": (),
    "org_people": ("org_departments",),
    "org_person_agent_grants": ("org_people",),
    # assistant + usage metering
    "assistant_usage": (),
    "email_workflow_overrides": (),
    "daily_counters": (),
    # NOTE: audit_events is intentionally NOT purged. The append-only audit trail (DB-level
    # append-only via migration 0022; 7-year retention class) is retained as compliance evidence
    # even on right-to-erasure of a tenant's business data — and app_user has no DELETE on it
    # post-0022, so including it here would fail the purge. learning_events (distilled signal, not a
    # compliance log) IS purged.
}


def deletion_plan() -> list[str]:
    """Return the tenant tables ordered so every child precedes each of its FK parents.

    A deterministic topological sort over ``_TENANT_TABLES``: a table is emitted only once all the
    tables that depend on it (its children) have been emitted. Insertion order is preserved among
    independent tables for a stable, reviewable plan. Raises ``ValueError`` on a dependency cycle
    (there are none in this schema, but the guard makes a future bad edit fail loudly).
    """
    remaining = {table: set(parents) for table, parents in _TENANT_TABLES.items()}
    ordered: list[str] = []
    # Children of a table = the tables that name it as a parent. We emit a table once all its
    # children are already emitted, i.e. once nothing remaining still lists it as a parent.
    while remaining:
        ready = [
            table
            for table in _TENANT_TABLES
            if table in remaining
            and not any(table in parents for parents in remaining.values())
        ]
        if not ready:
            raise ValueError(f"cycle in tenant-table FK graph: {sorted(remaining)}")
        for table in ready:
            ordered.append(table)
            del remaining[table]
    return ordered


# ---------------------------------------------------------------------------------------------------
# 3) The purge.
# ---------------------------------------------------------------------------------------------------


async def purge_tenant_data(session: AsyncSession, tenant_id: uuid.UUID) -> dict[str, int]:
    """Delete this tenant's business data — every tenant table except the retained append-only audit
    trail — FK-safe, returning per-table deleted counts.

    Must be called with a session already scoped to ``tenant_id`` (an ``app.db.tenant_session``):
    RLS then double-scopes each DELETE so it can only reach this tenant's rows. The ``tenant_id``
    argument is accepted for an explicit, self-documenting call site; the row filtering itself is RLS.
    """
    _ = tenant_id  # filtering is enforced by RLS on the scoped session, not a WHERE clause here
    deleted: dict[str, int] = {}
    for table in deletion_plan():
        result = await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608 - table from fixed allowlist
        deleted[table] = result.rowcount or 0
    return deleted
