"""Pure QuickBooks Online request-builders + response-parsers (ADR-0003 / ADR-0005).

This module is the **deterministic, network-free** half of the QBO live read path. It does two jobs,
both unit-testable without a realm or a refresh token:

  1. **Build** the exact Intuit request (path + query params) for each Finance read in
     ``docs/QBO_DATA_MAP.md §2`` — the Reports API calls (``AgedReceivables`` / ``AgedReceivableDetail``
     / ``BalanceSheet`` / ``ProfitAndLoss``) and the Query API selects (``Invoice`` / ``Bill`` /
     ``Payment``). ``minorversion`` is pinned and accrual is forced where the CPA notes (§2.4) require it.
  2. **Parse** a saved sample-report JSON into cents-based domain shapes — money is carried as integer
     **cents** (ADR-0003: dollars only at the API boundary). Parsing is total and fail-soft on missing
     cells (a malformed/absent figure parses to 0 cents, never raises) so a partial report degrades a
     KPI rather than crashing the scorecard.

The live ``QuickBooksClient`` (``quickbooks_client.py``) composes these: it gates the actual HTTP on the
connected-credential check, then feeds the response JSON through the matching ``parse_*`` here. Because
these functions never touch the network, the request shapes and the cents math are pinned by tests on
the saved fixtures in ``fixtures/qbo_reports/`` — no live company required.

Pinned ``minorversion`` (Intuit Reports/Query API). Bump deliberately at go-live, never silently — a
generic connector lagging Intuit's minorversion is exactly the Zapier brittleness we removed (§1.4).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

# Pin the Intuit API minorversion. We own the request contract and bump it on our cadence (QBO_DATA_MAP
# §1.4) — not a generic connector that lags Intuit.
QBO_MINOR_VERSION = "75"

# Reports API report names (QBO_DATA_MAP §2.1). The receivables report resolves under either name form;
# we use the documented `AgedReceivables` / `AgedReceivableDetail` family (§2 report-name note).
REPORT_AGED_RECEIVABLES = "AgedReceivables"
REPORT_AGED_RECEIVABLE_DETAIL = "AgedReceivableDetail"
REPORT_BALANCE_SHEET = "BalanceSheet"
REPORT_PROFIT_AND_LOSS = "ProfitAndLoss"

# Aging-bucket day boundaries. QBO's summary report buckets at "91 and over"; the scorecard needs the
# 91-120 / 121+ split, which we derive from the per-invoice detail report (QBO_DATA_MAP §2.1 ⚠ / §2.3).
_BUCKET_121_FLOOR_DAYS = 121


# ==============================================================================================
# Cents helpers (ADR-0003) — QBO returns decimal dollars as a string or number; we carry cents.
# ==============================================================================================


def dollars_to_cents(value: Any) -> int:
    """Convert a QBO money cell (``"1500.00"`` | ``1500.0`` | ``None``) to integer cents.

    Total + fail-soft: a missing/blank/garbage cell parses to ``0`` cents (never raises), so a partial
    report degrades a single KPI rather than crashing the scorecard. Rounds half-away-from-zero on the
    cent (QBO money is already 2dp; this only guards float dust like ``1500.005``).
    """
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    try:
        dollars = float(text)
    except (TypeError, ValueError):
        return 0
    # Round on cents, away from zero, to avoid 1499.9999 -> 149999 truncation.
    return int(dollars * 100 + (0.5 if dollars >= 0 else -0.5))


# ==============================================================================================
# Parsed report domain shapes (frozen, cents)
# ==============================================================================================


@dataclass(frozen=True)
class AgedReceivables:
    """A/R aging totals in cents, split into the scorecard's six buckets.

    ``current_cents`` + the five overdue buckets sum to ``total_cents``. The 91-120 / 121+ split is the
    one the summary report cannot give directly (it stops at "91 and over") — see
    :func:`parse_aged_receivables` (which folds the whole 91+ column into 91-120 as a conservative
    placeholder) vs :func:`split_91_plus_from_detail` (which derives the true split per-invoice, §2.1).
    """

    current_cents: int
    d1_30_cents: int
    d31_60_cents: int
    d61_90_cents: int
    d91_120_cents: int
    d121_plus_cents: int
    total_cents: int


@dataclass(frozen=True)
class BalanceSheetSummary:
    """Balance-sheet figures the Finance scorecard reads, in cents.

    ``current_liabilities_cents`` is the **Current Liabilities subtotal only** — never total liabilities
    — so the quick ratio is the correct acid-test (QBO_DATA_MAP §2.4: a CPA will catch total-liabilities
    here). The revolving LOC is a *current* liability and is therefore already inside this subtotal.
    """

    cash_cents: int
    credit_card_balance_cents: int
    line_of_credit_cents: int
    current_liabilities_cents: int


@dataclass(frozen=True)
class ProfitAndLossSummary:
    """P&L figures in cents. ``gross_margin_ratio`` is TRUE gross margin (revenue - COGS) / revenue —
    never markup-on-cost (QBO_DATA_MAP §2.4). ``department_income_cents`` maps a class/department name to
    its net-income cents when ``summarize_column_by=Classes`` was requested (else empty)."""

    total_income_cents: int
    total_cogs_cents: int
    total_expenses_cents: int
    net_income_cents: int
    department_income_cents: dict[str, int] = field(default_factory=dict)

    @property
    def gross_profit_cents(self) -> int:
        return self.total_income_cents - self.total_cogs_cents

    @property
    def gross_margin_ratio(self) -> float | None:
        """(revenue - COGS) / revenue. ``None`` when there is no revenue (never divide by zero)."""
        if self.total_income_cents == 0:
            return None
        return self.gross_profit_cents / self.total_income_cents


@dataclass(frozen=True)
class OpenInvoice:
    """One open A/R invoice row from the Query API (``Balance > 0``)."""

    id: str
    doc_number: str
    customer: str
    txn_date: date | None
    due_date: date | None
    total_cents: int
    balance_cents: int


@dataclass(frozen=True)
class OpenBill:
    """One open A/P bill row from the Query API (``Balance > 0``)."""

    id: str
    doc_number: str
    vendor: str
    txn_date: date | None
    due_date: date | None
    total_cents: int
    balance_cents: int


@dataclass(frozen=True)
class PaymentRow:
    """One received-payment row from the Query API (cash-basis collections, §2.4)."""

    id: str
    customer: str
    txn_date: date | None
    amount_cents: int


# ==============================================================================================
# Request builders — the exact Intuit request shape (path + params). Network-free + unit-testable.
# ==============================================================================================


def _company_base(realm_id: str) -> str:
    return f"/v3/company/{realm_id}"


def build_report_request(
    realm_id: str,
    report_name: str,
    *,
    params: dict[str, Any] | None = None,
    accrual: bool = True,
) -> tuple[str, dict[str, str]]:
    """Build a Reports API request: ``(path, query_params)``.

    Path = ``/v3/company/{realmId}/reports/{ReportName}``. ``minorversion`` is always pinned and
    ``accounting_method=Accrual`` is forced when ``accrual`` (A/R + Balance Sheet are inherently accrual,
    §2.4). All param values are stringified so the shape is stable and assertable.
    """
    query: dict[str, str] = {"minorversion": QBO_MINOR_VERSION}
    if accrual:
        query["accounting_method"] = "Accrual"
    for key, value in (params or {}).items():
        if value is None:
            continue
        query[key] = value if isinstance(value, str) else str(value)
    return f"{_company_base(realm_id)}/reports/{report_name}", query


def build_aged_receivables_request(
    realm_id: str, *, report_date: date | None = None
) -> tuple[str, dict[str, str]]:
    """``AgedReceivables`` summary, as-of ``report_date``, aged by report date, accrual (§2.1)."""
    params: dict[str, Any] = {"aging_method": "Report_Date"}
    if report_date is not None:
        params["report_date"] = report_date.isoformat()
    return build_report_request(realm_id, REPORT_AGED_RECEIVABLES, params=params, accrual=True)


def build_aged_receivable_detail_request(
    realm_id: str, *, report_date: date | None = None
) -> tuple[str, dict[str, str]]:
    """``AgedReceivableDetail`` — per-invoice rows for the 121+ derivation + collections worklist."""
    params: dict[str, Any] = {"aging_method": "Report_Date"}
    if report_date is not None:
        params["report_date"] = report_date.isoformat()
    return build_report_request(realm_id, REPORT_AGED_RECEIVABLE_DETAIL, params=params, accrual=True)


def build_balance_sheet_request(
    realm_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    date_macro: str | None = None,
) -> tuple[str, dict[str, str]]:
    """``BalanceSheet`` point-in-time, accrual (§2.1). Pass either an explicit range or a ``date_macro``
    (e.g. ``Today``); explicit dates win when both are given."""
    params: dict[str, Any] = {}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()
    if date_macro is not None and not (start_date or end_date):
        params["date_macro"] = date_macro
    return build_report_request(realm_id, REPORT_BALANCE_SHEET, params=params, accrual=True)


def build_profit_and_loss_request(
    realm_id: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    summarize_column_by: str | None = None,
    accrual: bool = True,
) -> tuple[str, dict[str, str]]:
    """``ProfitAndLoss`` over a range; ``summarize_column_by=Classes`` (or ``Month``) for the
    per-department / trailing grid (§2.1). Accrual is the default basis on a ~$7M contractor (§2.4)."""
    params: dict[str, Any] = {}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()
    if summarize_column_by is not None:
        params["summarize_column_by"] = summarize_column_by
    return build_report_request(realm_id, REPORT_PROFIT_AND_LOSS, params=params, accrual=accrual)


def build_query_request(realm_id: str, query: str) -> tuple[str, dict[str, str]]:
    """Build a Query API request: ``(path, {query, minorversion})``.

    Path = ``/v3/company/{realmId}/query``. The QBO Query language is a SQL subset; the caller passes the
    full select. ``minorversion`` is pinned.
    """
    return f"{_company_base(realm_id)}/query", {
        "query": query,
        "minorversion": QBO_MINOR_VERSION,
    }


def build_open_invoices_query(realm_id: str) -> tuple[str, dict[str, str]]:
    """Open A/R rows: ``SELECT * FROM Invoice WHERE Balance > '0'`` (§2.2)."""
    return build_query_request(realm_id, "SELECT * FROM Invoice WHERE Balance > '0'")


def build_open_bills_query(realm_id: str) -> tuple[str, dict[str, str]]:
    """Open A/P rows: ``SELECT * FROM Bill WHERE Balance > '0'`` (§2.2)."""
    return build_query_request(realm_id, "SELECT * FROM Bill WHERE Balance > '0'")


def build_payments_query(realm_id: str, *, start: date, end: date) -> tuple[str, dict[str, str]]:
    """Cash collected over a window: ``SELECT * FROM Payment WHERE TxnDate >= '..' AND TxnDate <= '..'``
    (§2.2). Cash-basis collections — distinct from booked P&L revenue (§2.4)."""
    query = (
        f"SELECT * FROM Payment WHERE TxnDate >= '{start.isoformat()}' "
        f"AND TxnDate <= '{end.isoformat()}'"
    )
    return build_query_request(realm_id, query)


# ==============================================================================================
# Report-grid helpers (QBO Reports JSON: nested Rows with ColData / Header / Summary / Section).
# ==============================================================================================


def _row_label(row: dict) -> str:
    """The first ColData cell's value for a Data/Section row's Header or ColData (the account/customer)."""
    coldata = row.get("ColData")
    if isinstance(coldata, list) and coldata:
        return str(coldata[0].get("value", "")).strip()
    header = row.get("Header")
    if isinstance(header, dict):
        hd = header.get("ColData")
        if isinstance(hd, list) and hd:
            return str(hd[0].get("value", "")).strip()
    return ""


def _summary_amount_cents(row: dict, *, col: int = 1) -> int:
    """Cents of the ``col``-th cell in a Section row's Summary (the section subtotal)."""
    summary = row.get("Summary")
    if isinstance(summary, dict):
        cells = summary.get("ColData")
        if isinstance(cells, list) and len(cells) > col:
            return dollars_to_cents(cells[col].get("value"))
    return 0


