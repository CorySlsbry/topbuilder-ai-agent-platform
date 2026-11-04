"""Oracle tests for the supplier price-file parser (Alex's 'Excel sheet to teach the agent' path).

These prove the agent can ingest a real, messy distributor price file (CSV or Excel) into deterministic,
cents-accurate VendorPriceUpdate rows — the input the Pricebook re-price engine consumes.
"""
from __future__ import annotations

import io
from datetime import date

import pytest

from app.agents.pricebook import price_file as pf

# A realistic, messy distributor export: $-formatted, a list-vs-net-cost pair (net must win), a blank row,
# a subtotal footer row, and a UOM column the parser must ignore.
MESSY_CSV = (
    "Item #,Description,List Price,Net Cost,Vendor,UOM\n"
    'C-COPPER-058,Copper Line Set 5/8,"$12.00","$6.50",Ferguson,ft\n'
    'R410A-25,R-410A Refrigerant 25lb,"$1,400.00","$1,250.00",Gemaire,lb\n'
    ",,,,,\n"
    'CND-3T,3-Ton Condenser,"$2,100.00","$1,820.00",Watsco,ea\n'
    'TOTAL,,,"$3,076.50",,\n'
)


class TestMoneyToCents:
    @pytest.mark.parametrize("raw,cents", [
        ("$6.50", 650), ("$1,250.00", 125_000), ("1820", 182_000), ("12.5", 1_250),
        ("$2,100", 210_000), ("(12.00)", -1_200), ("", None), ("  ", None), ("n/a", None), (None, None),
    ])
    def test_money(self, raw, cents):
        assert pf.money_to_cents(raw) == cents


class TestParseCsv:
    def test_messy_csv_yields_exact_updates(self):
        ups = pf.parse_csv_text(MESSY_CSV, effective=date(2026, 7, 1))
        # blank + TOTAL rows skipped -> exactly 3 SKUs; NET cost wins over List price.
        assert [(u.sku, u.new_unit_cost_cents, u.vendor) for u in ups] == [
            ("C-COPPER-058", 650, "Ferguson"),
            ("R410A-25", 125_000, "Gemaire"),
            ("CND-3T", 182_000, "Watsco"),
        ]
        # description flows into note; effective date applied
        assert ups[0].note == "Copper Line Set 5/8"
        assert ups[1].effective_date == date(2026, 7, 1)

    def test_duplicate_sku_last_cost_wins(self):
        csv_text = "SKU,Cost\nABC,$10.00\nABC,$11.50\n"
        ups = pf.parse_csv_text(csv_text)
        assert len(ups) == 1 and ups[0].new_unit_cost_cents == 1_150

    def test_default_vendor_when_no_vendor_column(self):
        ups = pf.parse_csv_text("Part Number,Unit Cost\nXYZ,$4.00\n", default_vendor="Johnstone")
        assert ups[0].vendor == "Johnstone" and ups[0].new_unit_cost_cents == 400

    def test_missing_sku_or_cost_column_raises(self):
        with pytest.raises(pf.PriceFileError):
            pf.parse_csv_text("Description,Notes\nfoo,bar\n")

    def test_all_unusable_rows_raises(self):
        with pytest.raises(pf.PriceFileError):
            pf.parse_csv_text("SKU,Cost\n,\nTOTAL,$5.00\n")


class TestParseXlsx:
    @staticmethod
    def _xlsx(headers, rows):
        import openpyxl
        wb = openpyxl.Workbook(); ws = wb.active
        ws.append(headers)
        for r in rows:
            ws.append(r)
        buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

    def test_xlsx_parses_with_different_headers(self):
        data = self._xlsx(["SKU", "Your Cost", "Supplier"],
                          [["LINE-34", 120.0, "RE Michel"], ["FIL-20", 8.75, "Winsupply"]])
        ups = pf.parse_xlsx_bytes(data, effective=date(2026, 7, 1))
        assert [(u.sku, u.new_unit_cost_cents, u.vendor) for u in ups] == [
            ("LINE-34", 12_000, "RE Michel"),
            ("FIL-20", 875, "Winsupply"),
        ]

    def test_dispatch_by_extension(self):
        data = self._xlsx(["Item", "Net Price"], [["Z-1", "$9.99"]])
        ups = pf.parse_price_file("vendor_q3.xlsx", data)
        assert ups[0].sku == "Z-1" and ups[0].new_unit_cost_cents == 999
        ups2 = pf.parse_price_file("vendor.csv", b"SKU,Cost\nZ-2,$3.00\n")
        assert ups2[0].sku == "Z-2" and ups2[0].new_unit_cost_cents == 300


class TestParserFeedsEngine:
    def test_parsed_price_file_reprices_the_matching_item(self):
        """End-to-end: a distributor CSV -> VendorPriceUpdate -> the deterministic re-price engine. Proves
        Alex's Excel/CSV path actually drives the sold-hour model, not just parses."""
        from app.agents.pricebook.analytics import analyze
        from app.agents.pricebook.models import MaterialLine, PricebookData, PricebookItem

        item = PricebookItem(
            code="AC", name="AC install", sold_hours=8, sold_hour_rate_cents=15_000, markup_pct=20.0,
            material_lines=[MaterialLine(sku="COP-58", qty=20, unit_cost_cents=500)],
        )
        # old: labor 8*$150=$1,200 + materials 20*$5=$100 + 20% = $1,320 (132_000c)
        updates = pf.parse_csv_text("SKU,Cost\nCOP-58,$6.50\n", effective=date(2026, 7, 1))
        analysis = analyze(PricebookData(as_of=date(2026, 7, 1), items=[item], updates=updates))
        change = next(c for c in analysis.changes if c.code == "AC")
        # new: materials 20*$6.50=$130 + 20% -> price $1,356 -> delta +$36 = 3_600c
        assert change.price_delta_cents == 3_600


def test_action_kind_is_bound_to_its_owning_agent():
    """Regression lock for the audit fix: the generic /v1/actions propose route checks the KIND's owning
    agent, so a finance/collections runner can't hand-craft a workforce payroll_adjustment."""
    from app.api.routes_actions import KIND_OWNER
    from app.org import permissions

    assert KIND_OWNER["payroll_adjustment"] == "workforce"
    assert KIND_OWNER["update_pricebook_item"] == "pricebook"
    assert KIND_OWNER["send_dunning_sms"] == "collections"
    # a finance-department runner does NOT own the workforce agent -> can't propose its kinds
    assert permissions.can_use_agent("analyst", "finance", "workforce") is False
    # the owning department (field) does
    assert permissions.can_use_agent("analyst", "field", "workforce") is True
