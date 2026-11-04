"""The propose-only system identity for the event-detection loop (ADR 0010).

A poll tick or webhook has no logged-in user, so the drain worker runs under this synthetic principal.
It carries `role='system'` (distinct from the demo admin the other crons reuse) and a fixed, derived
sentinel `user_id` so its proposals are attributable in the audit trail. The action gate refuses
approve/execute under this role, so the loop can only ever leave a proposal for a human.
"""
from __future__ import annotations

import uuid

from app.security import SYSTEM_ROLE, Principal

# Deterministic, distinct sentinel user id (NOT a real account, NOT the demo admin_user_id).
SYSTEM_USER_ID = uuid.uuid5(uuid.NAMESPACE_URL, "topbuilderai:system-principal")
SYSTEM_EMAIL = "person1@example.com"


def system_principal(tenant_id: uuid.UUID) -> Principal:
    """The propose-only principal the drain worker uses for `tenant_id`."""
    return Principal(
        tenant_id=tenant_id,
        user_id=SYSTEM_USER_ID,
        email=SYSTEM_EMAIL,
        role=SYSTEM_ROLE,
    )


def is_system_principal(principal: Principal) -> bool:
    return principal.role == SYSTEM_ROLE or principal.user_id == SYSTEM_USER_ID