def _iter_child_rows(node: dict):
    """Yield the child ``Row`` entries of a Rows container (report root or a Section)."""
    rows = node.get("Rows")
    if isinstance(rows, dict):
        children = rows.get("Row")
        if isinstance(children, list):
            yield from children


def _walk_sections(root: dict):
    """In-order depth-first walk of every Section/row node under the report root.

    Yields each ``Row`` dict in document order (a node before its children) so detail rows preserve the
    report's ordering — the collections worklist must be deterministic, not reversed.
    """
    for node in _iter_child_rows(root):
        yield node
        yield from _walk_sections(node)


def _find_section_summary_cents(report: dict, label: str, *, col: int = 1) -> int:
    """Cents of the Summary subtotal of the first section whose Header label == ``label`` (case-insensitive)."""
    root = report.get("Rows", {})
    wanted = label.strip().lower()
    for node in _walk_sections({"Rows": root}):
        if _row_label(node).lower() == wanted:
            return _summary_amount_cents(node, col=col)
    return 0


def _data_rows_under(report: dict, section_label: str):
    """Yield the leaf Data rows directly under the first section matching ``section_label``."""
    root = report.get("Rows", {})
    wanted = section_label.strip().lower()
    for node in _walk_sections({"Rows": root}):
        if _row_label(node).lower() == wanted:
            for child in _walk_sections(node):
                if child.get("type") == "Data" and isinstance(child.get("ColData"), list):
                    yield child
            return


