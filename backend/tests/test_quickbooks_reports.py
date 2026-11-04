"""Oracle + property tests for the QuickBooks Online request-builders + report parsers (PURE, no net).

GAP A4: prove the request URL/params built for each §2 call and that each ``parse_*`` maps a saved
sample-report JSON to the right cents fields — including the 91-120 / 121+ derivation from the detail
report and the current-liabilities-only quick-ratio denominator (QBO_DATA_MAP §2.4).

Every asserted figure is an INDEPENDENT hand-computed oracle derived from the fixture JSON, not from the
parser's own output. Money is integer cents (ADR-0003). No network, no realm, no refresh token required.
"""
from __future__ import annotations

import json
import pathlib
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.config import Settings
from app.integrations.accounting import quickbooks_reports as qr
from app.integrations.accounting.quickbooks_client import QuickBooksClient

_FIXTURES = (
    pathlib.Path(__file__).resolve().parents[1]
    / "app"
    / "integrations"
    / "accounting"
    / "fixtures"
    / "qbo_reports"
)


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


_REALM = "9130350000000001"


# --------------------------------------------------------------------------------------------
# 1. dollars_to_cents — total, fail-soft money parsing
# --------------------------------------------------------------------------------------------


class TestDollarsToCents:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("1500.00", 150000),
            (1500.0, 150000),
            ("0.00", 0),
            ("250.50", 25050),
            ("-300.25", -30025),
            ("1500", 150000),
            ("  42.10  ", 4210),
        ],
    )
    def test_known(self, value, expected: int) -> None:
        assert qr.dollars_to_cents(value) == expected

    @pytest.mark.parametrize("value", [None, "", "   ", "n/a", "abc"])
    def test_fail_soft_to_zero(self, value) -> None:
        # Missing/garbage cells degrade a KPI to 0, never raise (a partial report must not crash).
        assert qr.dollars_to_cents(value) == 0

    def test_rounds_float_dust_away_from_zero(self) -> None:
        # 1500.005 dollars -> 150000.5 cents -> 150001 (never truncates to 150000).
        assert qr.dollars_to_cents("1500.005") == 150001

    @given(st.integers(min_value=-10_000_000, max_value=10_000_000))
    def test_whole_dollar_round_trip(self, dollars: int) -> None:
        assert qr.dollars_to_cents(f"{dollars}.00") == dollars * 100


# --------------------------------------------------------------------------------------------
# 2. Request builders — exact path + params (minorversion pinned, accrual forced where required)
# --------------------------------------------------------------------------------------------


class TestReportRequestBuilders:
    def test_aged_receivables_url_and_params(self) -> None:
        path, params = qr.build_aged_receivables_request(_REALM, report_date=date(2026, 6, 17))
        assert path == f"/v3/company/{_REALM}/reports/AgedReceivables"
        assert params == {
            "minorversion": qr.QBO_MINOR_VERSION,
            "accounting_method": "Accrual",
            "aging_method": "Report_Date",
            "report_date": "2026-06-17",
        }

    def test_aged_receivable_detail_url(self) -> None:
        path, params = qr.build_aged_receivable_detail_request(_REALM, report_date=date(2026, 6, 17))
        assert path == f"/v3/company/{_REALM}/reports/AgedReceivableDetail"
        assert params["accounting_method"] == "Accrual"  # A/R is inherently accrual (§2.4)
        assert params["report_date"] == "2026-06-17"

    def test_balance_sheet_is_accrual_and_pins_minorversion(self) -> None:
        path, params = qr.build_balance_sheet_request(_REALM, date_macro="Today")
        assert path == f"/v3/company/{_REALM}/reports/BalanceSheet"
        assert params == {
            "minorversion": qr.QBO_MINOR_VERSION,
            "accounting_method": "Accrual",
            "date_macro": "Today",
        }

    def test_balance_sheet_explicit_dates_win_over_macro(self) -> None:
        _, params = qr.build_balance_sheet_request(
            _REALM, start_date=date(2026, 1, 1), end_date=date(2026, 6, 30), date_macro="Today"
        )
        assert params["start_date"] == "2026-01-01"
        assert params["end_date"] == "2026-06-30"
        assert "date_macro" not in params  # explicit range suppresses the macro

    def test_profit_and_loss_by_class_for_department_income(self) -> None:
        path, params = qr.build_profit_and_loss_request(
            _REALM,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 6, 30),
            summarize_column_by="Classes",
        )
        assert path == f"/v3/company/{_REALM}/reports/ProfitAndLoss"
        assert params["summarize_column_by"] == "Classes"
        assert params["accounting_method"] == "Accrual"

    def test_profit_and_loss_can_request_cash_basis(self) -> None:
        _, params = qr.build_profit_and_loss_request(_REALM, accrual=False)
        assert "accounting_method" not in params  # cash basis -> no Accrual override


