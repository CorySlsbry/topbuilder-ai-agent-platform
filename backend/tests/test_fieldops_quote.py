"""Unit + property tests for the field-ops custom-quote engine.

Hand-computed oracle: AC Tune-Up $129 + Capacitor $189 + Air Filter $24 x2 + Permit $75 (not taxable),
tax 8.6% on the taxable $366.00 → subtotal $441.00, tax $31.48, total $472.48.
"""
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.fieldops.models import PricebookService, QuoteLineItem
from app.fieldops.quote import QuoteError, price_quote

PRICEBOOK = [
    PricebookService("SVC-AC-TUNE", "AC Tune-Up", "hvac", 12900, taxable=True),
    PricebookService("SVC-CAP", "Capacitor Replacement", "hvac", 18900, taxable=True),
    PricebookService("SVC-DIAG", "Diagnostic Fee", "general", 8900, taxable=True),
    PricebookService("SVC-FILTER", "Air Filter (each)", "hvac", 2400, taxable=True),
    PricebookService("SVC-PERMIT", "Permit Filing", "compliance", 7500, taxable=False),
]


class TestQuoteEngine:
    def test_oracle(self) -> None:
        q = price_quote(
            PRICEBOOK,
            [QuoteLineItem("SVC-AC-TUNE"), QuoteLineItem("SVC-CAP"),
             QuoteLineItem("SVC-FILTER", 2), QuoteLineItem("SVC-PERMIT")],
            tax_rate=0.086,
        )
        assert q.subtotal_cents == 44100
        assert q.taxable_subtotal_cents == 36600     # permit excluded
        assert q.tax_cents == 3148                   # round(36600 * 0.086)
        assert q.total_cents == 47248                # $472.48

    def test_remove_service_changes_total(self) -> None:
        # Removing the capacitor drops the taxable base and the total.
        full = price_quote(PRICEBOOK, [QuoteLineItem("SVC-AC-TUNE"), QuoteLineItem("SVC-CAP")], tax_rate=0.086)
        reduced = price_quote(PRICEBOOK, [QuoteLineItem("SVC-AC-TUNE")], tax_rate=0.086)
        assert reduced.total_cents < full.total_cents
        assert reduced.subtotal_cents == 12900

    def test_empty_quote_is_zero(self) -> None:
        q = price_quote(PRICEBOOK, [])
        assert (q.subtotal_cents, q.tax_cents, q.total_cents) == (0, 0, 0)

    def test_unknown_service_rejected(self) -> None:
        with pytest.raises(QuoteError):
            price_quote(PRICEBOOK, [QuoteLineItem("SVC-NOPE")])

    def test_nonpositive_qty_rejected(self) -> None:
        with pytest.raises(QuoteError):
            price_quote(PRICEBOOK, [QuoteLineItem("SVC-AC-TUNE", 0)])


class TestProperties:
    @given(st.lists(st.integers(min_value=1, max_value=5), min_size=0, max_size=5))
    def test_total_is_subtotal_plus_tax(self, qtys: list[int]) -> None:
        items = [QuoteLineItem(PRICEBOOK[i % len(PRICEBOOK)].code, q) for i, q in enumerate(qtys)]
        q = price_quote(PRICEBOOK, items)
        assert q.total_cents == q.subtotal_cents + q.tax_cents
        assert q.total_cents >= q.subtotal_cents
        assert q.taxable_subtotal_cents <= q.subtotal_cents