# ==============================================================================================
# Parsers — saved sample report JSON -> cents domain shapes
# ==============================================================================================


def parse_aged_receivables(report: dict) -> AgedReceivables:
    """Parse an ``AgedReceivables`` summary into bucket cents.

    QBO's summary report exposes Current / 1-30 / 31-60 / 61-90 / **91 and over** / Total. We read the
    grand-total Summary row's columns. Because the summary stops at "91 and over", we fold that whole
    column into ``d91_120_cents`` and leave ``d121_plus_cents`` at 0 here — the true 91-120 / 121+ split
    is derived from the detail report by :func:`split_91_plus_from_detail` (QBO_DATA_MAP §2.1 ⚠, §2.3).
    """
    total_row = _grand_total_row(report)
    cells = total_row.get("ColData", []) if total_row else []

    def cell(idx: int) -> int:
        return dollars_to_cents(cells[idx].get("value")) if 0 <= idx < len(cells) else 0

    def cells_sum(indices: list[int]) -> int:
        return sum(cell(i) for i in indices)

    cols = _aging_summary_columns(report)
    if cols is not None:
        # Resolved by ColTitle — robust to a leading blank column or reconfigured buckets.
        current = cells_sum(cols["current"]) if cols["current"] else cell(1)
        d1_30 = cells_sum(cols["d1_30"])
        d31_60 = cells_sum(cols["d31_60"])
        d61_90 = cells_sum(cols["d61_90"])
        d91 = cells_sum(cols["d91_plus"])
        total = cells_sum(cols["total"]) if cols["total"] else (current + d1_30 + d31_60 + d61_90 + d91)
    else:
        # Documented positional fallback: [label, Current, 1-30, 31-60, 61-90, 91+, Total].
        current, d1_30, d31_60, d61_90, d91 = cell(1), cell(2), cell(3), cell(4), cell(5)
        total = cell(6) if len(cells) > 6 else (current + d1_30 + d31_60 + d61_90 + d91)

    return AgedReceivables(
        current_cents=current,
        d1_30_cents=d1_30,
        d31_60_cents=d31_60,
        d61_90_cents=d61_90,
        d91_120_cents=d91,  # whole "91 and over" column(s) folded; split derived from detail
        d121_plus_cents=0,
        total_cents=total,
    )