class TestQueryRequestBuilders:
    def test_open_invoices_query(self) -> None:
        path, params = qr.build_open_invoices_query(_REALM)
        assert path == f"/v3/company/{_REALM}/query"
        assert params == {
            "query": "SELECT * FROM Invoice WHERE Balance > '0'",
            "minorversion": qr.QBO_MINOR_VERSION,
        }

    def test_open_bills_query(self) -> None:
        _, params = qr.build_open_bills_query(_REALM)
        assert params["query"] == "SELECT * FROM Bill WHERE Balance > '0'"

    def test_payments_query_window(self) -> None:
        _, params = qr.build_payments_query(_REALM, start=date(2026, 6, 8), end=date(2026, 6, 15))
        assert params["query"] == (
            "SELECT * FROM Payment WHERE TxnDate >= '2026-06-08' AND TxnDate <= '2026-06-15'"
        )
        assert params["minorversion"] == qr.QBO_MINOR_VERSION


# --------------------------------------------------------------------------------------------
# 3. parse_aged_receivables — grand-total buckets, in cents
# --------------------------------------------------------------------------------------------


class TestParseAgedReceivables:
    def test_buckets_from_grand_total(self) -> None:
        # Fixture grand-total row: Current 1000 / 1-30 500 / 31-60 200 / 61-90 300 / 91+ 700 / Total 2700.
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        assert aged.current_cents == 100000
        assert aged.d1_30_cents == 50000
        assert aged.d31_60_cents == 20000
        assert aged.d61_90_cents == 30000
        # The whole "91 and over" column lands in d91_120 PRE-split (121+ derived from detail later).
        assert aged.d91_120_cents == 70000
        assert aged.d121_plus_cents == 0
        assert aged.total_cents == 270000

    def test_pre_split_buckets_sum_to_total(self) -> None:
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        summed = (
            aged.current_cents
            + aged.d1_30_cents
            + aged.d31_60_cents
            + aged.d61_90_cents
            + aged.d91_120_cents
            + aged.d121_plus_cents
        )
        assert summed == aged.total_cents

    def test_anchors_grand_total_not_a_per_customer_subtotal(self) -> None:
        """A real QBO report can nest per-customer sub-sections whose Summary subtotal appears BEFORE
        the grand total. We must read the grand-total row (labeled TOTAL), never the first subtotal —
        else the whole portfolio aging is silently computed from one customer (the worst ADR-0003 bug)."""
        report = {
            "Columns": {"Column": [
                {"ColTitle": ""}, {"ColTitle": "Current"}, {"ColTitle": "1 - 30"},
                {"ColTitle": "31 - 60"}, {"ColTitle": "61 - 90"}, {"ColTitle": "91 and over"},
                {"ColTitle": "Total"},
            ]},
            "Rows": {"Row": [
                {  # a per-customer SECTION whose Summary subtotal is the first Summary in the tree
                    "type": "Section",
                    "Header": {"ColData": [{"value": "Acme Mechanical"}]},
                    "Rows": {"Row": [
                        {"type": "Data", "ColData": [
                            {"value": "Invoice #1"}, {"value": "100.00"}, {"value": "0"},
                            {"value": "0"}, {"value": "0"}, {"value": "0"}, {"value": "100.00"}]},
                    ]},
                    "Summary": {"ColData": [
                        {"value": "Total Acme Mechanical"}, {"value": "100.00"}, {"value": "0"},
                        {"value": "0"}, {"value": "0"}, {"value": "0"}, {"value": "100.00"}]},
                },
                {  # the GRAND total
                    "type": "Section",
                    "Summary": {"ColData": [
                        {"value": "TOTAL"}, {"value": "900.00"}, {"value": "100.00"},
                        {"value": "50.00"}, {"value": "25.00"}, {"value": "10.00"}, {"value": "1085.00"}]},
                },
            ]},
        }
        aged = qr.parse_aged_receivables(report)
        assert aged.current_cents == 90000  # the grand total, NOT Acme's 10000 subtotal
        assert aged.total_cents == 108500

    def test_resolves_buckets_by_column_title_with_leading_blank_and_121_split(self) -> None:
        """Columns are read by ColTitle, so a leading blank column + a reconfigured layout that splits
        91-120 from 121+ both parse correctly (a separate 121+ column folds into the pre-split 91+ pool)."""
        report = {
            "Columns": {"Column": [
                {"ColTitle": ""}, {"ColTitle": "Current"}, {"ColTitle": "1 - 30"},
                {"ColTitle": "31 - 60"}, {"ColTitle": "61 - 90"}, {"ColTitle": "91 - 120"},
                {"ColTitle": "121 and over"}, {"ColTitle": "Total"},
            ]},
            "Rows": {"Row": [
                {"type": "Section", "Summary": {"ColData": [
                    {"value": "TOTAL"}, {"value": "1000.00"}, {"value": "500.00"},
                    {"value": "200.00"}, {"value": "300.00"}, {"value": "700.00"},
                    {"value": "400.00"}, {"value": "3100.00"}]}},
            ]},
        }
        aged = qr.parse_aged_receivables(report)
        assert aged.current_cents == 100000
        assert aged.d1_30_cents == 50000
        assert aged.d31_60_cents == 20000
        assert aged.d61_90_cents == 30000
        assert aged.d91_120_cents == 110000  # 91-120 (700) + 121+ (400) folded pre-split
        assert aged.d121_plus_cents == 0
        assert aged.total_cents == 310000


