"""The cross-tenant membership-injection guard (routes_admin) — pure tests.

A per-tenant 'admin' must NOT be able to invite/list into another tenant; only a platform operator
(email on the allowlist) may. This is the only control over the permissive-write directory table,
so it is regression-locked here.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.api import routes_admin
from app.config import Settings
from app.security import Principal

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")


def _principal(email: str, tenant: uuid.UUID) -> Principal:
    return Principal(tenant_id=tenant, user_id=uuid.uuid4(), email=email, role="admin", aal="aal2")


@pytest.fixture(autouse=True)
def _operator_allowlist(monkeypatch):
    """operator@topbuilderai.com is a platform operator; tenant admins are not."""
    from app import config

    settings = Settings(platform_operator_emails="operator@topbuilderai.com")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(routes_admin, "get_settings", lambda: settings)
    return settings


def test_tenant_admin_cannot_target_another_tenant():
    admin_a = _principal("person1@example.com", TENANT_A)
    body = routes_admin.InviteIn(email="person2@example.com", role="admin", tenant_id=TENANT_B)
    with pytest.raises(HTTPException) as exc:
        routes_admin._resolve_tenant(body, admin_a)
    assert exc.value.status_code == 403
    assert "platform-operator" in exc.value.detail


def test_tenant_admin_targeting_own_tenant_is_allowed():
    admin_a = _principal("person1@example.com", TENANT_A)
    body = routes_admin.InviteIn(email="person3@example.com", role="analyst", tenant_id=TENANT_A)
    assert routes_admin._resolve_tenant(body, admin_a) == TENANT_A


def test_default_target_is_own_tenant():
    admin_a = _principal("person1@example.com", TENANT_A)
    body = routes_admin.InviteIn(email="person3@example.com", role="analyst")  # no tenant given
    assert routes_admin._resolve_tenant(body, admin_a) == TENANT_A


def test_platform_operator_may_target_any_tenant():
    op = _principal("operator@topbuilderai.com", TENANT_A)
    body = routes_admin.InviteIn(email="person4@example.com", role="admin", tenant_id=TENANT_B)
    assert routes_admin._resolve_tenant(body, op) == TENANT_B


def test_is_platform_operator_is_case_insensitive_and_closed_by_default():
    assert routes_admin._is_platform_operator(_principal("Operator@TopBuilderAI.com", TENANT_A))
    assert not routes_admin._is_platform_operator(_principal("person1@example.com", TENANT_A))
    assert not routes_admin._is_platform_operator(_principal("", TENANT_A))


def test_authorize_tenant_target_helper_matches():
    op = _principal("operator@topbuilderai.com", TENANT_A)
    tenant_admin = _principal("person1@example.com", TENANT_A)
    routes_admin._authorize_tenant_target(TENANT_B, op)  # operator: no raise
    routes_admin._authorize_tenant_target(TENANT_A, tenant_admin)  # own tenant: no raise
    with pytest.raises(HTTPException):
        routes_admin._authorize_tenant_target(TENANT_B, tenant_admin)