_AGING_SUMMARY_BUCKETS = ("current", "d1_30", "d31_60", "d61_90", "d91_plus", "total")


def _aging_summary_columns(report: dict) -> dict[str, list[int]] | None:
    """Resolve the AgedReceivables summary bucket columns BY TITLE, not by fixed position.

    QBO lets a company reconfigure aging buckets and the report may carry a leading blank column, so a
    position-based read (Current/1-30/... at indices 1..6) silently shifts every bucket if the layout
    differs (QBO_DATA_MAP §2.1) — a wrong-but-plausible aging total a CPA would never trust. We map each
    money column by the day-range in its ColTitle:
        "Current"->current · "1 - 30"->d1_30 · "31 - 60"->d31_60 · "61 - 90"->d61_90 ·
        "91 and over" / "91 - 120" / "121 and over"->d91_plus (folded; the 91-120 / 121+ split comes from
        the detail report) · "Total"->total
    Returns bucket -> [column index(es)] (``d91_plus`` may span >1 column), or ``None`` if the core
    overdue buckets don't resolve (the caller then falls back to the documented positional layout).
    """
    titles = _column_titles(report)  # lowercased + stripped
    if not titles:
        return None
    cols: dict[str, list[int]] = {k: [] for k in _AGING_SUMMARY_BUCKETS}
    for i, title in enumerate(titles):
        if not title:
            continue
        if title == "current":
            cols["current"].append(i)
            continue
        if title.startswith("total"):
            cols["total"].append(i)
            continue
        nums = [int(n) for n in re.findall(r"\d+", title)]
        if not nums:
            continue
        start = nums[0]  # the bucket's lower day-boundary
        if 0 <= start <= 1:
            cols["d1_30"].append(i)
        elif start == 31:
            cols["d31_60"].append(i)
        elif start == 61:
            cols["d61_90"].append(i)
        elif start >= 91:
            cols["d91_plus"].append(i)  # 91-120 and a separate 121+ column both fold here
    if not (cols["d1_30"] and cols["d31_60"] and cols["d61_90"] and cols["d91_plus"]):
        return None  # titles didn't resolve the core buckets — use the positional fallback
    return cols