# --------------------------------------------------------------------------------------------
# 4. parse_aged_receivable_detail + split_91_plus_from_detail — the 121+ derivation (§2.1/§2.3)
# --------------------------------------------------------------------------------------------


class TestAgedReceivableDetailAndSplit:
    def test_detail_rows_parse_days_and_open_balance(self) -> None:
        rows = qr.parse_aged_receivable_detail(_load("aged_receivable_detail.json"))
        # Three open invoices: 78d/$300, 100d/$400, 160d/$300 (all open balance > 0).
        assert rows == [
            {"days_overdue": 78, "open_balance_cents": 30000},
            {"days_overdue": 100, "open_balance_cents": 40000},
            {"days_overdue": 160, "open_balance_cents": 30000},
        ]

    def test_split_moves_121_plus_out_of_91_pool(self) -> None:
        # Summary 91+ pool = 700.00 (= 70000c). Detail: only the 160-day invoice ($300) is >=121 days.
        # So 121+ = 30000c ; 91-120 = 70000 - 30000 = 40000c. Other buckets + total unchanged.
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        rows = qr.parse_aged_receivable_detail(_load("aged_receivable_detail.json"))
        split = qr.split_91_plus_from_detail(aged, rows)
        assert split.d121_plus_cents == 30000
        assert split.d91_120_cents == 40000
        assert split.current_cents == 100000  # untouched
        assert split.total_cents == 270000  # untouched

    def test_split_still_sums_to_total(self) -> None:
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        rows = qr.parse_aged_receivable_detail(_load("aged_receivable_detail.json"))
        split = qr.split_91_plus_from_detail(aged, rows)
        summed = (
            split.current_cents
            + split.d1_30_cents
            + split.d31_60_cents
            + split.d61_90_cents
            + split.d91_120_cents
            + split.d121_plus_cents
        )
        assert summed == split.total_cents

    def test_empty_detail_leaves_summary_unchanged(self) -> None:
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        assert qr.split_91_plus_from_detail(aged, []) == aged

    def test_121_plus_never_exceeds_reported_91_pool(self) -> None:
        # If detail somehow over-reports >=121d beyond the summary 91+ pool, clamp to the pool.
        aged = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        over = [{"days_overdue": 200, "open_balance_cents": 999_999_00}]
        split = qr.split_91_plus_from_detail(aged, over)
        assert split.d121_plus_cents == aged.d91_120_cents  # clamped to 70000
        assert split.d91_120_cents == 0


