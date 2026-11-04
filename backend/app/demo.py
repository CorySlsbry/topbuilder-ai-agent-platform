"""Demo tenants for local dev / the dashboard login.

These IDs MUST stay in sync with migrations/0003_seed_dev.sql. The dev-token endpoint mints a
tenant-scoped JWT for one of these without a DB lookup, so the dashboard works immediately.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoTenant:
    slug: str
    name: str
    tenant_id: uuid.UUID
    admin_user_id: uuid.UUID
    admin_email: str


DEMO_TENANTS: dict[str, DemoTenant] = {
    "apex": DemoTenant(
        slug="apex",
        name="Apex Mechanical",
        tenant_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        admin_user_id=uuid.UUID("1a000000-0000-0000-0000-000000000001"),
        admin_email="person1@example.com",
    ),
    "summit": DemoTenant(
        slug="summit",
        name="Summit HVAC",
        tenant_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        admin_user_id=uuid.UUID("2b000000-0000-0000-0000-000000000001"),
        admin_email="person2@example.com",
    ),
    "canyonridge": DemoTenant(
        slug="canyonridge",
        name="Canyon Ridge Mechanical",
        tenant_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
        admin_user_id=uuid.UUID("3c000000-0000-0000-0000-000000000001"),
        admin_email="person3@example.com",
    ),
}

DEFAULT_DEMO_SLUG = "apex"