_GRAND_TOTAL_LABELS = {"total", "grand total", "totals", "total receivables"}


def _grand_total_row(report: dict) -> dict | None:
    """The report's GRAND-TOTAL Summary row (its ColData holds the column totals).

    Anchoring matters: a real QBO ``AgedReceivables`` can nest per-customer sub-sections that each
    carry their own Summary subtotal, so naively taking the *first* row with a Summary would silently
    compute the whole portfolio aging from ONE customer's subtotal — a wrong-but-plausible number, the
    worst ADR-0003 failure mode (QBO_DATA_MAP §2.1). We anchor explicitly, in order of trust:
      1. a node QBO tags ``group == "GrandTotal"``;
      2. a Summary whose first label is TOTAL / GRAND TOTAL (the report's grand-total row — a
         sub-section subtotal reads "Total <Customer>", which does NOT match); prefer the LAST such;
      3. only then fall back to the first top-level Summary, then the last Summary anywhere.
    """

    def summary_of(node: dict) -> dict | None:
        s = node.get("Summary")
        return s if isinstance(s, dict) else None

    def label_of(summary: dict) -> str:
        cells = summary.get("ColData")
        if isinstance(cells, list) and cells:
            return str(cells[0].get("value", "")).strip().lower()
        return ""

    # (1) Explicit GrandTotal group tag.
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        if str(node.get("group", "")).strip().lower() == "grandtotal":
            s = summary_of(node)
            if s is not None:
                return s
    # (2) A Summary labeled TOTAL / GRAND TOTAL (outermost == last in document order).
    labeled: dict | None = None
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        s = summary_of(node)
        if s is not None and label_of(s) in _GRAND_TOTAL_LABELS:
            labeled = s
    if labeled is not None:
        return labeled
    # (3) Fall back to the first top-level Summary, then the last Summary anywhere in the tree.
    for node in _iter_child_rows(report.get("Rows", {})):
        s = summary_of(node)
        if s is not None:
            return s
    last: dict | None = None
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        s = summary_of(node)
        if s is not None:
            last = s
    return last


def parse_aged_receivable_detail(report: dict) -> list[dict]:
    """Parse ``AgedReceivableDetail`` into per-invoice rows: ``{days_overdue, open_balance_cents}``.

    Detail columns include a "Past Due" (days) cell and an "Open Balance" money cell. We read those by
    column position (the report-name note in §2 confirms this family's structure). Rows without a numeric
    open balance are skipped. This is the input to :func:`split_91_plus_from_detail`.
    """
    columns = _column_titles(report)
    past_due_idx = _column_index(columns, "past due")
    balance_idx = _column_index(columns, "open balance")
    if balance_idx is None:  # detail without an explicit open-balance col -> fall back to "amount"
        balance_idx = _column_index(columns, "amount")

    out: list[dict] = []
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        if node.get("type") != "Data":
            continue
        cells = node.get("ColData")
        if not isinstance(cells, list):
            continue
        balance = dollars_to_cents(cells[balance_idx].get("value")) if balance_idx is not None and len(cells) > balance_idx else 0
        if balance == 0:
            continue
        days = 0
        if past_due_idx is not None and len(cells) > past_due_idx:
            raw = str(cells[past_due_idx].get("value", "")).strip()
            try:
                days = int(float(raw)) if raw else 0
            except ValueError:
                days = 0
        out.append({"days_overdue": days, "open_balance_cents": balance})
    return out


def _column_titles(report: dict) -> list[str]:
    cols = report.get("Columns", {})
    column = cols.get("Column", []) if isinstance(cols, dict) else []
    return [str(c.get("ColTitle", "")).strip().lower() for c in column]


