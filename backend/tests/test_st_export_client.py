"""Pure tests for the ServiceTitan `/export` change-feed client (ADR 0010).

No network: the credential gate and the entity->module map are the unit-testable surface; the HTTP
page fetch is exercised live at go-live (ADR 0005 — field shapes verified against a real tenant).
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.integrations.servicetitan import export_client as st_export
from app.sync import normalize, router

NO_CREDS = Settings(servicetitan_mode="live")
FAKE_CREDS = Settings(
    servicetitan_mode="live",
    servicetitan_client_id="cid",
    servicetitan_client_secret="secret",
    servicetitan_app_key="appkey",
    servicetitan_tenant_id="12345",
)


class TestFailClosed:
    async def test_fetch_refuses_without_credentials(self) -> None:
        client = st_export.ServiceTitanExportClient(NO_CREDS)
        with pytest.raises(RuntimeError, match="ServiceTitan live mode requires"):
            await client.fetch_export_page("accounting", "bill", None)

    async def test_unmapped_entity_refuses_before_any_network(self) -> None:
        # Creds present, but `attachment` has no export feed -> refuse, never guess an endpoint.
        client = st_export.ServiceTitanExportClient(FAKE_CREDS)
        with pytest.raises(RuntimeError, match="no ServiceTitan export feed"):
            await client.fetch_export_page("documents", "attachment", None)

    async def test_wrong_module_for_entity_refuses(self) -> None:
        client = st_export.ServiceTitanExportClient(FAKE_CREDS)
        with pytest.raises(RuntimeError, match="exports under module 'accounting'"):
            await client.fetch_export_page("jpm", "bill", None)


class TestEntityModuleMap:
    def test_expected_module_pairs(self) -> None:
        assert st_export.EXPORT_ENTITIES["bill"] == ("accounting", "inventory-bills")
        assert st_export.EXPORT_ENTITIES["invoice"] == ("accounting", "invoices")
        assert st_export.EXPORT_ENTITIES["job"] == ("jpm", "jobs")
        assert st_export.EXPORT_ENTITIES["appointment"] == ("jpm", "appointments")
        assert st_export.EXPORT_ENTITIES["purchase_order"] == ("inventory", "purchase-orders")
        assert st_export.EXPORT_ENTITIES["gross_pay_item"] == ("payroll", "gross-pay-items")
        assert st_export.EXPORT_ENTITIES["booking"] == ("crm", "bookings")

    def test_export_module_for_resolves_and_none_for_unmapped(self) -> None:
        assert st_export.export_module_for("bill") == "accounting"
        assert st_export.export_module_for("timesheet") == "payroll"
        assert st_export.export_module_for("attachment") is None  # no export feed -> fallback path
        assert st_export.export_module_for("not-an-entity") is None

    def test_every_mapped_entity_is_handled_by_the_sync_layer(self) -> None:
        # The map must never reach past what normalize/router can process: every polled entity is
        # normalizable (its module is known) AND routable (nothing is pulled just to no_route).
        for entity, (module, segment) in st_export.EXPORT_ENTITIES.items():
            assert module == normalize.module_for(entity), entity
            assert segment
        assert set(st_export.EXPORT_ENTITIES) <= router.known_entities()
