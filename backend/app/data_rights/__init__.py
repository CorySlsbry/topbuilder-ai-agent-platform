"""Customer-data RETENTION + DELETION (data-rights) layer.

Two responsibilities, both required by enterprise data-processing agreements (the Procore
"deletion controls" + "data retention policy" line items):

1. A documented RETENTION POLICY — a per-data-class window after which a class of customer data is
   eligible for purge. The policy is declarative data (``RETENTION_POLICY``) so it can be served to
   auditors and reasoned about without a database.
2. A right-to-erasure PURGE — :func:`app.data_rights.service.purge_tenant_data` deletes ALL of one
   tenant's rows across every tenant-scoped table, in FK-safe order, inside a tenant-scoped session
   so RLS double-scopes the deletes to that tenant.

The ordered table list is computed by the pure :func:`app.data_rights.service.deletion_plan`, so the
FK-safe ordering is unit-testable without a database.
"""
from __future__ import annotations

from app.data_rights.service import (
    RETENTION_POLICY,
    RetentionRule,
    deletion_plan,
    purge_tenant_data,
    retention_policy,
)

__all__ = [
    "RETENTION_POLICY",
    "RetentionRule",
    "deletion_plan",
    "purge_tenant_data",
    "retention_policy",
]