# --------------------------------------------------------------------------------------------
# 5. parse_balance_sheet — cash / CC / LOC / CURRENT liabilities only (§2.4 quick-ratio rule)
# --------------------------------------------------------------------------------------------


class TestParseBalanceSheet:
    def test_cash_is_total_bank_accounts(self) -> None:
        # Fixture: Operating Checking 5000 + Savings 2000 -> Total Bank Accounts 7000.00.
        bs = qr.parse_balance_sheet(_load("balance_sheet.json"))
        assert bs.cash_cents == 700000

    def test_credit_card_balance_is_total_credit_cards(self) -> None:
        bs = qr.parse_balance_sheet(_load("balance_sheet.json"))
        assert bs.credit_card_balance_cents == 120000  # Fleet Card 1200.00

    def test_line_of_credit_by_account_name(self) -> None:
        bs = qr.parse_balance_sheet(_load("balance_sheet.json"))
        assert bs.line_of_credit_cents == 50000  # "Line of Credit" 500.00

    def test_current_liabilities_is_current_subtotal_not_total(self) -> None:
        # The CPA rule (§2.4): denominator = Total Current Liabilities (2500.00), EXCLUDING the
        # 10000.00 long-term Equipment Loan. Total Liabilities would be 12500.00 — must NOT be used.
        bs = qr.parse_balance_sheet(_load("balance_sheet.json"))
        assert bs.current_liabilities_cents == 250000
        assert bs.current_liabilities_cents != 1_250_000  # would be wrong (total liabilities)

    def test_quick_ratio_uses_current_liabilities(self) -> None:
        # Acid-test (§2.4): (cash + A/R) / current liabilities. With AR total 2700 from the aging report:
        #   (7000 + 2700) / 2500 = 3.88. Using total liabilities (12500) would wrongly give 0.776.
        bs = qr.parse_balance_sheet(_load("balance_sheet.json"))
        ar = qr.parse_aged_receivables(_load("aged_receivables_summary.json"))
        quick = (bs.cash_cents + ar.total_cents) / bs.current_liabilities_cents
        assert quick == pytest.approx((700000 + 270000) / 250000)
        assert quick == pytest.approx(3.88, abs=0.01)


# --------------------------------------------------------------------------------------------
# 6. parse_profit_and_loss — income / COGS / TRUE gross margin / net income (§2.4)
# --------------------------------------------------------------------------------------------


class TestParseProfitAndLoss:
    def test_section_subtotals(self) -> None:
        pl = qr.parse_profit_and_loss(_load("profit_and_loss.json"))
        assert pl.total_income_cents == 1_000_000  # Total Income 10000.00
        assert pl.total_cogs_cents == 400000  # Total COGS 4000.00
        assert pl.total_expenses_cents == 250000  # Total Expenses 2500.00
        assert pl.net_income_cents == 350000  # NET INCOME 3500.00

    def test_gross_profit_and_true_margin(self) -> None:
        # Gross profit = 10000 - 4000 = 6000. Gross MARGIN = 6000/10000 = 0.60 (not markup 6000/4000=1.5).
        pl = qr.parse_profit_and_loss(_load("profit_and_loss.json"))
        assert pl.gross_profit_cents == 600000
        assert pl.gross_margin_ratio == pytest.approx(0.60)
        # Guard against the markup mislabel a CPA would catch (§2.4).
        assert pl.gross_margin_ratio != pytest.approx(1.5)

    def test_zero_revenue_margin_is_none(self) -> None:
        empty = qr.ProfitAndLossSummary(0, 0, 0, 0)
        assert empty.gross_margin_ratio is None  # never divide by zero


# --------------------------------------------------------------------------------------------
# 7. Query API parsers — Invoice / Bill / Payment rows + cash_collected
# --------------------------------------------------------------------------------------------


