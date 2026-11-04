"""End-to-end (DB) test for the event-detection drain (ADR 0010).

Proves: a detected vendor bill -> normalized -> enqueued (idempotent) -> drained -> a job-costed
`create_ap_draft` left PROPOSED for a human (never auto-executed, even though the loop ran the agent),
and that the propose-only system principal cannot approve/execute. A bill with no job match degrades
to advisory (no proposal).
"""
from __future__ import annotations

import pytest

from app.actions import service as actions_service
from app.actions.service import ActionForbidden
from app.demo import DEMO_TENANTS
from app.security import Principal
from app.sync import normalize, service
from app.sync.principal import system_principal

pytestmark = pytest.mark.integration


def _human(slug: str = "apex") -> Principal:
    dt = DEMO_TENANTS[slug]
    return Principal(tenant_id=dt.tenant_id, user_id=dt.admin_user_id, email=dt.admin_email, role="admin")


async def test_detected_bill_with_job_proposes_ap_draft_for_a_human() -> None:
    from app import db

    tenant = DEMO_TENANTS["apex"].tenant_id
    human = _human("apex")
    try:
        bill = {"id": 90125, "modifiedOn": "2026-06-27T10:00:00Z", "jobNumber": "J-9001",
                "total": 412.50, "vendor": "Ferguson", "docNumber": "INV-9001"}
        event = normalize.normalize_st_export_row("bill", bill, verb="created")

        assert await service.enqueue_events(tenant, [event]) == 1
        # Re-detecting the SAME change (poll overlap / includeRecentChanges) collapses — no duplicate.
        assert await service.enqueue_events(tenant, [event]) == 0

        result = await service.drain_tenant(tenant)
        assert result["claimed"] == 1
        assert result["proposed"] == 1
        assert result["failed"] == 0

        actions = await actions_service.list_actions(human, agent="documents")
        ap = [a for a in actions if a.kind == "create_ap_draft" and a.params.get("bill_id") == "90125"]
        assert len(ap) == 1
        action = ap[0]
        assert action.status == "proposed"  # approve-first: NOT auto-executed
        assert action.params["job_ref"] == "J-9001"
        assert action.params["amount_cents"] == 41250

        # The propose-only system principal cannot advance it; a human must.
        with pytest.raises(ActionForbidden):
            await actions_service.approve_action(system_principal(tenant), action.id)
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()


async def test_detected_bill_without_job_match_is_advisory_not_proposed() -> None:
    from app import db

    tenant = DEMO_TENANTS["summit"].tenant_id
    human = _human("summit")
    try:
        bill = {"id": 70007, "modifiedOn": "2026-06-27T11:00:00Z", "total": 88.0, "vendor": "Grainger"}
        event = normalize.normalize_st_export_row("bill", bill, verb="created")
        await service.enqueue_events(tenant, [event])

        result = await service.drain_tenant(tenant)
        assert result["claimed"] == 1
        assert result["proposed"] == 0
        assert result["advisory"] == 1

        actions = await actions_service.list_actions(human, agent="documents")
        assert not [a for a in actions if a.params.get("bill_id") == "70007"]
    finally:
        await db.get_engine().dispose()
        db.get_engine.cache_clear()
        db.get_sessionmaker.cache_clear()
