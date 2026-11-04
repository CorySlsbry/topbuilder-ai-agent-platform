"""Pure tests for the QuickBooks CDC poll client (ADR 0010).

No network: the credential gate, the entity maps, and the response parser are the unit-testable
surface; the live shape is verified against a real company at go-live (ADR 0005).
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.integrations.quickbooks import cdc_client
from app.sync import normalize

NO_CREDS = Settings(accounting_mode="quickbooks")


class TestFailClosed:
    async def test_fetch_cdc_refuses_without_connected_company(self) -> None:
        client = cdc_client.QuickBooksCdcClient(NO_CREDS)
        with pytest.raises(RuntimeError, match="QuickBooks mode requires"):
            await client.fetch_cdc()

    async def test_fetch_cdc_refuses_even_with_explicit_entities(self) -> None:
        client = cdc_client.QuickBooksCdcClient(NO_CREDS)
        with pytest.raises(RuntimeError, match="QUICKBOOKS_REALM_ID"):
            await client.fetch_cdc(["Attachable"], changed_since="2026-06-27T00:00:00Z")


class TestEntityMaps:
    def test_default_entities_include_attachable(self) -> None:
        # Attachable (receipt images) fires NO QBO webhook — CDC is its only detection path.
        assert "Attachable" in cdc_client.DEFAULT_CDC_ENTITIES

    def test_every_default_entity_is_normalizable(self) -> None:
        for name in cdc_client.DEFAULT_CDC_ENTITIES:
            assert normalize.canonical_qbo_entity(name) is not None, name

    def test_reverse_map_resolves_canonical_entities(self) -> None:
        assert cdc_client.qbo_entity_for("bill") == "Bill"
        assert cdc_client.qbo_entity_for("attachment") == "Attachable"
        assert cdc_client.qbo_entity_for("invoice") == "Invoice"
        # Two QBO names map to canonical `payment`; the CDC poll prefers Payment over BillPayment.
        assert cdc_client.qbo_entity_for("payment") == "Payment"
        assert cdc_client.qbo_entity_for("not-an-entity") is None


class TestParseCdcResponse:
    def test_parses_rows_across_entities(self) -> None:
        body = {
            "CDCResponse": [
                {
                    "QueryResponse": [
                        {"Bill": [{"Id": "1", "TotalAmt": 100.0}, {"Id": "2"}],
                         "startPosition": 1, "maxResults": 2},
                        {"Attachable": [{"Id": "9", "FileName": "receipt.jpg"}]},
                    ]
                }
            ]
        }
        rows = cdc_client.parse_cdc_response(body)
        assert rows == [
            ("Bill", {"Id": "1", "TotalAmt": 100.0}),
            ("Bill", {"Id": "2"}),
            ("Attachable", {"Id": "9", "FileName": "receipt.jpg"}),
        ]

    def test_empty_and_malformed_envelopes_yield_nothing(self) -> None:
        assert cdc_client.parse_cdc_response({}) == []
        assert cdc_client.parse_cdc_response({"CDCResponse": [{"QueryResponse": [{}]}]}) == []
        assert cdc_client.parse_cdc_response({"CDCResponse": ["garbage", {"QueryResponse": ["x"]}]}) == []