class TestParseInvoiceQuery:
    def test_maps_open_invoices(self) -> None:
        invoices = qr.parse_invoice_query(_load("invoice_query.json"))
        assert [i.id for i in invoices] == ["1041", "1102"]
        first = invoices[0]
        assert first.customer == "Birch Property Group"
        assert first.balance_cents == 30000  # 300.00
        assert first.total_cents == 30000
        assert first.txn_date == date(2026, 3, 1)
        assert first.due_date == date(2026, 3, 31)

    def test_invoice_cents_sum(self) -> None:
        invoices = qr.parse_invoice_query(_load("invoice_query.json"))
        # 300.00 + 1500.00 = 1800.00 open A/R.
        assert sum(i.balance_cents for i in invoices) == 180000


class TestParseBillQuery:
    def test_maps_open_bills(self) -> None:
        bills = qr.parse_bill_query(_load("bill_query.json"))
        assert [b.id for b in bills] == ["501", "502"]
        assert bills[0].vendor == "Supply House Inc"
        assert bills[0].balance_cents == 80000  # 800.00
        assert sum(b.balance_cents for b in bills) == 125000  # 800 + 450


class TestParsePaymentQuery:
    def test_maps_payments_and_cash_collected(self) -> None:
        payments = qr.parse_payment_query(_load("payment_query.json"))
        assert [p.id for p in payments] == ["9001", "9002", "9003"]
        assert payments[2].amount_cents == 25050  # 250.50
        # cash_collected = 1500.00 + 500.00 + 250.50 = 2250.50 -> 225050 cents.
        assert qr.cash_collected_cents(payments) == 225050

    def test_empty_query_response_is_empty_list(self) -> None:
        assert qr.parse_payment_query({"QueryResponse": {}}) == []
        assert qr.parse_payment_query({}) == []


# --------------------------------------------------------------------------------------------
# 8. Fail-closed: the live client raises (never fabricates) without connected credentials (ADR-0005)
# --------------------------------------------------------------------------------------------


def _unconfigured_settings() -> Settings:
    # accounting_mode=quickbooks but NO client/secret/refresh/realm -> the demo posture.
    return Settings(
        accounting_mode="quickbooks",
        quickbooks_client_id=None,
        quickbooks_client_secret=None,
        quickbooks_refresh_token=None,
        quickbooks_realm_id=None,
    )


class TestFailClosedWithoutCredentials:
    @pytest.mark.asyncio
    async def test_get_ar_invoices_raises(self) -> None:
        client = QuickBooksClient(_unconfigured_settings())
        with pytest.raises(RuntimeError) as exc:
            await client.get_ar_invoices()
        assert "QuickBooks mode requires" in str(exc.value)

    @pytest.mark.asyncio
    async def test_get_ap_bills_raises(self) -> None:
        client = QuickBooksClient(_unconfigured_settings())
        with pytest.raises(RuntimeError):
            await client.get_ap_bills()

    @pytest.mark.asyncio
    async def test_get_company_financials_raises(self) -> None:
        client = QuickBooksClient(_unconfigured_settings())
        with pytest.raises(RuntimeError):
            await client.get_company_financials()


# --------------------------------------------------------------------------------------------
# 9. Property — parsing any well-formed money cell yields exact cents (round-trip invariant)
# --------------------------------------------------------------------------------------------


class TestParseProperties:
    @given(st.integers(min_value=0, max_value=5_000_000), st.integers(min_value=0, max_value=99))
    def test_invoice_balance_round_trips_to_cents(self, dollars: int, cents: int) -> None:
        payload = {
            "QueryResponse": {
                "Invoice": [
                    {
                        "Id": "X",
                        "DocNumber": "X",
                        "TxnDate": "2026-06-01",
                        "DueDate": "2026-06-30",
                        "TotalAmt": f"{dollars}.{cents:02d}",
                        "Balance": f"{dollars}.{cents:02d}",
                        "CustomerRef": {"name": "Test"},
                    }
                ]
            }
        }
        parsed = qr.parse_invoice_query(payload)
        assert parsed[0].balance_cents == dollars * 100 + cents
