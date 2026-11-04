"""Parse a supplier / distributor PRICE FILE (CSV or Excel) into ``VendorPriceUpdate`` rows.

This is Alex's "supply an Excel sheet to teach the agent" path: most HVAC/plumbing distributors hand a
contractor a downloadable price file from their portal (Ferguson, Watsco/Gemaire, Johnstone, RE Michel,
Winsupply, Lennox PartnerLink, ...) rather than a clean public API. The formats vary wildly — different
header names, ``$1,234.56`` vs ``1234.56``, a UOM column, total/blank rows — so this parser maps flexibly
and converts money to integer **cents** (ADR-0003). CSV uses the stdlib; XLSX uses openpyxl (lazy import).

Pure + deterministic: the same file always yields the same updates. The parsed updates feed the normal
Pricebook re-price engine; the actual price write still goes through the human-approved action gate.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date

from app.agents.pricebook.models import VendorPriceUpdate

# Header synonyms (normalized: lowercased, stripped). A column matches if its normalized name equals one
# of these OR contains one as a whole word. COST is resolved by PRIORITY (a "net/your cost" beats "list").
_SKU_NAMES = ("sku", "item", "item #", "item#", "item number", "item no", "part", "part #",
              "part number", "part no", "catalog", "catalog #", "catalog number", "product",
              "product code", "model", "mpn", "mfg #", "mfg part")
_COST_PRIORITY = ("net cost", "your cost", "net price", "your price", "dealer price", "dealer cost",
                  "contractor price", "contractor cost", "unit cost", "cost", "unit price", "price",
                  "list price", "list")
_VENDOR_NAMES = ("vendor", "supplier", "distributor", "manufacturer", "mfg", "mfr", "brand")
_DESC_NAMES = ("description", "desc", "name", "item description", "product description")
_DATE_NAMES = ("effective date", "effective", "price date", "as of", "date")

# Rows whose SKU/first cell looks like a subtotal/footer are skipped.
_SKIP_TOKENS = ("total", "subtotal", "grand total", "page ", "thank you")

MAX_ROWS = 50_000  # a hard cap so a giant/garbage upload can't exhaust memory


class PriceFileError(ValueError):
    """The price file could not be parsed into vendor price updates (no SKU/cost column, all rows bad)."""


def _norm(h: object) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().lower())


def money_to_cents(value: object) -> int | None:
    """``"$1,234.56"`` | ``"1234.5"`` | ``"(12.00)"`` | ``12`` -> integer cents; junk/blank -> None."""
    if value is None:
        return None
    s = str(value).strip().replace("$", "").replace(",", "").replace("USD", "").strip()
    if not s:
        return None
    neg = s.startswith("(") and s.endswith(")")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    cents = int(round(float(m.group()) * 100))
    return -cents if (neg and cents > 0) else cents


def _resolve_columns(headers: list[str]) -> tuple[str, str, str | None, str | None, str | None]:
    """Pick the (sku, cost, vendor?, desc?, date?) header keys from the file's headers. Raises if no
    SKU or no cost column can be found."""
    norm = {h: _norm(h) for h in headers}

    def find(names: tuple[str, ...]) -> str | None:
        # exact match first, then whole-word contains
        for h, n in norm.items():
            if n in names:
                return h
        for name in names:
            for h, n in norm.items():
                if re.search(rf"(^|[^a-z]){re.escape(name)}([^a-z]|$)", n):
                    return h
        return None

    sku = find(_SKU_NAMES)
    # cost: walk the priority list, return the first header that matches one
    cost = None
    for pref in _COST_PRIORITY:
        for h, n in norm.items():
            if n == pref or re.search(rf"(^|[^a-z]){re.escape(pref)}([^a-z]|$)", n):
                cost = h
                break
        if cost:
            break
    if sku is None or cost is None:
        raise PriceFileError(
            f"could not find a SKU column ({'ok' if sku else 'MISSING'}) and a cost column "
            f"({'ok' if cost else 'MISSING'}) in headers: {headers}"
        )
    return sku, cost, find(_VENDOR_NAMES), find(_DESC_NAMES), find(_DATE_NAMES)


def _parse_date(value: object, fallback: date) -> date:
    s = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d-%b-%Y", "%b %d, %Y"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return fallback


def parse_rows(
    rows: list[dict],
    *,
    default_vendor: str = "vendor",
    effective: date | None = None,
) -> list[VendorPriceUpdate]:
    """Map a list of header->value dict rows into ``VendorPriceUpdate``. Rows missing a SKU or a usable
    cost are skipped; subtotal/footer rows are skipped; the LAST cost wins for a duplicated SKU."""
    if not rows:
        raise PriceFileError("price file is empty")
    if len(rows) > MAX_ROWS:
        raise PriceFileError(f"price file has too many rows ({len(rows)} > {MAX_ROWS})")
    eff = effective or date.today()
    sku_c, cost_c, vendor_c, desc_c, date_c = _resolve_columns(list(rows[0].keys()))

    by_sku: dict[str, VendorPriceUpdate] = {}
    for row in rows:
        sku = str(row.get(sku_c, "") or "").strip()
        if not sku or any(tok in sku.lower() for tok in _SKIP_TOKENS):
            continue
        cents = money_to_cents(row.get(cost_c))
        if cents is None or cents <= 0:
            continue
        vendor = str(row.get(vendor_c, "") or "").strip() if vendor_c else ""
        by_sku[sku] = VendorPriceUpdate(
            sku=sku,
            vendor=vendor or default_vendor,
            new_unit_cost_cents=cents,
            effective_date=_parse_date(row.get(date_c), eff) if date_c else eff,
            note=(str(row.get(desc_c, "") or "").strip() or None) if desc_c else None,
        )
    if not by_sku:
        raise PriceFileError("no valid SKU + cost rows found in the price file")
    return list(by_sku.values())


def parse_csv_text(text: str, **kw) -> list[VendorPriceUpdate]:
    rows = list(csv.DictReader(io.StringIO(text)))
    return parse_rows(rows, **kw)


def parse_xlsx_bytes(data: bytes, **kw) -> list[VendorPriceUpdate]:
    try:
        import openpyxl  # lazy: the module loads even where openpyxl isn't installed (CSV still works)
    except ImportError as e:  # pragma: no cover
        raise PriceFileError("Excel (.xlsx) parsing needs openpyxl installed") from e
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    try:
        headers = [str(h) if h is not None else f"col{i}" for i, h in enumerate(next(it))]
    except StopIteration:
        raise PriceFileError("Excel file is empty") from None
    rows = [dict(zip(headers, vals)) for vals in it]
    return parse_rows(rows, **kw)


def parse_price_file(filename: str, data: bytes, **kw) -> list[VendorPriceUpdate]:
    """Dispatch on the filename extension (.csv/.tsv -> stdlib; .xlsx/.xlsm -> openpyxl)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return parse_xlsx_bytes(data, **kw)
    return parse_csv_text(data.decode("utf-8-sig", errors="replace"), **kw)