def _column_index(titles: list[str], wanted: str) -> int | None:
    wanted = wanted.strip().lower()
    for i, title in enumerate(titles):
        if title == wanted:
            return i
    return None


def split_91_plus_from_detail(
    summary: AgedReceivables, detail_rows: list[dict]
) -> AgedReceivables:
    """Derive the true 91-120 vs 121+ split from the per-invoice detail (QBO_DATA_MAP §2.1 / §2.3).

    Takes the summary (whose ``d91_120_cents`` currently holds the WHOLE "91 and over" column) and the
    detail rows (``days_overdue`` / ``open_balance_cents``). Any invoice ≥121 days overdue moves into the
    121+ bucket; the rest of the 91+ pool stays in 91-120. The other buckets and the grand total are
    preserved exactly. If the detail is empty, the summary is returned unchanged (fail-soft).
    """
    if not detail_rows:
        return summary
    cents_121_plus = sum(
        r["open_balance_cents"] for r in detail_rows if r.get("days_overdue", 0) >= _BUCKET_121_FLOOR_DAYS
    )
    # The 91+ pool to redistribute is what the summary folded into d91_120_cents.
    pool_91_plus = summary.d91_120_cents
    cents_121_plus = min(cents_121_plus, pool_91_plus)  # never exceed the reported 91+ pool
    return AgedReceivables(
        current_cents=summary.current_cents,
        d1_30_cents=summary.d1_30_cents,
        d31_60_cents=summary.d31_60_cents,
        d61_90_cents=summary.d61_90_cents,
        d91_120_cents=pool_91_plus - cents_121_plus,
        d121_plus_cents=cents_121_plus,
        total_cents=summary.total_cents,
    )


def parse_balance_sheet(report: dict) -> BalanceSheetSummary:
    """Parse a ``BalanceSheet`` into the Finance figures (cents).

    - **cash** = the "Total Bank Accounts" section subtotal (Assets ▸ Bank).
    - **credit_card_balance** = the "Total Credit Cards" section subtotal (Liabilities ▸ Credit Card).
    - **line_of_credit** = a leaf account named like a line of credit (by name; §2.3 — it depends on the
      LOC being its own COA account).
    - **current_liabilities** = the **"Total Current Liabilities" subtotal ONLY** (never total
      liabilities; §2.4) — the correct quick-ratio denominator, with the revolving LOC already inside it.
    """
    cash = _find_section_summary_cents(report, "Bank Accounts")
    credit_cards = _find_section_summary_cents(report, "Credit Cards")
    current_liabilities = _find_section_summary_cents(report, "Current Liabilities")
    loc = _find_line_of_credit_cents(report)
    return BalanceSheetSummary(
        cash_cents=cash,
        credit_card_balance_cents=credit_cards,
        line_of_credit_cents=loc,
        current_liabilities_cents=current_liabilities,
    )


_LOC_NAME_HINTS = ("line of credit", "loc", "operating line", "revolving")


def _find_line_of_credit_cents(report: dict) -> int:
    """Sum leaf Data accounts whose name looks like a line of credit (§2.3 — LOC by COA account name)."""
    total = 0
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        if node.get("type") != "Data":
            continue
        cells = node.get("ColData")
        if not isinstance(cells, list) or not cells:
            continue
        name = str(cells[0].get("value", "")).strip().lower()
        if any(hint in name for hint in _LOC_NAME_HINTS):
            total += dollars_to_cents(cells[-1].get("value"))
    return total


def parse_profit_and_loss(report: dict) -> ProfitAndLossSummary:
    """Parse a ``ProfitAndLoss`` into income / COGS / expenses / net-income cents.

    Section subtotals are read by their Summary label ("Total Income", "Total Cost of Goods Sold",
    "Total Expenses"); Net Income from the "NET INCOME" data row. When ``summarize_column_by=Classes``
    was requested, each per-class net-income column is captured into ``department_income_cents`` (here we
    parse the single-column shape; per-class columns map name->cents when present).
    """
    income = _find_section_summary_cents(report, "Income")
    cogs = _find_section_summary_cents(report, "Cost of Goods Sold")
    expenses = _find_section_summary_cents(report, "Expenses")
    net_income = _find_net_income_cents(report)
    return ProfitAndLossSummary(
        total_income_cents=income,
        total_cogs_cents=cogs,
        total_expenses_cents=expenses,
        net_income_cents=net_income,
        department_income_cents=_parse_class_columns(report),
    )


