"""Pure tests for the data-rights layer (retention policy + FK-safe purge plan + endpoint authz).

No database: the deletion PLAN is pure (topological order over a declared FK map), the retention
policy is declarative data, and the purge endpoint's operator gate is a pure predicate over the
Principal's email + the operator allowlist.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.api import routes_data_rights
from app.config import Settings
from app.data_rights import service
from app.security import Principal

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

# The FK parents of each tenant table, derived INDEPENDENTLY from the migrations as the test oracle
# (a child must be deleted before each table named here). Kept separate from the production
# `_TENANT_TABLES` so the ordering assertion compares against an independent source of truth.
EXPECTED_PARENTS: dict[str, tuple[str, ...]] = {
    "agent_recommendations": ("agent_runs",),
    "agent_reasoning_logs": ("agent_runs",),
    "agent_actions": ("agent_runs",),
    "agent_feedback": ("agent_runs",),
    "agent_cases": ("agent_runs",),
    "agent_preference_supporters": ("agent_preferences",),
    "eval_runs": ("agent_preferences",),
    "knowledge_chunks": ("knowledge_documents",),
    "org_people": ("org_departments",),
    "org_person_agent_grants": ("org_people",),
}


def _principal(email: str, *, role: str = "admin", aal: str = "aal2") -> Principal:
    return Principal(tenant_id=TENANT_A, user_id=uuid.uuid4(), email=email, role=role, aal=aal)


@pytest.fixture(autouse=True)
def _operator_allowlist(monkeypatch):
    """operator@topbuilderai.com is a platform operator; tenant admins are not."""
    from app import config

    settings = Settings(platform_operator_emails="operator@topbuilderai.com")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_data_rights, "get_settings", lambda: settings)
    return settings


# --- deletion_plan: FK-safe ordering --------------------------------------------------------------
def test_deletion_plan_covers_every_tenant_table_exactly_once():
    plan = service.deletion_plan()
    assert sorted(plan) == sorted(service._TENANT_TABLES)
    assert len(plan) == len(set(plan)), "no table appears twice in the plan"


def test_deletion_plan_never_includes_the_tenant_or_directory_tables():
    # Erasure removes a tenant's DATA, not the tenant routing row or the membership directory.
    plan = set(service.deletion_plan())
    assert "tenants" not in plan
    assert "user_memberships" not in plan


def test_deletion_plan_is_fk_safe_children_before_parents():
    plan = service.deletion_plan()
    position = {table: i for i, table in enumerate(plan)}
    for child, parents in EXPECTED_PARENTS.items():
        for parent in parents:
            assert position[child] < position[parent], (
                f"{child} must be deleted before its FK parent {parent}"
            )


def test_deletion_plan_is_deterministic():
    assert service.deletion_plan() == service.deletion_plan()


def test_deletion_plan_retains_audit_trail_but_purges_learning_events():
    # Right-to-erasure removes business data but RETAINS the append-only audit trail as compliance
    # evidence (7-year retention class + DB-level append-only, migration 0022 revokes app_user DELETE).
    # learning_events is distilled signal, not a compliance log, so it IS purged.
    plan = set(service.deletion_plan())
    assert "audit_events" not in plan, "audit trail is retained as compliance evidence"
    assert "learning_events" in plan


def test_deletion_plan_raises_on_a_cycle(monkeypatch):
    monkeypatch.setattr(service, "_TENANT_TABLES", {"a": ("b",), "b": ("a",)})
    with pytest.raises(ValueError, match="cycle"):
        service.deletion_plan()


# --- retention policy shape ------------------------------------------------------------------------
def test_retention_policy_shape():
    policy = service.retention_policy()
    assert isinstance(policy, list) and policy
    for rule in policy:
        assert set(rule) == {"data_class", "retention_days", "description", "tables"}
        assert isinstance(rule["data_class"], str) and rule["data_class"]
        assert rule["retention_days"] is None or (
            isinstance(rule["retention_days"], int) and rule["retention_days"] > 0
        )
        assert isinstance(rule["tables"], list) and rule["tables"]


def test_every_planned_table_belongs_to_exactly_one_retention_class():
    classified = [t for rule in service.RETENTION_POLICY for t in rule.tables]
    # Each table in a retention class is unique across the whole policy (no double classification)...
    assert len(classified) == len(set(classified)), "a table is in two retention classes"
    # ...and every purgeable table except the learning_events audit trail is classified.
    plan = set(service.deletion_plan())
    unclassified = plan - set(classified)
    assert unclassified == {"learning_events"}, unclassified


def test_retention_policy_is_json_serializable():
    import json

    json.dumps(service.retention_policy())  # raises if any field is not serializable


# --- endpoint authz wiring (operator-only) --------------------------------------------------------
def test_is_platform_operator_case_insensitive_and_closed_by_default():
    assert routes_data_rights._is_platform_operator(_principal("Operator@TopBuilderAI.com"))
    assert not routes_data_rights._is_platform_operator(_principal("person1@example.com"))
    assert not routes_data_rights._is_platform_operator(_principal(""))


def test_require_platform_operator_rejects_a_tenant_admin():
    with pytest.raises(HTTPException) as exc:
        routes_data_rights._require_platform_operator(_principal("person1@example.com"))
    assert exc.value.status_code == 403
    assert "platform-operator" in exc.value.detail


def test_require_platform_operator_allows_an_operator():
    routes_data_rights._require_platform_operator(_principal("operator@topbuilderai.com"))  # no raise


@pytest.mark.asyncio
async def test_purge_endpoint_rejects_a_tenant_admin_before_touching_the_db():
    # A per-tenant admin (with 2FA) is still blocked by the operator gate — even for their own tenant.
    admin = _principal("person1@example.com")
    with pytest.raises(HTTPException) as exc:
        await routes_data_rights.purge_tenant(TENANT_A, principal=admin)
    assert exc.value.status_code == 403
