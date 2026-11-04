"""Pure tests for the Pricebook service helpers + the price-update executor (no DB).

Covers: the server-side ``proposed_pricebook_update_params`` gate (refuses an unchanged item + unknown
item, packages the engine-computed old/new price) and the ``update_pricebook_item`` executor + its undo
(restore the prior price), all offline + deterministic.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.actions.executors import ActionError
from app.agents.pricebook import executors as ex
from app.agents.pricebook import service
from app.agents.pricebook.analytics import analyze
from app.agents.pricebook.models import (
    MaterialLine,
    PricebookData,
    PricebookItem,
    VendorPriceUpdate,
)
from app.agents.pricebook.schemas import build_result
from app.config import get_settings

AS_OF = date(2026, 6, 15)


def _result():
    items = [
        PricebookItem(
            code="P-AC", name="AC Install", category="Install",
            sold_hours=8.0, sold_hour_rate_cents=15_000, markup_pct=20.0,
            current_price_cents=386_400,
            material_lines=[
                MaterialLine(sku="R410A", qty=4, unit_cost_cents=5_000),
                MaterialLine(sku="CU-34", qty=20, unit_cost_cents=500),
                MaterialLine(sku="COND", qty=1, unit_cost_cents=192_000),
            ],
        ),
        PricebookItem(
            code="P-TUNE", name="Tune-Up", category="Maintenance",
            sold_hours=1.0, sold_hour_rate_cents=11_000, markup_pct=25.0,
            current_price_cents=11_000, material_lines=[],  # no materials -> never moves
        ),
    ]
    updates = [
        VendorPriceUpdate(sku="CU-34", vendor="Ferguson", new_unit_cost_cents=650,
                          effective_date=date(2026, 7, 1)),
    ]
    data = PricebookData(as_of=AS_OF, items=items, updates=updates, price_change_tolerance_pct=5.0)
    return build_result(analyze(data), narrative="x", analysis_timestamp=datetime.now(timezone.utc))


class TestProposedPricebookUpdateParams:
    def test_changed_item_maps_to_update_kind_with_engine_prices(self) -> None:
        kind, params = service.proposed_pricebook_update_params(_result(), "P-AC")
        assert kind == "update_pricebook_item"
        assert params["code"] == "P-AC"
        # CU-34 went $5.00 -> $6.50 (+$1.50 x 20 = +$30 materials); +20% markup = +$36 price.
        # old price = 386,400; new price = 386,400 + 3,600 = 390,000 cents.
        assert params["old_price_cents"] == 386_400
        assert params["new_price_cents"] == 390_000
        assert params["changed_skus"] == ["CU-34"]
        assert params["run_id"] is None or isinstance(params["run_id"], str)

    def test_refuses_unchanged_item(self) -> None:
        with pytest.raises(ValueError, match="unchanged"):
            service.proposed_pricebook_update_params(_result(), "P-TUNE")

    def test_refuses_unknown_item(self) -> None:
        with pytest.raises(ValueError, match="not in this pricebook run"):
            service.proposed_pricebook_update_params(_result(), "NOPE")


class TestUpdatePricebookExecutor:
    async def test_fixture_confirmation_quotes_old_and_new_price(self) -> None:
        out = await ex.update_pricebook_item(
            {"code": "P-AC", "name": "AC Install", "old_price_cents": 386_400, "new_price_cents": 390_000},
            get_settings(),
        )
        assert out["status"] == "price_updated"
        assert out["external_ref"] == "st-pricebook-P-AC"
        assert out["old_price_usd"] == 3_864.0 and out["new_price_usd"] == 3_900.0

    async def test_requires_code(self) -> None:
        with pytest.raises(ActionError, match="code"):
            await ex.update_pricebook_item({"new_price_cents": 1}, get_settings())

    async def test_requires_new_price(self) -> None:
        with pytest.raises(ActionError, match="new_price_cents"):
            await ex.update_pricebook_item({"code": "P-AC"}, get_settings())

    async def test_undo_restores_prior_price(self) -> None:
        out = await ex.undo_update_pricebook_item(
            {"code": "P-AC", "old_price_cents": 386_400},
            {"external_ref": "st-pricebook-P-AC", "code": "P-AC"},
            get_settings(),
        )
        assert out["status"] == "price_restored"
        assert out["restored_price_usd"] == 3_864.0
        assert out["external_ref"] == "st-pricebook-P-AC"