def _find_net_income_cents(report: dict) -> int:
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        label = _row_label(node).lower()
        if label in ("net income", "net operating income"):
            cells = node.get("ColData")
            if isinstance(cells, list) and len(cells) > 1:
                return dollars_to_cents(cells[-1].get("value"))
    return 0


def _parse_class_columns(report: dict) -> dict[str, int]:
    """When a P&L is summarized by Classes/Departments, the Net Income data row carries one money cell
    per class. Map the (non-Total) column titles to those cents. Single-column reports -> empty dict."""
    titles = [str(c.get("ColTitle", "")).strip() for c in
              (report.get("Columns", {}).get("Column", []) if isinstance(report.get("Columns"), dict) else [])]
    # Money columns are every column after the first (account) col; skip a trailing "Total" col.
    class_cols = [(i, t) for i, t in enumerate(titles) if i >= 1 and t.lower() != "total"]
    if len(class_cols) <= 1:
        return {}
    for node in _walk_sections({"Rows": report.get("Rows", {})}):
        if _row_label(node).lower() in ("net income", "net operating income"):
            cells = node.get("ColData")
            if isinstance(cells, list):
                out: dict[str, int] = {}
                for idx, title in class_cols:
                    if len(cells) > idx and title:
                        out[title] = dollars_to_cents(cells[idx].get("value"))
                return out
    return {}


# ==============================================================================================
# Query API parsers (entity rows)
# ==============================================================================================


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _query_rows(payload: dict, entity: str) -> list[dict]:
    qr = payload.get("QueryResponse", {})
    rows = qr.get(entity, []) if isinstance(qr, dict) else []
    return rows if isinstance(rows, list) else []


def parse_invoice_query(payload: dict) -> list[OpenInvoice]:
    """Parse ``QueryResponse.Invoice`` rows into :class:`OpenInvoice` (cents)."""
    out: list[OpenInvoice] = []
    for row in _query_rows(payload, "Invoice"):
        customer = row.get("CustomerRef", {}) if isinstance(row.get("CustomerRef"), dict) else {}
        out.append(
            OpenInvoice(
                id=str(row.get("Id", "")),
                doc_number=str(row.get("DocNumber", "")),
                customer=str(customer.get("name", customer.get("value", ""))),
                txn_date=_parse_iso_date(row.get("TxnDate")),
                due_date=_parse_iso_date(row.get("DueDate")),
                total_cents=dollars_to_cents(row.get("TotalAmt")),
                balance_cents=dollars_to_cents(row.get("Balance")),
            )
        )
    return out


def parse_bill_query(payload: dict) -> list[OpenBill]:
    """Parse ``QueryResponse.Bill`` rows into :class:`OpenBill` (cents)."""
    out: list[OpenBill] = []
    for row in _query_rows(payload, "Bill"):
        vendor = row.get("VendorRef", {}) if isinstance(row.get("VendorRef"), dict) else {}
        out.append(
            OpenBill(
                id=str(row.get("Id", "")),
                doc_number=str(row.get("DocNumber", "")),
                vendor=str(vendor.get("name", vendor.get("value", ""))),
                txn_date=_parse_iso_date(row.get("TxnDate")),
                due_date=_parse_iso_date(row.get("DueDate")),
                total_cents=dollars_to_cents(row.get("TotalAmt")),
                balance_cents=dollars_to_cents(row.get("Balance")),
            )
        )
    return out


def parse_payment_query(payload: dict) -> list[PaymentRow]:
    """Parse ``QueryResponse.Payment`` rows into :class:`PaymentRow` (cents)."""
    out: list[PaymentRow] = []
    for row in _query_rows(payload, "Payment"):
        customer = row.get("CustomerRef", {}) if isinstance(row.get("CustomerRef"), dict) else {}
        out.append(
            PaymentRow(
                id=str(row.get("Id", "")),
                customer=str(customer.get("name", customer.get("value", ""))),
                txn_date=_parse_iso_date(row.get("TxnDate")),
                amount_cents=dollars_to_cents(row.get("TotalAmt")),
            )
        )
    return out


def cash_collected_cents(payments: list[PaymentRow]) -> int:
    """Sum of received-payment amounts (the ``cash_collected`` KPI, §2.1/§2.2)."""
    return sum(p.amount_cents for p in payments)
