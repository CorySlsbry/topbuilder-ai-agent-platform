"""Pure tests for the propose-only system principal (ADR 0010)."""
from __future__ import annotations

import uuid

import pytest

from app.actions.service import (
    ActionForbidden,
    approve_action,
    execute_action,
    undo_action,
)
from app.security import SYSTEM_ROLE, Principal
from app.sync.principal import (
    SYSTEM_USER_ID,
    is_system_principal,
    system_principal,
)

_TENANT = uuid.uuid4()


def test_system_principal_carries_the_system_role_and_stable_sentinel_id():
    principal = system_principal(_TENANT)
    assert principal.role == SYSTEM_ROLE
    assert principal.tenant_id == _TENANT
    assert principal.user_id == SYSTEM_USER_ID
    # Deterministic + distinct from any real account.
    assert system_principal(_TENANT).user_id == SYSTEM_USER_ID


def test_is_system_principal_distinguishes_humans():
    assert is_system_principal(system_principal(_TENANT)) is True
    human = Principal(tenant_id=_TENANT, user_id=uuid.uuid4(), email="person1@example.com", role="admin")
    assert is_system_principal(human) is False


async def test_system_principal_is_refused_approve_execute_undo():
    # The security belt: the propose-only identity is rejected BEFORE any DB touch (the guard is the
    # first statement), so a detected event can never approve, execute, or undo itself.
    principal = system_principal(_TENANT)
    action_id = uuid.uuid4()
    with pytest.raises(ActionForbidden):
        await approve_action(principal, action_id)
    with pytest.raises(ActionForbidden):
        await execute_action(principal, action_id)
    with pytest.raises(ActionForbidden):
        await undo_action(principal, action_id)
